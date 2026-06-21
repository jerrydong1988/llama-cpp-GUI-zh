"""GGUF model file reader and classifier.

Provides cached reading of GGUF binary headers for metadata extraction,
file type classification (model/mmproj/imatrix), and embedding model
detection. All functions are stateless and LRU-cached to avoid
redundant file I/O.
"""

import struct
import os
from functools import lru_cache

# ── Known embedding model architectures ────────────────────────────
EMBEDDING_ARCHS = frozenset({
    "bge", "gte", "e5", "text-embedding",
    "sentence-bert", "sentence-t5", "instructor",
})


def _read_string(f):
    """Read a GGUF string: length (uint64) + UTF-8 data."""
    length = struct.unpack("<Q", f.read(8))[0]
    return f.read(length).decode("utf-8", errors="replace")


def _read_value(f):
    """Read a GGUF value based on its type. Returns the value or None."""
    val_type = struct.unpack("<I", f.read(4))[0]
    if val_type == 8:          # STRING
        return _read_string(f)
    elif val_type == 7:        # BOOL
        return struct.unpack("<?", f.read(1))[0]
    elif val_type == 0:        # UINT8
        return struct.unpack("<B", f.read(1))[0]
    elif val_type == 1:        # INT8
        return struct.unpack("<b", f.read(1))[0]
    elif val_type == 2:        # UINT16
        return struct.unpack("<H", f.read(2))[0]
    elif val_type == 3:        # INT16
        return struct.unpack("<h", f.read(2))[0]
    elif val_type == 4:        # UINT32
        return struct.unpack("<I", f.read(4))[0]
    elif val_type == 5:        # INT32
        return struct.unpack("<i", f.read(4))[0]
    elif val_type == 10:       # UINT64
        return struct.unpack("<Q", f.read(8))[0]
    elif val_type == 11:       # INT64
        return struct.unpack("<q", f.read(8))[0]
    elif val_type == 6:        # FLOAT32
        return struct.unpack("<f", f.read(4))[0]
    elif val_type == 12:       # FLOAT64
        return struct.unpack("<d", f.read(8))[0]
    elif val_type == 9:        # ARRAY - skip
        arr_type = struct.unpack("<I", f.read(4))[0]
        arr_len = struct.unpack("<Q", f.read(8))[0]
        for _ in range(arr_len):
            if arr_type == 8:
                _read_string(f)
            elif arr_type in (0, 1, 2, 3, 4, 5, 6, 7, 10, 11, 12):
                f.read({0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}[arr_type])
            else:
                f.read(8)
        return None
    return None


@lru_cache(maxsize=256)
def read_metadata(filepath):
    """Read basic GGUF metadata from the file header.

    Returns dict with architecture, context_length, file_type, etc.
    Cached via lru_cache to avoid repeated file I/O.
    """
    try:
        with open(filepath, "rb") as f:
            magic = f.read(4)
            if magic != b"GGUF":
                return None

            version = struct.unpack("<I", f.read(4))[0]
            tensor_count = struct.unpack("<Q", f.read(8))[0]
            metadata_count = struct.unpack("<Q", f.read(8))[0]

            meta = {}
            for _ in range(min(metadata_count, 500)):
                try:
                    key = _read_string(f)
                    val = _read_value(f)
                    if key and val is not None:
                        meta[key] = val
                except Exception:
                    break
            return meta
    except Exception:
        return None


@lru_cache(maxsize=256)
def read_type(filepath):
    """Cached helper: read general.type from GGUF header."""
    meta = read_metadata(filepath)
    return meta.get("general.type", "unknown") if meta else "unknown"


@lru_cache(maxsize=256)
def is_embedding_check(filepath):
    """Cached helper: check if a GGUF model is an embedding model."""
    meta = read_metadata(filepath)
    if not meta:
        return False
    arch = meta.get("general.architecture", "")
    if arch and arch.lower() in EMBEDDING_ARCHS:
        return True
    basename = meta.get("general.basename", "")
    if basename and "embed" in basename.lower():
        return True
    name = meta.get("general.name", "")
    if name and "embed" in name.lower():
        return True
    return False


def classify_file(filepath=None, fname=None):
    """Determine if a GGUF file is mmproj / model / imatrix / unknown.

    Priority:
    1. Local file -> read GGUF header ``general.type`` (authoritative).
    2. Filename heuristic (fallback / ModelScope remote).

    Returns ``"mmproj"``, ``"model"``, ``"imatrix"``, or ``"unknown"``.
    """
    # --- Filename heuristic (imatrix detected by name, not header) ---
    if fname:
        lower = fname.lower()
        if "imatrix" in lower:
            return "imatrix"

    # --- GGUF header (authoritative for mmproj vs model) ---
    if filepath and os.path.isfile(filepath):
        tp = read_type(filepath)
        if tp in ("mmproj", "model"):
            return tp

    # --- Filename heuristic (mmproj fallback) ---
    if fname:
        lower = fname.lower()
        if "mmproj" in lower:
            return "mmproj"
        if lower.endswith(".gguf") or lower.endswith(".gguf_file"):
            return "model"

    return "unknown"


def is_embedding_model(filepath=None, fname=None):
    """Detect if a GGUF file is an embedding / vector model.

    Priority:
    1. Local file -> read GGUF header (authoritative).
    2. Filename heuristic (ModelScope remote / fallback).
    """
    # --- GGUF header (authoritative for local files) ---
    if filepath and os.path.isfile(filepath):
        if is_embedding_check(filepath):
            return True

    # --- Filename heuristic ---
    if fname:
        lower = fname.lower()
        if "mmproj" in lower or "imatrix" in lower:
            return False
        if "embed" in lower:
            return True

    return False


def metadata_display(filepath):
    """Get a human-readable string of model metadata from GGUF header."""
    meta = read_metadata(filepath)
    if not meta:
        return "\u65e0\u6cd5\u8bfb\u53d6\u5143\u4fe1\u606f"  # 无法读取元信息

    lines = []
    arch = meta.get("general.architecture", "")
    if arch:
        lines.append(f"\u67b6\u6784: {arch}")

    ctx = meta.get(f"{arch}.context_length") if arch else None
    if not ctx:
        for k, v in meta.items():
            if "context_length" in k:
                ctx = v
                break
    if ctx:
        lines.append(f"\u4e0a\u4e0b\u6587: {ctx:,} tokens")

    ftype = meta.get("general.file_type", "")
    if ftype:
        type_names = {1: "F32", 2: "F16", 3: "Q4_0", 5: "Q4_1", 7: "Q8_0",
                      8: "Q5_0", 9: "Q5_1", 10: "Q2_K", 12: "Q3_K",
                      13: "Q4_K", 14: "Q5_K", 15: "Q6_K", 16: "Q8_K"}
        lines.append(f"\u91cf\u5316: {type_names.get(ftype, f'Type {ftype}')}")

    params = meta.get("general.size_label", "")
    if not params and arch:
        n_layer = meta.get(f"{arch}.block_count", 0)
        if n_layer:
            lines.append(f"\u5c42\u6570: {n_layer}")

    name = meta.get("general.name", "")
    if name:
        lines.insert(0, f"\u6a21\u578b: {name}")

    return " | ".join(lines) if lines else "\u57fa\u672c\u5143\u4fe1\u606f"