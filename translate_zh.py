#!/usr/bin/env python3
"""Translate llama-server_gui_new.py UI strings to Chinese."""

import shutil, os

SRC = "C:/Users/Jerry/Projects/llama-cpp-GUI/llama-server_gui_new.py"
BAK = SRC + ".bak"

# Read source
with open(SRC, "r", encoding="utf-8") as f:
    source = f.read()

# Backup
shutil.copy2(SRC, BAK)
print(f"Backup: {BAK}")

# All translations: (old, new) pairs
translations = [
    # Window
    ('"LLaMA Server GUI Manager"', '"LLaMA 服务器管理器"'),

    # Tab names
    ('"  Models "', '"  模型  "'),
    ('" Generation "', '"  生成参数  "'),
    ('" Performance "', '"  性能  "'),
    ('" Advanced "', '"  高级  "'),
    ('" Server & API "', '"  服务器与API  "'),
    ('" Server Output "', '"  服务器输出  "'),

    # Top buttons
    ('"Save As 💾"', '"另存为 💾"'),
    ('"Load (Browse) 📂"', '"加载配置 📂"'),
    ('"Generate Command ⚡"', '"生成命令 ⚡"'),
    ('"Open Browser 🌐"', '"打开浏览器 🌐"'),
    ('"Stop Server ⏹️"', '"停止服务器 ⏹️"'),
    ('"Start Server ▶️"', '"启动服务器 ▶️"'),

    # Labelframe titles
    ('"Primary Model"', '"主模型"'),
    ('"Model Extensions"', '"模型扩展"'),
    ('"Chat Behavior"', '"对话行为"'),
    ('"Output Control"', '"输出控制"'),
    ('"Sampling Parameters"', '"采样参数"'),
    ('"Core Performance"', '"核心性能"'),
    ('"Advanced Throughput"', '"高级吞吐量"'),
    ('"Memory & Optimizations"', '"内存与优化"'),
    ('"Speculative Decoding"', '"推测解码"'),
    ('"Network Configuration"', '"网络配置"'),
    ('"Access & Features"', '"访问与功能"'),
    ('"Custom Arguments Management"', '"自定义参数管理"'),

    # Model tab labels
    ('"Model Path (-m):"', '"模型路径 (-m):"'),
    ('"Model Alias (-a):"', '"模型别名 (-a):"'),
    ('"LoRA Path (--lora):"', '"LoRA 路径 (--lora):"'),
    ('"Multimodal Projector (--mmproj):"', '"多模态投影器 (--mmproj):"'),
    ('"Template (--chat-template):"', '"聊天模板 (--chat-template):"'),
    ('"Reasoning Format (--reasoning-format):"', '"推理格式 (--reasoning-format):"'),
    ('"Reasoning Effort:"', '"推理力度:"'),
    ('"Enable Jinja (--jinja)"', '"启用 Jinja (--jinja)"'),

    # Generation tab labels
    ('"Tokens to Generate (-n, --n-predict):"', '"生成令牌数 (-n, --n-predict):"'),
    ('"Ignore End-of-Sequence (--ignore-eos)"', '"忽略结束标记 (--ignore-eos)"'),
    ('"Temperature (--temp):"', '"温度 (--temp):"'),
    ('"Top-K (--top-k):"', '"Top-K (--top-k):"'),
    ('"Top-P (--top-p):"', '"Top-P (--top-p):"'),
    ('"Repeat Penalty (--repeat-penalty):"', '"重复惩罚 (--repeat-penalty):"'),

    # Performance tab labels
    ('"Context Size (-c):"', '"上下文大小 (-c):"'),
    ('"GPU Layers (-ngl):"', '"GPU 层数 (-ngl):"'),
    ('"CPU Threads (-t):"', '"CPU 线程数 (-t):"'),
    ('"Batch Size (-b):"', '"批大小 (-b):"'),
    ('"Physical Batch Size (-ub):"', '"物理批大小 (-ub):"'),
    ('"Parallel Sequences (-np):"', '"并行序列数 (-np):"'),
    ('"Continuous Batching (-cb)"', '"持续批处理 (-cb)"'),

    # Advanced tab labels
    ('"Flash Attention (-fa):"', '"Flash Attention (-fa):"'),
    ('"MoE CPU Layers (--n-cpu-moe):"', '"MoE CPU 层数 (--n-cpu-moe):"'),
    ('"Memory Lock (--mlock)"', '"内存锁定 (--mlock)"'),
    ('"No Memory Mapping (--no-mmap)"', '"禁用内存映射 (--no-mmap)"'),
    ('"NUMA Optimizations (--numa)"', '"NUMA 优化 (--numa)"'),
    ('"Cache Type K (-ctk, --cache-type-k):"', '"K 缓存类型 (-ctk):"'),
    ('"Cache Type V (-ctv, --cache-type-v):"', '"V 缓存类型 (-ctv):"'),
    ('"Draft Model (-md):"', '"草稿模型 (-md):"'),
    ('"Draft GPU Layers (-ngld):"', '"草稿 GPU 层数 (-ngld):"'),
    ('"Draft Tokens (--draft):"', '"草稿令牌数 (--draft):"'),

    # Server & API tab labels
    ('"Host (--host):"', '"主机 (--host):"'),
    ('"Port (--port):"', '"端口 (--port):"'),
    ('"API Key (--api-key):"', '"API 密钥 (--api-key):"'),
    ('"Disable Web UI (--no-webui)"', '"禁用网页界面 (--no-webui)"'),
    ('"Embeddings Only (--embedding)"', '"仅嵌入模式 (--embedding)"'),
    ('"Verbose Logging (-v)"', '"详细日志 (-v)"'),

    # Output tab
    ('"Server Log Output:"', '"服务器日志输出："'),
    ('"Clear Output"', '"清空输出"'),
    ('"Browse"', '"浏览"'),

    # Custom args
    ('"Add"', '"添加"'),
    ('"Delete"', '"删除"'),

    # Show command window
    ('"Generated Command"', '"生成的命令"'),
    ('"Generated Command:"', '"生成的命令："'),
    ('"Copy to Clipboard"', '"复制到剪贴板"'),

    # Messagebox strings
    ('"Duplicate Argument"', '"重复参数"'),
    ('"This argument already exists in the list."', '"该参数已存在于列表中。"'),
    ('"Error"', '"错误"'),
    ('"Model path is required!"', '"请选择模型路径！"'),
    ('"Not Found"', '"未找到"'),
    ('"Success"', '"成功"'),
    ('"Copied"', '"已复制"'),
    ('"Command copied to clipboard!"', '"命令已复制到剪贴板！"'),
    ('"Configuration saved to "', '"配置已保存至 "'),
    ('"Config file not found: "', '"未找到配置文件： "'),

    # File dialog
    ('"Save Configuration As"', '"保存配置为"'),
    ('"Select Configuration"', '"选择配置"'),

    # Server messages
    ('"\\n" + "="*80 + "\\n⏹️ Server stop requested...\\n"',
     '"\\n" + "="*80 + "\\n⏹️ 正在停止服务器...\\n"'),
    ('"⏹️ Server process has terminated.\\n"', '"⏹️ 服务器进程已终止。\\n"'),

    # f-string text parts (preserve f prefix and {var} suffix)
    ('f"Configuration saved to ', 'f"配置已保存至 '),
    ('f"Config file not found: ', 'f"未找到配置文件： '),
    ('f"🌐 Opened browser at ', 'f"🌐 已打开浏览器：'),
    ('f"\\n⚠ Error starting server: ', 'f"\\n⚠ 启动服务器错误：'),
    ('f"\\n⚠ Error stopping server: ', 'f"\\n⚠ 停止服务器错误：'),
    ('f"Failed to save configuration: ', 'f"保存配置失败： '),
    ('f"Failed to load configuration: ', 'f"加载配置失败： '),
    ('f"Failed to open browser: ', 'f"打开浏览器失败： '),

    # Tooltips - model tab
    ('"Path to the GGUF model file."', '"GGUF 模型文件的路径。"'),
    ('"Set an alias for the model (used in API calls)."', '"为模型设置别名（API 调用时使用）。"'),
    ('"Path to a LoRA adapter file (optional)."', '"LoRA 适配器文件的路径（可选）。"'),
    ('"Path to a multimodal projector file (for vision models)."', '"多模态投影器文件的路径（视觉模型用）。"'),
    ('"Select a chat template (leave blank for auto-detection)."', '"选择聊天模板（留空自动检测）。"'),
    ('"Controls whether thought tags are allowed and/or extracted from the response."', '"控制是否允许/提取回复中的思考标签。"'),
    ('"Set reasoning effort for chat template kwargs (some models)."', '"为聊天模板设置推理力度（部分模型支持）。"'),
    ('"Enable Jinja2 templating (required for some custom templates)."', '"启用 Jinja2 模板（某些自定义模板需要）。"'),

    # Tooltips - generation tab
    ('"Number of tokens to generate (default -1 = infinite)."', '"生成的令牌数（默认 -1 = 无限）。"'),
    ('"Prevents model from stopping early."', '"防止模型提前停止。"'),
    ('"Creativity level (default 0.8). Lower = deterministic, higher = creative."', '"创造力级别（默认 0.8）。越低越确定，越高越有创造力。"'),
    ('"Keep only top-k tokens when sampling (default 40)."', '"采样时仅保留 top-k 个令牌（默认 40）。"'),
    ('"Nucleus sampling (default 0.9)."', '"核采样（默认 0.9）。"'),
    ('"Penalizes repetition (default 1.0). Increase to reduce loops."', '"重复惩罚（默认 1.0）。增加以减少重复循环。"'),

    # Tooltips - performance tab
    ('"Context size (sequence length) for the model."', '"模型的上下文大小（序列长度）。"'),
    ('"Number of model layers to offload to GPU (99 for all)."', '"卸载到 GPU 的模型层数（99 = 全部）。"'),
    ('"Number of CPU threads to use (e.g., 8)."', '"使用的 CPU 线程数（例如 8）。"'),
    ('"Batch size for prompt processing (e.g., 2048)."', '"提示处理的批大小（例如 2048）。"'),
    ('"Physical batch size. Lower values reduce VRAM use but slow things down."', '"物理批大小。较低值减少显存占用但降低速度。"'),
    ('"Number of parallel sequences to process (e.g., 4)."', '"并行处理的序列数（例如 4）。"'),
    ('"Enable continuous batching for higher throughput."', '"启用持续批处理以提高吞吐量。"'),

    # Tooltips - advanced tab
    ("\"Set Flash Attention use ('on', 'off', or 'auto', default: 'auto').\"", '"设置 Flash Attention（on/off/auto，默认 auto）。"'),
    ("\"MoE layers to keep on CPU if model doesn't fit on GPU.\"", '"GPU 放不下时保留在 CPU 上的 MoE 层数。"'),
    ('"Lock model in RAM to prevent swapping."', '"将模型锁定在 RAM 中防止交换。"'),
    ('"Disable memory mapping of the model file."', '"禁用模型文件的内存映射。"'),
    ('"Enable NUMA-aware optimizations for specific hardware."', '"启用 NUMA 感知优化（特定硬件）。"'),
    ('"KV cache data type for K (default: f16)."', '"K 的 KV 缓存数据类型（默认 f16）。"'),
    ('"KV cache data type for V (default: f16)."', '"V 的 KV 缓存数据类型（默认 f16）。"'),
    ('"Path to the draft model for speculative decoding."', '"推测解码用的草稿模型路径。"'),
    ('"Number of GPU layers for the draft model."', '"草稿模型的 GPU 层数。"'),
    ('"Number of tokens to draft (e.g., 5)."', '"草稿令牌数（例如 5）。"'),

    # Tooltips - server tab
    ('"IP address to listen on (0.0.0.0 for network access)."', '"监听的 IP 地址（0.0.0.0 允许网络访问）。"'),
    ('"Network port for the server to listen on."', '"服务器监听的网络端口。"'),
    ('"API key for bearer token authentication (optional)."', '"API 密钥，用于令牌认证（可选）。"'),
    ('"Disable the built-in web interface."', '"禁用内置网页界面。"'),
    ('"Enable embedding-only mode (disables chat)."', '"启用仅嵌入模式（禁用聊天功能）。"'),
    ('"Enable verbose server logging for debugging."', '"启用详细服务器日志以便调试。"'),
    ('"Clear all text from the log output window."', '"清除日志输出窗口中的所有文本。"'),

    # Tooltips - custom args
    ('"Double-click to edit this argument."', '"双击编辑此参数。"'),
    ('"Enter a full argument with its value (e.g., --my-flag value) and press Add."', '"输入完整参数及其值（例如 --my-flag value），然后点击添加。"'),

    # File dialog
    ('"Select a {file_ext} file."', '"选择一个 {file_ext} 文件。"'),

    # Server error messages
    ("f\"\\n⚠ Error: 'llama-server' executable not found. Ensure it's in the PATH or same directory.\\n\"",
     '"\\n⚠ 错误：找不到 llama-server 可执行文件，请确保它在 PATH 或同目录下。\\n"'),
    ('"\\n⚠ Error starting server: "', '"\\n⚠ 启动服务器错误："'),
    ('"\\n⚠ Error stopping server: "', '"\\n⚠ 停止服务器错误："'),

    # System tray
    ("item('Show Window'", "item('显示窗口'"),
    ("item('Open Browser'", "item('打开浏览器'"),
    ("item('Quit Application'", "item('退出程序'"),
    ('"LLaMA Server"', '"LLaMA 服务器"'),

    # On-close
    ("app.hide_to_tray()", "app.hide_to_tray()"),  # no-op, just a marker

    # Reasoning effort label update (double-check)
    ("self.reasoning_effort.get()", "self.reasoning_effort.get()"),  # no-op, data not UI
]

