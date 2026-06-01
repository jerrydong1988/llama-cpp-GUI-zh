"""Configuration persistence helpers.

Provides atomic JSON file I/O and parameter serialization utilities,
independent of the UI layer.
"""

import json
import os
import threading


def save_atomic(filepath, data):
    """Save data to JSON file atomically (tmp + fsync + replace).

    Args:
        filepath: Target JSON file path.
        data: JSON-serializable dict.

    Returns:
        True on success, raises on failure.
    """
    tmp = filepath + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, filepath)
    return True


def load_json(filepath):
    """Load JSON data from file.

    Returns dict or empty dict if file does not exist.
    """
    if not os.path.isfile(filepath):
        return {}
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def params_to_dict(param_defs, get_var):
    """Serialize UI parameters to dict using a param definition table.

    Args:
        param_defs: List of (config_key, attr_name, cli_flag, kind, default) tuples.
        get_var: Callable that returns tk.Variable or None for an attr_name.

    Returns:
        dict of config_key -> value.
    """
    d = {}
    for ck, an, flag, kind, default in param_defs:
        var = get_var(an)
        if var is None:
            d[ck] = default
            continue
        val = var.get()
        if kind == "bool":
            d[ck] = bool(val)
        elif kind == "int":
            d[ck] = int(val) if val else default
        else:
            d[ck] = str(val).strip() if str(val).strip() else str(default)
    return d


def params_from_dict(config, param_defs, get_var, set_var_cb):
    """Restore UI parameters from a config dict.

    Args:
        config: dict of config_key -> value.
        param_defs: List of (config_key, attr_name, cli_flag, kind, default) tuples.
        get_var: Callable that returns tk.Variable or None for an attr_name.
        set_var_cb: Called with (attr_name, value) for each restored param.
    """
    for ck, an, flag, kind, default in param_defs:
        val = config.get(ck, default)
        if kind == "bool":
            set_var_cb(an, bool(val))
        elif kind == "int":
            try:
                set_var_cb(an, int(val))
            except (ValueError, TypeError):
                set_var_cb(an, default)
        else:
            set_var_cb(an, str(val) if val is not None else str(default))