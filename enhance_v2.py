#!/usr/bin/env python3
"""Apply first-wave enhancements to llama-cpp-GUI Chinese version."""

import os, sys

SRC = "C:/Users/Jerry/Projects/llama-cpp-GUI/llama-server_gui_new.py"

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()
    lines = content.splitlines(keepends=True)
    # Normalize line endings - check what we have
    eol = '\r\n' if content.find('\r\n') >= 0 else '\n'
    print(f"Detected line ending: {repr(eol)}")

# Now fix insert_after patterns to use detected EOL
# We need to re-read the file since we modified it with the normalization

import re

with open(SRC, "r", encoding="utf-8") as f:
    content = f.read()
    lines = content.splitlines(keepends=True)
    eol = '\r\n' if content.find('\r\n') >= 0 else '\n'

# Also detect EOL
eol = content.find('\r\n') >= 0 and '\r\n' or '\n'
print(f"Using EOL: {repr(eol)}")

# ============================================================
# 1. Add HuggingFace section to Model tab (after mmproj line)
# ============================================================
hf_section = f"""\
        # --- HuggingFace Auto Download ---
        hf_group = ttk.Labelframe(parent, text="HuggingFace 自动下载", padding="10")
        hf_group.pack(fill=tk.X, pady=5)
        self.hf_repo = tk.StringVar()
        self.create_entry(hf_group, "HF 仓库 (--hf-repo):", self.hf_repo, "HuggingFace 模型仓库，例如 ggml-org/gemma-3-1b-it-GGUF:Q4_K_M，设置后自动下载。", row=0)
        self.hf_file = tk.StringVar()
        self.create_entry(hf_group, "HF 文件 (--hf-file):", self.hf_file, "指定仓库中的具体文件名（可选，覆盖 --hf-repo 中的量化级别）。", row=1)

"""

# ============================================================
# 2. All expansion content blocks
# ============================================================
sampling_expansion = """\
        self.seed = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "随机种子 (--seed):", self.seed, "RNG 种子（默认 -1 = 随机）。设为固定值可重现结果。", from_=-1, to=2147483647, increment=1, row=4)
        self.min_p = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "Min-P (--min-p):", self.min_p, "最小概率采样（默认 0.05，0.0 = 禁用）。比 top-p 更新更好的采样方式。", from_=0, to=1, increment=0.05, row=5)
        self.presence_penalty = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "存在惩罚 (--presence-penalty):", self.presence_penalty, "话题存在惩罚（默认 0.0）。降低重复讨论相同话题。", from_=0, to=2, increment=0.1, row=6)
        self.frequency_penalty = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "频率惩罚 (--frequency-penalty):", self.frequency_penalty, "词频惩罚（默认 0.0）。降低高频词重复出现。", from_=0, to=2, increment=0.1, row=7)
        self.repeat_last_n = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "惩罚窗口 (--repeat-last-n):", self.repeat_last_n, "重复惩罚考虑的最近令牌数（默认 64，0 = 禁用，-1 = 上下文大小）。", from_=-1, to=4096, increment=1, row=8)

"""

perf_expansion = """\
        self.cache_prompt = tk.BooleanVar(value=True)
        self.create_checkbutton(throughput_group, "提示缓存 (--cache-prompt)", self.cache_prompt, "启用提示缓存以提高重复请求的速度（默认启用）。", row=2)
        self.threads_batch = tk.StringVar(value="")
        self.create_spinbox(core_group, "批处理线程 (-tb, --threads-batch):", self.threads_batch, "提示处理和批处理时使用的线程数（默认同 --threads）。", from_=1, to=128, increment=1, row=5)

"""

