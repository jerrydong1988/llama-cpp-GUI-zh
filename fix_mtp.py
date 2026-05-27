#!/usr/bin/env python3
"""Fix MTP/speculative decoding support in GUI."""
import os, shutil

# ⚠ WARNING: One-time migration script. Hardcoded Windows path, will not work on other machines.
SRC = "C:/Users/Jerry/Projects/llama-cpp-GUI/llama-server_gui_new.py"

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Fix the deprecated --draft flag → --spec-draft-n-max in generate_command
content = content.replace(
    "'--draft': self.draft_tokens,",
    "'--spec-draft-n-max': self.draft_tokens,"
)

# 2. Fix the draft tokens label and tooltip
content = content.replace(
    '草稿令牌数 (--draft):',
    '草稿令牌上限 (--spec-draft-n-max):'
)
content = content.replace(
    '"草稿令牌数（例如 5）。"',
    '"推测解码最大草稿令牌数（默认 16）。--draft 已废弃，改用此参数。"'
)

# 3. Add --spec-type combobox and --spec-draft-n-min and --spec-draft-hf
#    Insert after the draft_tokens spinbox line
old_line = '        self.create_spinbox(spec_group, "草稿令牌上限 (--spec-draft-n-max):", self.draft_tokens, "推测解码最大草稿令牌数（默认 16）。--draft 已废弃，改用此参数。", row=2, from_=1, to=1024, increment=1)\n'
new_block = old_line + """\
        self.spec_draft_n_min = tk.StringVar(value="")
        self.create_spinbox(spec_group, "最小草稿令牌数 (--spec-draft-n-min):", self.spec_draft_n_min, "推测解码最小草稿令牌数（默认 0）。", row=3, from_=0, to=512, increment=1)
        self.spec_type = tk.StringVar()
        spec_types = ["", "none", "draft-simple", "draft-eagle3", "draft-mtp", "ngram-simple", "ngram-map-k", "ngram-mod", "ngram-cache"]
        self.create_combobox(spec_group, "推测解码类型 (--spec-type):", self.spec_type, "推测解码类型。draft-mtp = 多令牌预测，draft-simple = 简单草稿，ngram-mod = ngram 缓存等。可组合多个，用逗号分隔。", spec_types, row=4)
        self.draft_hf_repo = tk.StringVar()
        self.create_entry(spec_group, "草稿 HF 仓库 (--hf-repo-draft):", self.draft_hf_repo, "草稿模型的 HuggingFace 仓库，例如 ggml-org/Qwen2.5-0.5B-GGUF:Q4_K_M，设置后自动下载。", row=5)

"""
content = content.replace(old_line, new_block)

# 4. Add new params to args dict (before the current self.draft_tokens line in args)
content = content.replace(
    "'--spec-draft-n-max': self.draft_tokens,",
    "'--spec-draft-n-max': self.draft_tokens,\n"
    "            '--spec-draft-n-min': self.spec_draft_n_min,\n"
    "            '--spec-type': self.spec_type,\n"
    "            '--hf-repo-draft': self.draft_hf_repo,"
)

# 5. Add to save_config
content = content.replace(
    "'draft_tokens': self.draft_tokens.get(),\n"
    "            'cache_type_k':",
    "'draft_tokens': self.draft_tokens.get(),\n"
    "            'spec_draft_n_min': self.spec_draft_n_min.get(),\n"
    "            'spec_type': self.spec_type.get(),\n"
    "            'draft_hf_repo': self.draft_hf_repo.get(),\n"
    "            'cache_type_k':"
)

# 6. Add to load_config (after draft_tokens set line)
content = content.replace(
    "self.draft_tokens.set(config.get('draft_tokens', ''))\n"
    "            self.seed.set(config.get('seed', ''))",
    "self.draft_tokens.set(config.get('draft_tokens', ''))\n"
    "            self.spec_draft_n_min.set(config.get('spec_draft_n_min', ''))\n"
    "            self.spec_type.set(config.get('spec_type', ''))\n"
    "            self.draft_hf_repo.set(config.get('draft_hf_repo', ''))\n"
    "            self.seed.set(config.get('seed', ''))"
)

# Write
bak = SRC + ".bak3"
if not os.path.exists(bak):
    shutil.copy2(SRC, bak)
    print(f"Backup: {bak}")

with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print("✅ MTP/speculative decoding fixes applied")