# File dialog filetypes - these need special handling because of nested quotes
# (f"{file_ext.upper()} files" -> f"{file_ext.upper()} 文件"
translations.append(
    ('f"{file_ext.upper()} files"', 'f"{file_ext.upper()} 文件"')
)
translations.append(
    ('"All files"', '"所有文件"')
)
translations.append(
    ("'JSON files'", "'JSON 文件'")
)
translations.append(
    ("'All files'", "'所有文件'")
)

# Verify config file not found message
translations.append(
    ('"Failed to save configuration: "', '"保存配置失败： "')
)
translations.append(
    ('"Failed to load configuration: "', '"加载配置失败： "')
)
translations.append(
    ('"Failed to open browser: "', '"打开浏览器失败： "')
)

# Apply all translations
translated = source
found_count = 0
not_found = []
for old, new in translations:
    count = translated.count(old)
    if count > 0:
        translated = translated.replace(old, new)
        found_count += 1
    else:
        not_found.append(old[:70])

# Write
with open(SRC, "w", encoding="utf-8") as f:
    f.write(translated)

print(f"\nApplied: {found_count} translations")
if not_found:
    print(f"Not found ({len(not_found)}):")
    for n in not_found[:10]:
        print(f"  ? {n}")
print(f"\nTranslated file: {SRC}")