advanced_expansion = """\
        # --- Server Reliability ---
        server_rel_group = ttk.Labelframe(parent, text="服务器可靠性", padding="10")
        server_rel_group.pack(fill=tk.X, pady=5)
        self.timeout = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "超时秒数 (--timeout):", self.timeout, "服务器读写超时秒数（默认 600）。", from_=1, to=3600, increment=10, row=0)
        self.sleep_idle = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "空闲休眠秒数 (--sleep-idle-seconds):", self.sleep_idle, "空闲 N 秒后自动卸载模型释放显存（默认 -1 = 禁用）。", from_=-1, to=86400, increment=60, row=1)

"""

server_expansion = """\
        self.pooling = tk.StringVar()
        pooling_options = ["", "none", "mean", "cls", "last", "rank"]
        self.create_combobox(access_group, "嵌入池化 (--pooling):", self.pooling, "嵌入模型的池化类型（使用嵌入模式时需设置）。", pooling_options, row=3)
        self.reranking = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "重排序端点 (--reranking)", self.reranking, "启用重排序端点（RAG 场景）。", row=4)

"""

# All insert points: (line_starts_with_pattern, content_to_insert)
insert_points = [
    ('self.create_file_entry(ext_group, "多模态投影器 (--mmproj):', hf_section),
    ('self.create_spinbox(sampling_group, "重复惩罚 (--repeat-penalty):', sampling_expansion),
    ('self.create_checkbutton(throughput_group, "持续批处理 (-cb)"', perf_expansion),
    ('self.create_spinbox(spec_group, "草稿令牌数 (--draft):', advanced_expansion),
    ('self.create_checkbutton(access_group, "仅嵌入模式 (--embedding)"', server_expansion),
]

# Apply all insert points
for pattern, content in insert_points:
    found = False
    for i, line in enumerate(lines):
        if line.strip().startswith(pattern):
            lines.insert(i+1, content)
            print(f"  Inserted after line {i+1}: {pattern[:50]}...")
            found = True
            break
    if not found:
        print(f"  ⚠ Not found: {pattern[:50]}...")

print()

# ============================================================
# 6. Update generate_command()
# ============================================================
# Find the args dict and add new params
for i, line in enumerate(lines):
    if "'--cache-type-v': self.cache_type_v" in line:
        # Add new string params before the closing }
        lines.insert(i, "            '--hf-repo': self.hf_repo,\n")
        lines.insert(i, "            '--hf-file': self.hf_file,\n")
        lines.insert(i, "            '--seed': self.seed,\n")
        lines.insert(i, "            '--min-p': self.min_p,\n")
        lines.insert(i, "            '--presence-penalty': self.presence_penalty,\n")
        lines.insert(i, "            '--frequency-penalty': self.frequency_penalty,\n")
        lines.insert(i, "            '--repeat-last-n': self.repeat_last_n,\n")
        lines.insert(i, "            '--tb': self.threads_batch,\n")
        lines.insert(i, "            '-to': self.timeout,\n")
        lines.insert(i, "            '--sleep-idle-seconds': self.sleep_idle,\n")
        lines.insert(i, "            '--pooling': self.pooling,\n")
        print(f"Added string params to args dict near line {i+1}")
        break

# Add bool params
for i, line in enumerate(lines):
    if "'--ignore-eos': self.ignore_eos" in line:
        lines.insert(i, "            '--reranking': self.reranking,\n")
        lines.insert(i, "            '--no-cache-prompt': self.cache_prompt_no,\n")
        print(f"Added bool params near line {i+1}")
        break

# Handle cache-prompt (it's inverted - enabled by default, --no-cache-prompt to disable)
# We need a negated variable
for i, line in enumerate(lines):
    if "self.cache_prompt = tk.BooleanVar(value=True)" in line:
        # Add the negated variable right after
        lines.insert(i+1, "        self.cache_prompt_no = tk.BooleanVar(value=False)\n")
        print(f"Added cache_prompt_no after line {i+1}")
        break

# Fix the bool_args section to handle --no-cache-prompt (inverted logic)
for i, line in enumerate(lines):
    if "'--ignore-eos': self.ignore_eos" in line:
        # Replace this line to add the new bool args
        # Actually it'll be handled by the insert above
        pass

