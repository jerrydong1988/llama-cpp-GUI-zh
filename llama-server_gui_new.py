import sys
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.scrolled import ScrolledText, ScrolledFrame
from ttkbootstrap.tooltip import ToolTip
from tkinter import filedialog

import subprocess
import threading
import os
import json
import webbrowser

try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

class LlamaServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LLaMA 服务器管理器")
        self.root.geometry("1080x720")
        self.root.minsize(1080, 720)

        # Server process management
        self.server_process = None
        self.is_running = False

        # System tray setup
        self.tray_icon = None
        self.is_in_tray = False

        # Use user's directory for portable config file
        self.config_file = self.get_config_path("llama_server_config.json")

        # Store slider references for updating on load
        self.slider_refs = {}
        
        # Data store for custom arguments
        self.custom_arguments = []

        self.setup_ui()
        self.load_config()

    def get_config_path(self, filename):
        """Get the path for config file that works with PyInstaller."""
        if getattr(sys, 'frozen', False):
            # Running as compiled executable
            app_dir = os.path.dirname(sys.executable)
        else:
            # Running as script
            app_dir = os.path.dirname(os.path.abspath(__file__))
        
        return os.path.join(app_dir, filename)

    def setup_ui(self):
        """Sets up the main UI layout, including notebook and control buttons."""
        main_container = ttk.Frame(self.root, padding="10")
        main_container.pack(fill=tk.BOTH, expand=True)

        # --- Control Buttons (Packed FIRST and anchored to the BOTTOM) ---
        control_frame = ttk.Frame(main_container)
        control_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))

        # Left-aligned buttons
        left_button_frame = ttk.Frame(control_frame)
        left_button_frame.pack(side=tk.LEFT)
        # Save = Save As (choose name) and Load = Browse and pick a config
        self.create_button(left_button_frame, "另存为 💾", self.save_config, "Save the current settings to a chosen file.", bootstyle="secondary")
        self.create_button(left_button_frame, "加载配置 📂", lambda: self.load_config(browse=True), "Browse and load a saved config.", bootstyle="secondary")
        self.create_button(left_button_frame, "生成命令 ⚡", self.show_command, "Show the final command to be executed.", bootstyle="info")

        # Right-aligned buttons
        right_button_frame = ttk.Frame(control_frame)
        right_button_frame.pack(side=tk.RIGHT)
        self.browser_button = self.create_button(right_button_frame, "打开浏览器 🌐", self.open_browser, "Access the server web UI.", state=tk.DISABLED, bootstyle="primary-outline")
        self.stop_button = self.create_button(right_button_frame, "停止服务器 ⏹️", self.stop_server, "Stop the running server process.", state=tk.DISABLED, bootstyle="danger")
        self.start_button = self.create_button(right_button_frame, "启动服务器 ▶️", self.start_server, "Start the server with current settings.", bootstyle="success")

        # --- Notebook (Packed SECOND to fill the remaining space) ---
        notebook = ttk.Notebook(main_container, bootstyle="primary")
        notebook.pack(fill=tk.BOTH, expand=True)

        # --- Create Tab Frames ---
        model_frame = ttk.Frame(notebook, padding="10")
        generation_frame = ttk.Frame(notebook, padding="10")
        performance_core_frame = ttk.Frame(notebook, padding="10")
        performance_advanced_frame = ttk.Frame(notebook, padding="10")
        server_api_frame = ttk.Frame(notebook, padding="10")
        output_frame = ttk.Frame(notebook, padding="10")

        notebook.add(model_frame, text="  模型  ")
        notebook.add(generation_frame, text="  生成参数  ")
        notebook.add(performance_core_frame, text="  性能  ")
        notebook.add(performance_advanced_frame, text="  高级  ")
        notebook.add(server_api_frame, text="  服务器与API  ")
        notebook.add(output_frame, text="  服务器输出  ")

        # --- Populate Tabs ---
        self.setup_model_tab(model_frame)
        self.setup_generation_tab(generation_frame)
        self.setup_performance_core_tab(performance_core_frame)
        self.setup_performance_advanced_tab(performance_advanced_frame)
        self.setup_server_api_tab(server_api_frame)
        self.setup_output_tab(output_frame)


    # --- Tab Setup Methods ---
    def setup_model_tab(self, parent):
        """Configures the 'Model' tab for model files, extensions, and chat behavior."""
        # --- Primary Model ---
        model_group = ttk.Labelframe(parent, text="主模型", padding="10")
        model_group.pack(fill=tk.X, pady=5)
        self.model_path = tk.StringVar()
        self.create_file_entry(model_group, "模型路径 (-m):", self.model_path, "GGUF 模型文件的路径。", ".gguf", row=0)
        self.alias = tk.StringVar()
        self.create_entry(model_group, "模型别名 (-a):", self.alias, "为模型设置别名（API 调用时使用）。", row=1)

        # --- Model Extensions ---
        ext_group = ttk.Labelframe(parent, text="模型扩展", padding="10")
        ext_group.pack(fill=tk.X, pady=5)
        self.lora_path = tk.StringVar()
        self.create_file_entry(ext_group, "LoRA 路径 (--lora):", self.lora_path, "LoRA 适配器文件的路径（可选）。", ".gguf", row=0)
        self.mmproj_path = tk.StringVar()
        self.create_file_entry(ext_group, "多模态投影器 (--mmproj):", self.mmproj_path, "多模态投影器文件的路径（视觉模型用）。", ".gguf", row=1)
        # --- HuggingFace Auto Download ---
        hf_group = ttk.Labelframe(parent, text="HuggingFace 自动下载", padding="10")
        hf_group.pack(fill=tk.X, pady=5)
        self.hf_repo = tk.StringVar()
        self.create_entry(hf_group, "HF 仓库 (--hf-repo):", self.hf_repo, "HuggingFace 模型仓库，例如 ggml-org/gemma-3-1b-it-GGUF:Q4_K_M，设置后自动下载。", row=0)
        self.hf_file = tk.StringVar()
        self.create_entry(hf_group, "HF 文件 (--hf-file):", self.hf_file, "指定仓库中的具体文件名（可选，覆盖 --hf-repo 中的量化级别）。", row=1)


        # --- Chat Behavior ---
        chat_group = ttk.Labelframe(parent, text="对话行为", padding="10")
        chat_group.pack(fill=tk.X, pady=5)
        self.chat_template = tk.StringVar()
        chat_templates = ["", "bailing", "chatglm3", "chatglm4", "chatml", "command-r", "deepseek", "deepseek2", "deepseek3", "exaone3", "gemma", "gpt-oss", "kimi-k2", "llama2", "llama3", "llama4", "mistral", "openchat", "phi3", "phi4", "vicuna", "zephyr"]
        self.create_combobox(chat_group, "聊天模板 (--chat-template):", self.chat_template, "选择聊天模板（留空自动检测）。", chat_templates, row=0)

        self.reasoning_format = tk.StringVar()
        reasoning_formats = ["", "auto", "none", "deepseek"]
        self.create_combobox(chat_group, "推理格式 (--reasoning-format):", self.reasoning_format, "控制是否允许/提取回复中的思考标签。", reasoning_formats, row=1)

        self.reasoning_effort = tk.StringVar()
        reasoning_levels = ["", "low", "medium", "high"]
        self.create_combobox(chat_group, "推理力度:", self.reasoning_effort, "为聊天模板设置推理力度（部分模型支持）。", reasoning_levels, row=2)
        
        self.reasoning = tk.StringVar()
        reasoning_options = ["", "on", "off", "auto"]
        self.create_combobox(chat_group, "推理开关 (--reasoning):", self.reasoning, "启用/禁用/自动推理（思考）功能。MTP 模型建议设为 off。", reasoning_options, row=3)
        self.jinja = tk.BooleanVar(value=False)
        self.create_checkbutton(chat_group, "启用 Jinja (--jinja)", self.jinja, "启用 Jinja2 模板（某些自定义模板需要）。", row=4)

    def setup_generation_tab(self, parent):
        """Configures the 'Generation' tab for sampling and output control."""
        # --- Output Control ---
        output_group = ttk.Labelframe(parent, text="输出控制", padding="10")
        output_group.pack(fill=tk.X, pady=5, side=tk.TOP)
        
        self.n_predict = tk.StringVar(value="")
        self.create_spinbox(output_group, "生成令牌数 (-n, --n-predict):", self.n_predict, "生成的令牌数（默认 -1 = 无限）。", from_=-1, to=131072, increment=1, row=0)
        
        self.ignore_eos = tk.BooleanVar(value=False)
        self.create_checkbutton(output_group, "忽略结束标记 (--ignore-eos)", self.ignore_eos, "防止模型提前停止。", row=1)
        
        # --- Sampling Parameters ---
        sampling_group = ttk.Labelframe(parent, text="采样参数", padding="10")
        sampling_group.pack(fill=tk.X, pady=5)
        
        self.temp = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "温度 (--temp):", self.temp, "创造力级别（默认 0.8）。越低越确定，越高越有创造力。", from_=0, to=2, increment=0.1, row=0)

        self.top_k = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "Top-K (--top-k):", self.top_k, "采样时仅保留 top-k 个令牌（默认 40）。", from_=0, to=1000, increment=1, row=1)
        
        self.top_p = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "Top-P (--top-p):", self.top_p, "核采样（默认 0.9）。", from_=0, to=1, increment=0.1, row=2)

        self.repeat_penalty = tk.StringVar(value="")
        self.create_spinbox(sampling_group, "重复惩罚 (--repeat-penalty):", self.repeat_penalty, "重复惩罚（默认 1.0）。增加以减少重复循环。", from_=0, to=2, increment=0.1, row=3)
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


    def setup_performance_core_tab(self, parent):
        """Configures the 'Performance' tab for core speed and throughput settings."""
        # --- Core Performance ---
        core_group = ttk.Labelframe(parent, text="核心性能", padding="10")
        core_group.pack(fill=tk.X, pady=5, side=tk.TOP)
        self.ctx_size = tk.IntVar(value=4096)
        self.create_slider(core_group, "上下文大小 (-c):", self.ctx_size, "模型的上下文大小（序列长度）。", from_=0, to=131072, resolution=1024, row=0)
        self.ctx_size_auto = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(core_group, text="自动上下文 (--ctx-size 0)", variable=self.ctx_size_auto, bootstyle="round-toggle")
        cb.grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ToolTip(cb, "勾选后不传 -c 参数，llama-server 自动使用模型完整上下文长度。")

        self.gpu_layers = tk.IntVar(value=99)
        self.create_slider(core_group, "GPU 层数 (-ngl):", self.gpu_layers, "卸载到 GPU 的模型层数（99 = 全部）。", from_=0, to=99, resolution=1, row=1)
        self.threads = tk.StringVar(value="")
        self.create_spinbox(core_group, "CPU 线程数 (-t):", self.threads, "使用的 CPU 线程数（例如 8）。", from_=1, to=128, increment=1, row=2)
        self.batch_size = tk.StringVar(value="")
        self.create_spinbox(core_group, "批大小 (-b):", self.batch_size, "提示处理的批大小（例如 2048）。", from_=1, to=8192, increment=1, row=3)
        self.ubatch_size = tk.StringVar(value="")
        self.create_spinbox(core_group, "物理批大小 (-ub):", self.ubatch_size, "物理批大小。较低值减少显存占用但降低速度。", from_=1, to=1024, increment=1, row=4)

        # --- Advanced Throughput ---
        throughput_group = ttk.Labelframe(parent, text="高级吞吐量", padding="10")
        throughput_group.pack(fill=tk.X, pady=5)
        self.parallel = tk.StringVar(value="")
        self.create_spinbox(throughput_group, "并行序列数 (-np):", self.parallel, "并行处理的序列数（例如 4）。", row=0, from_=1, to=16, increment=1)
        self.cont_batching = tk.BooleanVar(value=False)
        self.create_checkbutton(throughput_group, "持续批处理 (-cb)", self.cont_batching, "启用持续批处理以提高吞吐量。", row=1)
        self.cache_prompt = tk.BooleanVar(value=True)
        self.create_checkbutton(throughput_group, "提示缓存 (--cache-prompt)", self.cache_prompt, "启用提示缓存以提高重复请求的速度（默认启用）。", row=2)
        self.threads_batch = tk.StringVar(value="")
        self.create_spinbox(core_group, "批处理线程 (-tb, --threads-batch):", self.threads_batch, "提示处理和批处理时使用的线程数（默认同 --threads）。", from_=1, to=128, increment=1, row=5)

    def setup_performance_advanced_tab(self, parent):
        """Configures the 'Advanced' tab for memory, optimizations, and speculative decoding."""
        # --- Memory & Optimizations ---
        mem_group = ttk.Labelframe(parent, text="内存与优化", padding="10")
        mem_group.pack(fill=tk.X, pady=5)
        self.flash_attn = tk.StringVar(value="auto")
        flash_attn_options = ["on", "off", "auto"]
        self.create_combobox(mem_group, "Flash Attention (-fa):", self.flash_attn, "设置 Flash Attention（on/off/auto，默认 auto）。", flash_attn_options, row=0)
        self.moe_cpu_layers = tk.StringVar(value="")
        self.create_spinbox(mem_group, "MoE CPU 层数 (--n-cpu-moe):", self.moe_cpu_layers, "GPU 放不下时保留在 CPU 上的 MoE 层数。", row=1, from_=0, to=99, increment=1)
        self.mlock = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "内存锁定 (--mlock)", self.mlock, "将模型锁定在 RAM 中防止交换。", row=2)
        self.no_mmap = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "禁用内存映射 (--no-mmap)", self.no_mmap, "禁用模型文件的内存映射。", row=3)
        self.numa = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "NUMA 优化 (--numa)", self.numa, "启用 NUMA 感知优化（特定硬件）。", row=4)
        # --- Cache Type for Draft K/V (moved here from Speculative Decoding)
        cache_types = ["", "f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"]
        self.cache_type_k = tk.StringVar(value="")
        self.create_combobox(mem_group, "K 缓存类型 (-ctk):", self.cache_type_k, "K 的 KV 缓存数据类型（默认 f16）。", cache_types, row=5)
        self.cache_type_v = tk.StringVar(value="")
        self.create_combobox(mem_group, "V 缓存类型 (-ctv):", self.cache_type_v, "V 的 KV 缓存数据类型（默认 f16）。", cache_types, row=6)

        # --- Speculative Decoding ---
        spec_group = ttk.Labelframe(parent, text="推测解码", padding="10")
        spec_group.pack(fill=tk.X, pady=5)
        self.draft_model_path = tk.StringVar()
        self.create_file_entry(spec_group, "草稿模型 (-md):", self.draft_model_path, "推测解码用的草稿模型路径。", ".gguf", row=0)
        self.draft_gpu_layers = tk.StringVar(value="")
        self.create_spinbox(spec_group, "草稿 GPU 层数 (-ngld):", self.draft_gpu_layers, "草稿模型的 GPU 层数。", row=1, from_=0, to=99, increment=1)
        self.draft_tokens = tk.StringVar(value="")
        self.create_spinbox(spec_group, "草稿令牌上限 (--spec-draft-n-max):", self.draft_tokens, "推测解码最大草稿令牌数（默认 16）。--draft 已废弃，改用此参数。", row=2, from_=1, to=1024, increment=1)
        self.spec_draft_n_min = tk.StringVar(value="")
        self.create_spinbox(spec_group, "最小草稿令牌数 (--spec-draft-n-min):", self.spec_draft_n_min, "推测解码最小草稿令牌数（默认 0）。", row=3, from_=0, to=512, increment=1)
        self.spec_type = tk.StringVar()
        spec_types = ["", "none", "mtp", "ngram-cache", "ngram-simple", "ngram-map-k", "ngram-map-k4v", "ngram-mod", "draft-simple", "draft-eagle3", "draft-mtp"]
        self.create_combobox(spec_group, "推测解码类型 (--spec-type):", self.spec_type, "推测解码类型。无草稿模型时（模型自带MTP头）可选：mtp / ngram-cache / ngram-mod 等；有草稿模型时（-md 指定）可选：draft-simple / draft-eagle3 / draft-mtp。可组合多个，用逗号分隔。", spec_types, row=4)
        self.draft_hf_repo = tk.StringVar()
        self.create_entry(spec_group, "草稿 HF 仓库 (--hf-repo-draft):", self.draft_hf_repo, "草稿模型的 HuggingFace 仓库，例如 ggml-org/Qwen2.5-0.5B-GGUF:Q4_K_M，设置后自动下载。", row=5)

        # --- Server Reliability ---
        server_rel_group = ttk.Labelframe(parent, text="服务器可靠性", padding="10")
        server_rel_group.pack(fill=tk.X, pady=5)
        self.timeout = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "超时秒数 (--timeout):", self.timeout, "服务器读写超时秒数（默认 600）。", from_=1, to=3600, increment=10, row=0)
        self.sleep_idle = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "空闲休眠秒数 (--sleep-idle-seconds):", self.sleep_idle, "空闲 N 秒后自动卸载模型释放显存（默认 -1 = 禁用）。", from_=-1, to=86400, increment=60, row=1)

        

    def setup_server_api_tab(self, parent):
        """Configures the 'Server & API' tab for network, access, and logging."""
        parent.rowconfigure(2, weight=1) # Allow custom args group to expand
        parent.columnconfigure(0, weight=1)
        
        # --- Network Configuration ---
        net_group = ttk.Labelframe(parent, text="网络配置", padding="10")
        net_group.grid(row=0, column=0, sticky=EW, pady=5)
        net_group.columnconfigure(1, weight=1)
        self.host = tk.StringVar(value="127.0.0.1")
        self.create_entry(net_group, "主机 (--host):", self.host, "监听的 IP 地址（0.0.0.0 允许网络访问）。", row=0)
        self.port = tk.StringVar(value="8080")
        self.create_entry(net_group, "端口 (--port):", self.port, "服务器监听的网络端口。", row=1)

        # --- Access & Features ---
        access_group = ttk.Labelframe(parent, text="访问与功能", padding="10")
        access_group.grid(row=1, column=0, sticky=EW, pady=5)
        access_group.columnconfigure(1, weight=1)
        self.api_key = tk.StringVar()
        self.create_entry(access_group, "API 密钥 (--api-key):", self.api_key, "API 密钥，用于令牌认证（可选）。", row=0)
        self.no_webui = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "禁用网页界面 (--no-webui)", self.no_webui, "禁用内置网页界面。", row=1)
        self.embedding = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "仅嵌入模式 (--embedding)", self.embedding, "启用仅嵌入模式（禁用聊天功能）。", row=2)
        self.pooling = tk.StringVar()
        pooling_options = ["", "none", "mean", "cls", "last", "rank"]
        self.create_combobox(access_group, "嵌入池化 (--pooling):", self.pooling, "嵌入模型的池化类型（使用嵌入模式时需设置）。", pooling_options, row=3)
        self.reranking = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "重排序端点 (--reranking)", self.reranking, "启用重排序端点（RAG 场景）。", row=4)


        # --- Custom Arguments Management ---
        custom_group = ttk.Labelframe(parent, text="自定义参数管理", padding="10")
        custom_group.grid(row=2, column=0, sticky=NSEW, pady=5)
        custom_group.columnconfigure(0, weight=1)
        custom_group.rowconfigure(1, weight=1)

        # Input for new argument
        add_arg_frame = ttk.Frame(custom_group)
        add_arg_frame.grid(row=0, column=0, sticky=EW, pady=(0, 10))
        add_arg_frame.columnconfigure(0, weight=1)
        self.new_arg_entry = ttk.Entry(add_arg_frame)
        self.new_arg_entry.grid(row=0, column=0, sticky=EW, padx=(0, 5))
        ToolTip(self.new_arg_entry, "输入完整参数及其值（例如 --my-flag value），然后点击添加。")
        add_button = ttk.Button(add_arg_frame, text="添加", command=self.add_custom_argument, bootstyle="success-outline")
        add_button.grid(row=0, column=1, sticky=E)

        # Scrollable list for existing arguments
        self.custom_args_list_frame = ScrolledFrame(custom_group, autohide=True, bootstyle="round")
        self.custom_args_list_frame.grid(row=1, column=0, sticky=NSEW)
        
        # Other options below the list
        other_options_frame = ttk.Frame(custom_group)
        other_options_frame.grid(row=2, column=0, sticky=EW, pady=(10, 0))
        self.verbose = tk.BooleanVar(value=False)
        verbose_cb = ttk.Checkbutton(other_options_frame, text="详细日志 (-v)", variable=self.verbose, bootstyle="round-toggle")
        verbose_cb.pack(side=tk.LEFT)
        ToolTip(verbose_cb, "启用详细服务器日志以便调试。")
        
    def setup_output_tab(self, parent):
        """Sets up the server output log view."""
        ttk.Label(parent, text="服务器日志输出：").pack(anchor=tk.W, pady=(0, 5))
        monospace_font = ("Consolas", 10)
        self.output_text = ScrolledText(parent, height=20, wrap=tk.WORD, font=monospace_font, autohide=True)
        self.output_text.pack(fill=tk.BOTH, expand=True)
        clear_btn = ttk.Button(parent, text="清空输出", command=self.clear_output, bootstyle="secondary-outline")
        clear_btn.pack(pady=(10, 0), anchor=tk.E)
        ToolTip(clear_btn, "清除日志输出窗口中的所有文本。")

    # --- UI Helper Methods ---
    def create_file_entry(self, parent, label_text, string_var, tooltip_text, file_ext, row):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        file_path_frame = ttk.Frame(parent)
        file_path_frame.grid(row=row, column=1, sticky=tk.EW, pady=5)
        parent.columnconfigure(1, weight=1)
        entry = ttk.Entry(file_path_frame, textvariable=string_var)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        browse_btn = ttk.Button(file_path_frame, text="浏览", command=lambda: self.browse_file(string_var, file_ext), bootstyle="primary")
        browse_btn.pack(side=tk.RIGHT)
        ToolTip(label, text=tooltip_text)
        ToolTip(entry, text=tooltip_text)
        ToolTip(browse_btn, text=f"选择一个 {file_ext} 文件。")

    def create_entry(self, parent, label_text, string_var, tooltip_text, row):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        entry = ttk.Entry(parent, textvariable=string_var, width=30)
        entry.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        parent.columnconfigure(1, weight=1)
        ToolTip(label, text=tooltip_text)
        ToolTip(entry, text=tooltip_text)
    
    def create_spinbox(self, parent, label_text, variable, tooltip_text, from_, to, increment, row):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)

        spin = ttk.Spinbox(
            parent, 
            textvariable=variable,
            from_=from_, 
            to=to, 
            increment=increment,
            width=10,
            bootstyle="primary"
        )
        spin.grid(row=row, column=1, sticky=tk.W, padx=5, pady=5)

        ToolTip(label, text=tooltip_text)
        ToolTip(spin, text=tooltip_text)
        return spin

    def create_combobox(self, parent, label_text, string_var, tooltip_text, values, row):
        label = ttk.Label(parent, text=label_text)
        label.grid(row=row, column=0, sticky=tk.W, padx=5, pady=5)
        combobox = ttk.Combobox(parent, textvariable=string_var, values=values)
        combobox.grid(row=row, column=1, sticky=tk.EW, padx=5, pady=5)
        parent.columnconfigure(1, weight=1)
        ToolTip(label, text=tooltip_text)
        ToolTip(combobox, text=tooltip_text)
        
    def create_slider(self, parent, label_text, int_var, tooltip_text, from_, to, resolution, row):
        slider_frame = ttk.Frame(parent)
        slider_frame.grid(row=row, column=0, columnspan=2, sticky=tk.EW, padx=5, pady=5)
        parent.columnconfigure(1, weight=1)
        label = ttk.Label(slider_frame, text=label_text)
        label.pack(anchor=tk.W)
        ToolTip(label, text=tooltip_text)
        control_frame = ttk.Frame(slider_frame)
        control_frame.pack(fill=tk.X, pady=(2, 0))
        slider = ttk.Scale(control_frame, from_=from_, to=to, orient=tk.HORIZONTAL,
                           variable=int_var, command=lambda v: self.update_slider_label(int_var, value_label, resolution), bootstyle="primary")
        slider.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 10))
        ToolTip(slider, text=tooltip_text)
        value_label = ttk.Label(control_frame, text=str(int_var.get()), width=8, anchor=tk.CENTER)
        value_label.pack(side=tk.RIGHT)
        
        slider_key = f"{label_text}_{id(int_var)}"
        self.slider_refs[slider_key] = {'var': int_var, 'slider': slider, 'label': value_label, 'resolution': resolution}
        self.update_slider_label(int_var, value_label, resolution)

    def update_slider_label(self, int_var, label, resolution):
        raw_value = int_var.get()
        rounded_value = round(raw_value / resolution) * resolution
        int_var.set(rounded_value)
        label.config(text=str(rounded_value))

    def update_all_sliders(self):
        for key, refs in self.slider_refs.items():
            refs['slider'].set(refs['var'].get())
            self.update_slider_label(refs['var'], refs['label'], refs['resolution'])

    def create_checkbutton(self, parent, text, variable, tooltip_text, row):
        cb = ttk.Checkbutton(parent, text=text, variable=variable, bootstyle="round-toggle")
        cb.grid(row=row, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        ToolTip(cb, text=tooltip_text)

    def create_button(self, parent, text, command, tooltip_text, state=tk.NORMAL, bootstyle="primary"):
        btn = ttk.Button(parent, text=text, command=command, state=state, bootstyle=bootstyle)
        btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(btn, text=tooltip_text)
        return btn

    # --- Custom Argument Methods ---
    def add_custom_argument(self):
        arg_text = self.new_arg_entry.get().strip()
        if not arg_text:
            return
        if any(arg['value'] == arg_text for arg in self.custom_arguments):
            Messagebox.show_warning("该参数已存在于列表中。", "重复参数")
            return
            
        self.custom_arguments.append({"value": arg_text, "enabled": True})
        self.new_arg_entry.delete(0, tk.END)
        self.rebuild_custom_args_list()

    def delete_custom_argument(self, arg_to_delete):
        self.custom_arguments.remove(arg_to_delete)
        self.rebuild_custom_args_list()
        
    def rebuild_custom_args_list(self):
        for widget in self.custom_args_list_frame.winfo_children():
            widget.destroy()

        for arg_item in self.custom_arguments:
            row_frame = ttk.Frame(self.custom_args_list_frame, padding=(5, 3))
            row_frame.pack(fill=X, expand=True, padx=(0, 5)) 

            is_enabled_var = tk.BooleanVar(value=arg_item.get("enabled", True))
            
            def on_toggle(item=arg_item, var=is_enabled_var):
                item["enabled"] = var.get()

            toggle = ttk.Checkbutton(row_frame, variable=is_enabled_var, bootstyle="round-toggle", command=on_toggle)
            toggle.pack(side=LEFT, padx=(0, 10))

            label = ttk.Label(row_frame, text=arg_item["value"])
            delete_btn = ttk.Button(row_frame, text="删除", bootstyle="danger-link", command=lambda item=arg_item: self.delete_custom_argument(item))
            
            # Pack order matters: label is packed after edit logic is set up.
            delete_btn.pack(side=RIGHT, padx=(10, 0))
            
            ### ADDED ### Logic for double-click-to-edit
            def start_edit(event, item, lbl, frame, del_btn):
                lbl.pack_forget() # Hide the label

                entry_var = tk.StringVar(value=item["value"])
                edit_entry = ttk.Entry(frame, textvariable=entry_var)
                edit_entry.pack(side=LEFT, fill=X, expand=True, before=del_btn)
                edit_entry.focus_set()
                edit_entry.selection_range(0, tk.END)

                def save_edit(event):
                    new_value = entry_var.get().strip()
                    if new_value:
                        item["value"] = new_value
                        lbl.config(text=new_value)
                    
                    edit_entry.destroy()
                    lbl.pack(side=LEFT, fill=X, expand=True, before=del_btn) # Show the label again

                edit_entry.bind("<Return>", save_edit)
                edit_entry.bind("<FocusOut>", save_edit)

            label.bind("<Double-1>", lambda e, item=arg_item, lbl=label, frame=row_frame, btn=delete_btn: start_edit(e, item, lbl, frame, btn))
            ToolTip(label, "双击编辑此参数。")
            label.pack(side=LEFT, fill=X, expand=True, anchor=W)


    # --- Core Functionality ---
    def browse_file(self, string_var, file_ext):
        filename = filedialog.askopenfilename(
            title=f"Select {file_ext} File",
            filetypes=[(f"{file_ext.upper()} 文件", f"*{file_ext}"), ("所有文件", "*.*")]
        )
        if filename:
            string_var.set(filename)

    def generate_command(self):
        if not self.model_path.get().strip():
            Messagebox.show_error("请选择模型路径！", "错误")
            return None
        
        cmd = ["llama-server", "-m", self.model_path.get().strip()]
        if not self.ctx_size_auto.get():
            cmd.extend(['-c', str(self.ctx_size.get())])
        cmd.extend(['-ngl', str(self.gpu_layers.get())])
        
        args = {
            '--host': self.host, '--port': self.port, '-a': self.alias,
            '--api-key': self.api_key, '-t': self.threads, '-b': self.batch_size, 
            '-np': self.parallel, '--lora': self.lora_path,
            '--mmproj': self.mmproj_path, '--chat-template': self.chat_template,
            '-md': self.draft_model_path, '-ngld': self.draft_gpu_layers,
            '--spec-draft-n-max': self.draft_tokens,
            '--spec-draft-n-min': self.spec_draft_n_min,
            '--spec-type': self.spec_type,
            '--reasoning': self.reasoning,
            '--hf-repo-draft': self.draft_hf_repo, '--n-cpu-moe': self.moe_cpu_layers,
            '--reasoning-format': self.reasoning_format, '-ub': self.ubatch_size,
            '-n': self.n_predict, '--temp': self.temp, '--top-k': self.top_k,
            '--top-p': self.top_p, '--repeat-penalty': self.repeat_penalty,
            '--pooling': self.pooling,
            '--sleep-idle-seconds': self.sleep_idle,
            '-to': self.timeout,
            '--tb': self.threads_batch,
            '--repeat-last-n': self.repeat_last_n,
            '--frequency-penalty': self.frequency_penalty,
            '--presence-penalty': self.presence_penalty,
            '--min-p': self.min_p,
            '--seed': self.seed,
            '--hf-file': self.hf_file,
            '--hf-repo': self.hf_repo,
            '--cache-type-k': self.cache_type_k, '--cache-type-v': self.cache_type_v
        }
        for flag, var in args.items():
            if var.get().strip():
                cmd.extend([flag, var.get().strip()])
        
        if self.reasoning_effort.get().strip():
            kwargs_json = json.dumps({"reasoning_effort": self.reasoning_effort.get()})
            cmd.extend(['--chat-template-kwargs', kwargs_json])
        
        # Handle flash attention as a special case since it needs a value
        if self.flash_attn.get().strip() and self.flash_attn.get().strip() != "auto":
            cmd.extend(['-fa', self.flash_attn.get().strip()])
        
        bool_args = {
            '--no-mmap': self.no_mmap,
            '--no-webui': self.no_webui, '-cb': self.cont_batching,
            '--mlock': self.mlock, '--embedding': self.embedding,
            '--jinja': self.jinja, '-v': self.verbose,
            '--reranking': self.reranking,
            '--ignore-eos': self.ignore_eos
        }
        for flag, var in bool_args.items():
            if var.get():
                cmd.append(flag)

        # Inverted logic: cache prompt is enabled by default, unchecked = --no-cache-prompt
        if not self.cache_prompt.get():
            cmd.append("--no-cache-prompt")

        if self.numa.get():
            cmd.extend(["--numa", "distribute"])
            
        # Add enabled custom arguments from the list
        for arg_item in self.custom_arguments:
            if arg_item.get("enabled", False) and arg_item.get("value", "").strip():
                cmd.extend(arg_item["value"].strip().split())
            
        return cmd

    def show_command(self):
        cmd = self.generate_command()
        if not cmd: return
        command_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
        cmd_window = ttk.Toplevel(self.root)
        cmd_window.title("生成的命令")
        cmd_window.geometry("1200x300")
        ttk.Label(cmd_window, text="生成的命令：", padding="10 10 0 5").pack(anchor=tk.W)
        cmd_text = ScrolledText(cmd_window, height=5, wrap=tk.WORD, autohide=True)
        cmd_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        cmd_text.insert(tk.END, command_str)
        cmd_text.text.configure(state=tk.DISABLED)
        
        def copy_command():
            cmd_window.clipboard_clear()
            cmd_window.clipboard_append(command_str)
            Messagebox.ok("命令已复制到剪贴板！", "已复制", parent=cmd_window)
        ttk.Button(cmd_window, text="复制到剪贴板", command=copy_command).pack(pady=10)

    def start_server(self):
        if self.is_running: return
        cmd = self.generate_command()
        if not cmd: return
            
        self.output_text.delete(1.0, tk.END)
        command_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
        self.update_output(f"▶ Starting server with command:\n{command_str}\n\n" + "="*80 + "\n")
        
        def run_server():
            try:
                startupinfo = None
                if os.name == 'nt':
                    startupinfo = subprocess.STARTUPINFO()
                    startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW

                self.server_process = subprocess.Popen(
                    cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    universal_newlines=False, bufsize=1, startupinfo=startupinfo
                )
                
                for line_bytes in iter(self.server_process.stdout.readline, b''):
                    try:
                        line = line_bytes.decode('utf-8')
                    except UnicodeDecodeError:
                        line = line_bytes.decode('latin-1', errors='replace')
                    self.root.after(0, self.update_output, line)
                self.server_process.wait()
                self.root.after(0, self.server_stopped)
                
            except FileNotFoundError:
                self.root.after(0, self.update_output, "\n⚠ 错误：找不到 llama-server 可执行文件，请确保它在 PATH 或同目录下。\n")
                self.root.after(0, self.server_stopped)
            except Exception as e:
                self.root.after(0, self.update_output, f"\n⚠ 启动服务器错误：{e}\n")
                self.root.after(0, self.server_stopped)
        
        threading.Thread(target=run_server, daemon=True).start()
        
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.browser_button.config(state=tk.NORMAL)

    def stop_server(self):
        if self.server_process and self.is_running:
            try:
                self.server_process.terminate()
                self.update_output("\n" + "="*80 + "\n⏹️ 正在停止服务器...\n")
            except Exception as e:
                self.update_output(f"\n⚠ 停止服务器错误：{e}\n")

    def server_stopped(self):
        self.is_running = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.browser_button.config(state=tk.DISABLED)
        self.update_output("⏹️ 服务器进程已终止。\n")

    def update_output(self, text):
        self.output_text.insert(tk.END, text)
        self.output_text.see(tk.END)

    def clear_output(self):
        self.output_text.delete(1.0, tk.END)

    def save_config(self, path=None):
        """Save the current configuration.

        If path is None, show a Save As dialog to choose a filename. The file will be
        saved inside a 'configs' directory next to the script (created if missing), and
        will be given a .json extension if omitted. After saving, update self.config_file.
        """
        config = {
            'model_path': self.model_path.get(), 'alias': self.alias.get(),
            'lora_path': self.lora_path.get(), 'mmproj_path': self.mmproj_path.get(),
            'chat_template': self.chat_template.get(), 'reasoning_effort': self.reasoning_effort.get(),
            'jinja': self.jinja.get(), 'ctx_size': self.ctx_size.get(),
            'gpu_layers': self.gpu_layers.get(), 'threads': self.threads.get(),
            'batch_size': self.batch_size.get(), 'cont_batching': self.cont_batching.get(),
            'parallel': self.parallel.get(), 'flash_attn': self.flash_attn.get(),
            'mlock': self.mlock.get(), 'no_mmap': self.no_mmap.get(), 'numa': self.numa.get(),
            'moe_cpu_layers': self.moe_cpu_layers.get(), 'draft_model_path': self.draft_model_path.get(),
            'draft_gpu_layers': self.draft_gpu_layers.get(), 'draft_tokens': self.draft_tokens.get(),
            'host': self.host.get(), 'port': self.port.get(), 'api_key': self.api_key.get(),
            'no_webui': self.no_webui.get(), 'embedding': self.embedding.get(),
            'verbose': self.verbose.get(), 'custom_arguments_list': self.custom_arguments,
            'reasoning_format': self.reasoning_format.get(), 'ubatch_size': self.ubatch_size.get(),
            'n_predict': self.n_predict.get(), 'ignore_eos': self.ignore_eos.get(),
            'temp': self.temp.get(), 'top_k': self.top_k.get(), 'top_p': self.top_p.get(),
            'repeat_penalty': self.repeat_penalty.get(),
            'pooling': self.pooling.get(), 'reranking': self.reranking.get(),
            'timeout': self.timeout.get(), 'sleep_idle': self.sleep_idle.get(),
            'cache_prompt': self.cache_prompt.get(),
            'threads_batch': self.threads_batch.get(),
            'repeat_last_n': self.repeat_last_n.get(),
            'presence_penalty': self.presence_penalty.get(), 'frequency_penalty': self.frequency_penalty.get(),
            'seed': self.seed.get(), 'min_p': self.min_p.get(),
            'ctx_size_auto': self.ctx_size_auto.get(),
            'reasoning': self.reasoning.get(),
            'hf_repo': self.hf_repo.get(), 'hf_file': self.hf_file.get(),
            'cache_type_k': self.cache_type_k.get(), 'cache_type_v': self.cache_type_v.get()
        }
        try:
            # Determine where to save: prefer provided path, otherwise show Save As dialog
            if path is None:
                # Ensure configs directory exists next to the executable/script
                app_dir = os.path.dirname(self.get_config_path(''))
                configs_dir = os.path.join(app_dir, 'configs')
                os.makedirs(configs_dir, exist_ok=True)

                save_path = filedialog.asksaveasfilename(
                    title="保存配置为",
                    defaultextension='.json',
                    filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')],
                    initialdir=configs_dir,
                    initialfile='config-'
                )
                if not save_path:
                    return
            else:
                save_path = path

            # Ensure .json extension
            if not save_path.lower().endswith('.json'):
                save_path = save_path + '.json'

            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=4)

            # Update current config file pointer
            self.config_file = save_path
            Messagebox.ok(f"配置已保存至 {save_path}", "成功")
        except Exception as e:
            Messagebox.show_error(f"保存配置失败： {e}", "错误")

    def load_config(self, path=None, browse=False):
        """Load configuration.

        If browse=True or path is provided, open a file dialog (or load provided path).
        If neither is provided, load from self.config_file (used on startup).
        """
        load_path = None
        # If user requested browsing, show open dialog populated from configs dir
        if browse:
            app_dir = os.path.dirname(self.get_config_path(''))
            configs_dir = os.path.join(app_dir, 'configs')
            os.makedirs(configs_dir, exist_ok=True)
            chosen = filedialog.askopenfilename(
                title="选择配置",
                filetypes=[('JSON 文件', '*.json'), ('所有文件', '*.*')],
                initialdir=configs_dir
            )
            if not chosen:
                return
            load_path = chosen
        elif path:
            load_path = path
        else:
            load_path = self.config_file

        if not os.path.exists(load_path):
            # If the user explicitly asked to browse or provided a path, warn them.
            # If this is the startup default (neither browse nor path provided),
            # silently return so the UI keeps its default values.
            if browse or path:
                Messagebox.show_warning(f"未找到配置文件： {load_path}", "未找到")
            return

        try:
            with open(load_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            # Load values, providing defaults for missing keys
            self.model_path.set(config.get('model_path', ''))
            self.alias.set(config.get('alias', ''))
            self.lora_path.set(config.get('lora_path', ''))
            self.mmproj_path.set(config.get('mmproj_path', ''))
            self.chat_template.set(config.get('chat_template', ''))
            self.reasoning_effort.set(config.get('reasoning_effort', ''))
            self.jinja.set(config.get('jinja', False))
            self.ctx_size.set(config.get('ctx_size', 4096))
            self.gpu_layers.set(config.get('gpu_layers', 99))
            self.threads.set(config.get('threads', ''))
            self.batch_size.set(config.get('batch_size', ''))
            self.cont_batching.set(config.get('cont_batching', False))
            self.parallel.set(config.get('parallel', ''))
            self.flash_attn.set(config.get('flash_attn', False))
            self.mlock.set(config.get('mlock', False))
            self.no_mmap.set(config.get('no_mmap', False))
            self.numa.set(config.get('numa', False))
            self.moe_cpu_layers.set(config.get('moe_cpu_layers', ''))
            self.draft_model_path.set(config.get('draft_model_path', ''))
            self.draft_gpu_layers.set(config.get('draft_gpu_layers', ''))
            self.draft_tokens.set(config.get('draft_tokens', ''))
            self.host.set(config.get('host', '127.0.0.1'))
            self.port.set(config.get('port', '8080'))
            self.api_key.set(config.get('api_key', ''))
            self.no_webui.set(config.get('no_webui', False))
            self.embedding.set(config.get('embedding', False))
            self.verbose.set(config.get('verbose', False))

            # Load new custom arguments list
            self.custom_arguments = config.get('custom_arguments_list', [])
            # Backward compatibility for old 'custom_args' string
            if not self.custom_arguments and 'custom_args' in config:
                old_args_str = config['custom_args'].strip()
                if old_args_str:
                    self.custom_arguments.append({"value": old_args_str, "enabled": True})
            self.rebuild_custom_args_list()

            self.reasoning_format.set(config.get('reasoning_format', ''))
            self.ubatch_size.set(config.get('ubatch_size', ''))
            self.n_predict.set(config.get('n_predict', ''))
            self.ignore_eos.set(config.get('ignore_eos', False))
            self.temp.set(config.get('temp', ''))
            self.top_k.set(config.get('top_k', ''))
            self.top_p.set(config.get('top_p', ''))
            self.repeat_penalty.set(config.get('repeat_penalty', ''))
            self.cache_prompt.set(config.get('cache_prompt', True))
            self.ctx_size_auto.set(config.get('ctx_size_auto', False))
            self.reasoning.set(config.get('reasoning', ''))
            self.reranking.set(config.get('reranking', False))
            self.pooling.set(config.get('pooling', ''))
            self.sleep_idle.set(config.get('sleep_idle', ''))
            self.timeout.set(config.get('timeout', ''))
            self.threads_batch.set(config.get('threads_batch', ''))
            self.hf_file.set(config.get('hf_file', ''))
            self.hf_repo.set(config.get('hf_repo', ''))
            self.repeat_last_n.set(config.get('repeat_last_n', ''))
            self.frequency_penalty.set(config.get('frequency_penalty', ''))
            self.presence_penalty.set(config.get('presence_penalty', ''))
            self.min_p.set(config.get('min_p', ''))
            self.seed.set(config.get('seed', ''))
            # Load cache type settings (default: none / empty)
            try:
                self.cache_type_k.set(config.get('cache_type_k', ''))
            except Exception:
                self.cache_type_k.set('')
            try:
                self.cache_type_v.set(config.get('cache_type_v', ''))
            except Exception:
                self.cache_type_v.set('')
            
            # Update pointer to currently-loaded config
            self.config_file = load_path

            self.update_all_sliders()
        except Exception as e:
            Messagebox.show_error(f"加载配置失败： {e}", "错误")

    def open_browser(self):
        host = self.host.get().strip()
        if host == '0.0.0.0': host = 'localhost'
        url = f"http://{host}:{self.port.get().strip()}"
        try:
            webbrowser.open(url)
            self.update_output(f"🌐 已打开浏览器：{url}\n")
        except Exception as e:
            Messagebox.show_error(f"打开浏览器失败： {e}", "错误")

        # --- Tray Management ---
    def create_tray_icon(self):
        """Create system tray icon with menu."""
        if not TRAY_AVAILABLE:
            return None

        image = self.load_app_icon()
        menu_items = [
            item('显示窗口', self.show_window, default=True),
            item('打开浏览器', self.open_browser_from_tray, enabled=lambda i: self.is_running),
            pystray.Menu.SEPARATOR,
            item('退出程序', self.quit_application),
        ]
        icon = pystray.Icon("llama_server", image, "LLaMA 服务器", menu=pystray.Menu(*menu_items))
        return icon

    def load_app_icon(self):
        """Load app icon for tray (fallback to blank)."""
        try:
            return Image.open(resource_path("llama-cpp.ico"))
        except Exception:
            return Image.new("RGB", (64, 64), color=(0, 0, 0))

    def show_window(self, icon=None, item=None):
        """Restore window from tray."""
        self.root.after(0, self.root.deiconify)

    def open_browser_from_tray(self, icon=None, item=None):
        """Open browser when clicked from tray."""
        self.root.after(0, self.open_browser)

    def quit_application(self, icon=None, item=None):
        """Quit app from tray."""
        if self.server_process:
            self.server_process.terminate()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def hide_to_tray(self):
        """Hide window and show tray icon."""
        self.root.withdraw()
        if self.tray_icon is None:
            self.tray_icon = self.create_tray_icon()
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

            
def resource_path(filename):
    """Get absolute path to resource, works for dev and for PyInstaller bundle"""
    if getattr(sys, 'frozen', False):
        return os.path.join(sys._MEIPASS, filename)
    return os.path.join(os.path.abspath("."), filename)

def main():
    root = ttk.Window(themename="cosmo")
    
    try:
        icon_path = resource_path("llama-cpp.ico")
        if os.path.exists(icon_path):
            root.iconbitmap(icon_path)
    except Exception:
        pass
    
    app = LlamaServerGUI(root)

    def on_closing():
        if app.is_running and TRAY_AVAILABLE:
            app.hide_to_tray()
        else:
            if app.server_process:
                app.server_process.terminate()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()



if __name__ == "__main__":
    main()