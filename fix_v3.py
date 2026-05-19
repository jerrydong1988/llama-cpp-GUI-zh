#!/usr/bin/env python3
"""Fix: add --reasoning and --ctx-size 0 auto support."""
import os, shutil

SRC = "C:/Users/Jerry/Projects/llama-cpp-GUI/llama-server_gui_new.py"
BAK = SRC + ".bak4"

# Read file
with open(SRC, "r", encoding="utf-8") as f:
    lines = f.readlines()

eol = '\r\n' if any(l.endswith('\r\n') for l in lines) else '\n'
print(f"EOL: {repr(eol)}, lines: {len(lines)}")

# ============================================================
# 1. Add --reasoning combobox in Chat Behavior section
# ============================================================
# Insert after the reasoning_effort combobox line (row=2) and before jinja checkbox
for i, line in enumerate(lines):
    if 'self.create_combobox(chat_group, "推理力度:' in line:
        reasoning_block = f"""\
        self.reasoning = tk.StringVar()
        reasoning_options = ["", "on", "off", "auto"]
        self.create_combobox(chat_group, "推理开关 (--reasoning):", self.reasoning, "启用/禁用/自动推理（思考）功能。MTP 模型建议设为 off。", reasoning_options, row=3)
        self.jinja = tk.BooleanVar(value=False)
        self.create_checkbutton(chat_group, "启用 Jinja (--jinja)", self.jinja, "启用 Jinja2 模板（某些自定义模板需要）。", row=4)
"""
        # Replace the original jinja line and insert reasoning before it
        # Find the jinja line and the one after it
        for j in range(i, len(lines)):
            if 'self.jinja = tk.BooleanVar(value=False)' in lines[j]:
                lines[j] = reasoning_block
                print(f"Inserted --reasoning at line {j+1}")
                break
        break

# ============================================================
# 2. Add auto-context checkbox in Core Performance
# ============================================================
# Insert after the ctx_size slider creation
for i, line in enumerate(lines):
    if 'self.create_slider(core_group, "上下文大小 (-c):"' in line:
        auto_ctx_block = f"""\
        self.ctx_size_auto = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(core_group, text="自动上下文 (--ctx-size 0)", variable=self.ctx_size_auto, bootstyle="round-toggle")
        cb.grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ToolTip(cb, "勾选后不传 -c 参数，llama-server 自动使用模型完整上下文长度。")

"""
        lines.insert(i+1, auto_ctx_block)
        print(f"Inserted ctx_size_auto after line {i+1}")
        break

# ============================================================
# 3. Update generate_command - handle ctx_size_auto
# ============================================================
for i, line in enumerate(lines):
    if "cmd.extend(['-c', str(self.ctx_size.get())])" in line:
        lines[i] = f"""\
        if not self.ctx_size_auto.get():
            cmd.extend(['-c', str(self.ctx_size.get())])
"""
        print(f"Updated ctx_size handling at line {i+1}")
        break

# ============================================================
# 4. Add --reasoning to args dict
# ============================================================
for i, line in enumerate(lines):
    if "'--hf-repo-draft': self.draft_hf_repo," in line:
        lines.insert(i, "            '--reasoning': self.reasoning,\n")
        print(f"Added --reasoning to args dict at line {i+1}")
        break

# ============================================================
# 5. Update save_config
# ============================================================
for i, line in enumerate(lines):
    if "'hf_repo': self.hf_repo.get()" in line:
        lines.insert(i, "            'reasoning': self.reasoning.get(),\n")
        lines.insert(i, "            'ctx_size_auto': self.ctx_size_auto.get(),\n")
        print(f"Added save_config fields at line {i+1}")
        break

# ============================================================
# 6. Update load_config
# ============================================================
for i, line in enumerate(lines):
    if "self.cache_prompt.set(config.get('cache_prompt', True))" in line:
        lines.insert(i+1, "            self.reasoning.set(config.get('reasoning', ''))\n")
        lines.insert(i+1, "            self.ctx_size_auto.set(config.get('ctx_size_auto', False))\n")
        print(f"Added load_config fields at line {i+1}")
        break

# Write
if not os.path.exists(BAK):
    shutil.copy2(SRC, BAK)
    print(f"Backup: {BAK}")

content = ''.join(lines)
with open(SRC, "w", encoding="utf-8") as f:
    f.write(content)

print(f"✅ Written to {SRC}, {len(lines)} lines")