# ============================================================
# 7. Update save_config()
# ============================================================
for i, line in enumerate(lines):
    if "'cache_type_v': self.cache_type_v.get()" in line:
        lines.insert(i, "            'hf_repo': self.hf_repo.get(), 'hf_file': self.hf_file.get(),\n")
        lines.insert(i, "            'seed': self.seed.get(), 'min_p': self.min_p.get(),\n")
        lines.insert(i, "            'presence_penalty': self.presence_penalty.get(), 'frequency_penalty': self.frequency_penalty.get(),\n")
        lines.insert(i, "            'repeat_last_n': self.repeat_last_n.get(),\n")
        lines.insert(i, "            'threads_batch': self.threads_batch.get(),\n")
        lines.insert(i, "            'cache_prompt': self.cache_prompt.get(),\n")
        lines.insert(i, "            'timeout': self.timeout.get(), 'sleep_idle': self.sleep_idle.get(),\n")
        lines.insert(i, "            'pooling': self.pooling.get(), 'reranking': self.reranking.get(),\n")
        print(f"Added save_config fields near line {i+1}")
        break

# ============================================================
# 8. Update load_config()
# ============================================================
# Find the load_config section and add new fields
# We need to find the end of the load_config set() chain
for i, line in enumerate(lines):
    if "self.repeat_penalty.set(config.get('repeat_penalty', ''))" in line:
        lines.insert(i+1, "            self.seed.set(config.get('seed', ''))\n")
        lines.insert(i+1, "            self.min_p.set(config.get('min_p', ''))\n")
        lines.insert(i+1, "            self.presence_penalty.set(config.get('presence_penalty', ''))\n")
        lines.insert(i+1, "            self.frequency_penalty.set(config.get('frequency_penalty', ''))\n")
        lines.insert(i+1, "            self.repeat_last_n.set(config.get('repeat_last_n', ''))\n")
        lines.insert(i+1, "            self.hf_repo.set(config.get('hf_repo', ''))\n")
        lines.insert(i+1, "            self.hf_file.set(config.get('hf_file', ''))\n")
        lines.insert(i+1, "            self.threads_batch.set(config.get('threads_batch', ''))\n")
        lines.insert(i+1, "            self.timeout.set(config.get('timeout', ''))\n")
        lines.insert(i+1, "            self.sleep_idle.set(config.get('sleep_idle', ''))\n")
        lines.insert(i+1, "            self.pooling.set(config.get('pooling', ''))\n")
        lines.insert(i+1, "            self.reranking.set(config.get('reranking', False))\n")
        lines.insert(i+1, "            self.cache_prompt.set(config.get('cache_prompt', True))\n")
        print(f"Added load_config fields near line {i+1}")
        break

# ============================================================
# 9. Update the chat template list with newer templates
# ============================================================
for i, line in enumerate(lines):
    if 'chat_templates = [""' in line:
        lines[i] = '        chat_templates = ["", "bailing", "chatglm3", "chatglm4", "chatml", "command-r", "deepseek", "deepseek2", "deepseek3", "exaone3", "gemma", "gpt-oss", "kimi-k2", "llama2", "llama3", "llama4", "mistral", "openchat", "phi3", "phi4", "vicuna", "zephyr"]\n'
        print(f"Updated chat templates list at line {i+1}")
        break

# ============================================================
# Write the modified file
# ============================================================
# Create backup
bak = SRC + ".bak2"
if not os.path.exists(bak):
    import shutil
    shutil.copy2(SRC, bak)
    print(f"Backup: {bak}")

write_content = ''.join(lines)

with open(SRC, "w", encoding="utf-8") as f:
    f.write(write_content)

print(f"\n✅ All changes applied to: {SRC}")
print(f"Total lines: {len(lines)}")
