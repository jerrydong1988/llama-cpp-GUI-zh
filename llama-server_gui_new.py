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
import urllib.request
import urllib.error

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

        # CPU thread detection for reference display
        self._logical_cpus = os.cpu_count() or 32
        self._physical_cores = self._logical_cpus
        try:
            import psutil
            phys = psutil.cpu_count(logical=False)
            if phys:
                self._physical_cores = phys
        except ImportError:
            if self._logical_cpus > 4:
                self._physical_cores = self._logical_cpus // 2
        self._cpu_hint = f"默认 {self._physical_cores}·最多 {self._logical_cpus} 线程"

        # Engine management
        self.engine_dirs = []  # list of {"name": str, "dir": str, "exe": str, "source": str}
        self.selected_engine_dir = ""  # dir of currently selected engine

        self.setup_ui()
        self.load_config()
        
        # Initialize config dropdown
        self._refresh_config_list()
        
        # Auto-adjust context slider when model path changes (debounced)
        self._ctx_slider_timer = None
        def on_model_path_change(*_):
            if self._ctx_slider_timer:
                self.root.after_cancel(self._ctx_slider_timer)
            self._ctx_slider_timer = self.root.after(500, self._auto_adjust_ctx_slider)
        self.model_path.trace_add('write', on_model_path_change)
        # Also trigger on startup (if model already loaded)
        self.root.after(600, self._auto_adjust_ctx_slider)

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
        
        # Config management: dropdown + save + delete
        ttk.Label(left_button_frame, text="配置:").pack(side=tk.LEFT, padx=(0, 3))
        self.config_combo = ttk.Combobox(left_button_frame, values=[], width=22, state="readonly")
        self.config_combo.pack(side=tk.LEFT, padx=(0, 5))
        self.config_combo.bind('<<ComboboxSelected>>', self._on_config_select)
        ToolTip(self.config_combo, "选择保存的配置，自动加载。")
        
        self.create_button(left_button_frame, "💾 保存", self.save_named_config, "以当前名称保存配置。", bootstyle="secondary")
        self.create_button(left_button_frame, "🗑 删除", self.delete_named_config, "删除选中的配置。", bootstyle="secondary")
        self.create_button(left_button_frame, "⚡ 生成命令", self.show_command, "显示将要执行的完整 llama-server 命令。", bootstyle="info")

        # Right-aligned buttons
        right_button_frame = ttk.Frame(control_frame)
        right_button_frame.pack(side=tk.RIGHT)
        self.browser_button = self.create_button(right_button_frame, "打开浏览器 🌐", self.open_browser, "Access the server web UI.", state=tk.DISABLED, bootstyle="primary-outline")
        self.stop_button = self.create_button(right_button_frame, "停止服务器 ⏹️", self.stop_server, "Stop the running server process.", state=tk.DISABLED, bootstyle="danger")
        self.start_button = self.create_button(right_button_frame, "启动服务器 ▶️", self.start_server, "Start the server with current settings.", bootstyle="success")
        
        # Server status indicator
        self.server_status_var = tk.StringVar(value="")
        self.server_status_label = ttk.Label(right_button_frame, textvariable=self.server_status_var,
            font=("", 9), foreground="gray")
        self.server_status_label.pack(side=tk.LEFT, padx=(10, 0))

        # --- Notebook (Packed SECOND to fill the remaining space) ---
        notebook = ttk.Notebook(main_container, bootstyle="primary")
        notebook.pack(fill=tk.BOTH, expand=True)

        # --- Create Tab Frames ---
        repo_frame = ttk.Frame(notebook, padding="10")
        engine_frame = ttk.Frame(notebook, padding="10")
        model_frame = ttk.Frame(notebook, padding="10")
        generation_frame = ttk.Frame(notebook, padding="10")
        performance_core_frame = ttk.Frame(notebook, padding="10")
        performance_advanced_frame = ttk.Frame(notebook, padding="10")
        server_api_frame = ttk.Frame(notebook, padding="10")
        output_frame = ttk.Frame(notebook, padding="10")

        notebook.add(repo_frame, text="  模型仓库  ")
        notebook.add(engine_frame, text="  引擎  ")
        notebook.add(model_frame, text="  模型  ")
        notebook.add(generation_frame, text="  生成参数  ")
        notebook.add(performance_core_frame, text="  性能  ")
        notebook.add(performance_advanced_frame, text="  高级  ")
        notebook.add(server_api_frame, text="  服务器与API  ")
        notebook.add(output_frame, text="  服务器输出  ")

        # --- Populate Tabs ---
        self.setup_model_repo_tab(repo_frame)
        self.setup_engine_tab(engine_frame)
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
        self.grammar_file = tk.StringVar()
        self.create_file_entry(ext_group, "语法文件 (--grammar-file):", self.grammar_file, "结构化输出用的 GBNF 语法文件路径（*.gbnf）。", ".gbnf", row=2)
        

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
        self.create_combobox(chat_group, "推理开关 (--reasoning):", self.reasoning, "启用/禁用/自动推理（思考）功能。off 时加载更快，on 开启思考过程但加载稍慢。MTP 模型都可正常使用。", reasoning_options, row=3)
        self.jinja = tk.BooleanVar(value=False)
        self.create_checkbutton(chat_group, "启用 Jinja (--jinja)", self.jinja, "启用 Jinja2 模板（某些自定义模板需要）。", row=4)
        self.reasoning_budget = tk.StringVar(value="")
        self.create_spinbox(chat_group, "推理预算 (--reasoning-budget):", self.reasoning_budget, "推理（思考）过程的令牌预算（默认 0 = 无限制）。", from_=0, to=65536, increment=256, row=5)

    def setup_generation_tab(self, parent):
        """Configures the 'Generation' tab for sampling and output control."""
        # --- Output Control ---
        output_group = ttk.Labelframe(parent, text="输出控制", padding="10")
        output_group.pack(fill=tk.X, pady=5, side=tk.TOP)
        
        self.n_predict = tk.StringVar(value="")
        self.create_spinbox(output_group, "生成令牌数 (-n, --n-predict):", self.n_predict, "生成的令牌数（默认 -1 = 无限）。", from_=-1, to=131072, increment=1, row=0)
        
        self.ignore_eos = tk.BooleanVar(value=False)
        self.create_checkbutton(output_group, "忽略结束标记 (--ignore-eos)", self.ignore_eos, "防止模型提前停止。", row=1)
        self.json_schema = tk.StringVar(value="")
        self.create_entry(output_group, "JSON 约束 (--json-schema):", self.json_schema, "JSON Schema 约束，限制输出为合法 JSON 格式。", row=2)
        
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

        # --- Advanced Sampling (collapsible) ---
        self.adv_sampling_visible = tk.BooleanVar(value=False)
        adv_toggle_frame = ttk.Frame(sampling_group)
        adv_toggle_frame.grid(row=9, column=0, columnspan=3, sticky=tk.W, pady=(10, 0))
        adv_toggle = ttk.Checkbutton(adv_toggle_frame, text="▸ 高级采样", variable=self.adv_sampling_visible, bootstyle="round-toggle")
        adv_toggle.pack(side=tk.LEFT)
        ToolTip(adv_toggle, "展开高级采样参数。建议一次只开一组：日常用 Mirostat，长文防重复用 DRY，创意写作加 XTC。")

        self.adv_sampling_frame = ttk.Frame(sampling_group)
        self.adv_sampling_frame.grid(row=10, column=0, columnspan=3, sticky=tk.EW, pady=5)
        self.adv_sampling_frame.grid_remove()  # hidden by default

        def toggle_adv_sampling():
            if self.adv_sampling_visible.get():
                self.adv_sampling_frame.grid()
            else:
                self.adv_sampling_frame.grid_remove()
        self.adv_sampling_visible.trace_add('write', lambda *_: toggle_adv_sampling())

        row = 0
        # --- Mirostat ---
        miro_group = ttk.Labelframe(self.adv_sampling_frame, text="Mirostat", padding="5")
        miro_group.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2); row += 1
        self.mirostat = tk.StringVar()
        self.create_combobox(miro_group, "模式 (--mirostat):", self.mirostat, "Mirostat 自适应采样。抗重复神器——动态调节筛选力度让文本熵稳定。推荐 2（v2），搭配 lr=0.05、ent=4.0 开箱即用。0=禁用。", ["", "0", "1", "2"], row=0)
        self.mirostat_lr = tk.StringVar(value="")
        self.create_spinbox(miro_group, "学习率 (--mirostat-lr):", self.mirostat_lr, "Mirostat 学习率。模型多快适应文本变化。推荐 0.05~0.1（快），创作用 0.01（稳）。默认 0.01。", from_=0.001, to=1, increment=0.001, row=1)
        self.mirostat_ent = tk.StringVar(value="")
        self.create_spinbox(miro_group, "目标熵 (--mirostat-ent):", self.mirostat_ent, "Mirostat 目标熵。越高越随机。推荐：对话 4.0，故事 5.0，代码 3.0。默认 5.0。", from_=0, to=10, increment=0.1, row=2)

        # --- XTC ---
        xtc_group = ttk.Labelframe(self.adv_sampling_frame, text="XTC 采样", padding="5")
        xtc_group.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2); row += 1
        self.xtc_probability = tk.StringVar(value="")
        self.create_spinbox(xtc_group, "概率 (--xtc-probability):", self.xtc_probability, 'XTC 采样概率。以该概率排除[太 obvious]的词，迫使模型选生僻词。推荐 0.1~0.3。0.0=禁用。创意写作、角色扮演效果佳。', from_=0, to=1, increment=0.05, row=0)
        self.xtc_threshold = tk.StringVar(value="")
        self.create_spinbox(xtc_group, "阈值 (--xtc-threshold):", self.xtc_threshold, 'XTC 阈值。词的概率超过此值即被视为[太 obvious]被排除。推荐 0.1~0.5。默认 0.1。', from_=0, to=1, increment=0.05, row=1)

        # --- Dynamic Temperature ---
        dyn_group = ttk.Labelframe(self.adv_sampling_frame, text="动态温度", padding="5")
        dyn_group.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2); row += 1
        self.dynatemp_range = tk.StringVar(value="")
        self.create_spinbox(dyn_group, "范围 (--dynatemp-range):", self.dynatemp_range, "动态温度范围。实际温度在 [temp-range, temp+range] 间自动摇摆。推荐 0.3~0.7。0.0=禁用。长文本生成效果好，开头保守中间放开。", from_=0, to=10, increment=0.1, row=0)
        self.dynatemp_exp = tk.StringVar(value="")
        self.create_spinbox(dyn_group, "指数 (--dynatemp-exp):", self.dynatemp_exp, "动态温度指数。调节对概率分布宽度的敏感度。推荐 1.0。越大越敏感。默认 1.0。", from_=0, to=5, increment=0.1, row=1)

        # --- Typical-P ---
        typ_group = ttk.Labelframe(self.adv_sampling_frame, text="典型采样", padding="5")
        typ_group.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2); row += 1
        self.typical_p = tk.StringVar(value="")
        self.create_spinbox(typ_group, "Typical-P (--typical-p):", self.typical_p, "局部典型采样。比 Top-P 更自然的选词策略，只选概率和信息量匹配的 typical 词。推荐 0.9~0.95。1.0=禁用。搭配 Mirostat 效果更好。", from_=0, to=1, increment=0.05, row=0)

        # --- DRY ---
        dry_group = ttk.Labelframe(self.adv_sampling_frame, text="DRY 采样", padding="5")
        dry_group.grid(row=row, column=0, columnspan=2, sticky=tk.EW, pady=2); row += 1
        self.dry_multiplier = tk.StringVar(value="")
        self.create_spinbox(dry_group, "倍数 (--dry-multiplier):", self.dry_multiplier, "DRY 重复惩罚强度。检测重复短语/句式并降权，比 --repeat-penalty 更智能。推荐 0.8~1.2。0.0=禁用。长文防重复神器。", from_=0, to=10, increment=0.1, row=0)
        self.dry_base = tk.StringVar(value="")
        self.create_spinbox(dry_group, "基数 (--dry-base):", self.dry_base, "DRY 惩罚增长曲线基数。通常保持默认 1.75，调高则惩罚增长更快。推荐 1.75。", from_=0, to=10, increment=0.1, row=1)
        self.dry_allowed_length = tk.StringVar(value="")
        self.create_spinbox(dry_group, "允许长度 (--dry-allowed-length):", self.dry_allowed_length, "DRY 允许重复的连续令牌数。推荐 2~3。设为 2 只允许 2 个词重复，更长就惩罚。默认 2。", from_=0, to=1024, increment=1, row=2)
        self.dry_penalty_last_n = tk.StringVar(value="")
        self.create_spinbox(dry_group, "惩罚窗口 (--dry-penalty-last-n):", self.dry_penalty_last_n, "DRY 扫描多少最近令牌检测重复。-1=整个上下文。推荐 -1（完整检测）。", from_=-1, to=999999, increment=1, row=3)
        self.dry_sequence_breaker = tk.StringVar(value="")
        self.create_entry(dry_group, "分隔符 (--dry-sequence-breaker):", self.dry_sequence_breaker, 'DRY 序列分隔符。写入后遇到此字符视为打断重复（如 "\\n" 遇换行重置计数）。按需设置。', row=4)




    def setup_performance_core_tab(self, parent):
        """Configures the 'Performance' tab for core speed and throughput settings."""
        # --- Core Performance ---
        core_group = ttk.Labelframe(parent, text="核心性能", padding="10")
        core_group.pack(fill=tk.X, pady=5, side=tk.TOP)
        self.ctx_size = tk.IntVar(value=4096)
        self.create_slider(core_group, "上下文大小 (-c):", self.ctx_size, "模型的上下文大小（序列长度）。选择模型后自动适配上限。", from_=0, to=524288, resolution=1024, row=0)
        self.ctx_size_auto = tk.BooleanVar(value=False)
        cb = ttk.Checkbutton(core_group, text="自动上下文 (--ctx-size 0)", variable=self.ctx_size_auto, bootstyle="round-toggle")
        cb.grid(row=0, column=2, sticky=tk.W, padx=5, pady=5)
        ToolTip(cb, "勾选后不传 -c 参数，llama-server 自动使用模型完整上下文长度。")

        self.gpu_layers = tk.IntVar(value=99)
        self.create_slider(core_group, "GPU 层数 (-ngl):", self.gpu_layers, "卸载到 GPU 的模型层数（99 = 全部）。", from_=0, to=99, resolution=1, row=1)
        self.threads = tk.StringVar(value="")
        spin_t = self.create_spinbox(core_group, "CPU 线程数 (-t):", self.threads, "使用的 CPU 线程数。留空=自动（默认物理核心数）。", from_=1, to=128, increment=1, row=2)
        hint_t = ttk.Label(core_group, text=self._cpu_hint, foreground="gray")
        hint_t.grid(row=2, column=2, sticky=tk.W, padx=(2, 2), pady=5)
        btn_t = ttk.Button(core_group, text="设为最大", bootstyle="primary-link",
                           command=lambda: self.threads.set(str(self._logical_cpus)))
        btn_t.grid(row=2, column=3, sticky=tk.W, padx=2, pady=5)
        ToolTip(btn_t, f"设置为系统最大线程数（{self._logical_cpus}）")
        def validate_thread(*_):
            val = self.threads.get()
            if val and val.isdigit() and int(val) > self._logical_cpus:
                hint_t.config(foreground="orange", text=f"⚠ 建议 ≤{self._logical_cpus}")
            elif val and val.isdigit() and int(val) == self._logical_cpus:
                hint_t.config(foreground="green", text=self._cpu_hint + " ✓")
            else:
                hint_t.config(foreground="gray", text=self._cpu_hint)
        self.threads.trace_add("write", validate_thread)
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
        spin_tb = self.create_spinbox(core_group, "批处理线程 (-tb, --threads-batch):", self.threads_batch, "提示处理和批处理时使用的线程数。留空=自动（默认同 -t）。", from_=1, to=128, increment=1, row=5)
        hint_tb = ttk.Label(core_group, text=self._cpu_hint, foreground="gray")
        hint_tb.grid(row=5, column=2, sticky=tk.W, padx=(2, 2), pady=5)
        btn_tb = ttk.Button(core_group, text="设为最大", bootstyle="primary-link",
                            command=lambda: self.threads_batch.set(str(self._logical_cpus)))
        btn_tb.grid(row=5, column=3, sticky=tk.W, padx=2, pady=5)
        ToolTip(btn_tb, f"设置为系统最大线程数（{self._logical_cpus}）")
        def validate_thread_batch(*_):
            val = self.threads_batch.get()
            if val and val.isdigit() and int(val) > self._logical_cpus:
                hint_tb.config(foreground="orange", text=f"⚠ 建议 ≤{self._logical_cpus}")
            elif val and val.isdigit() and int(val) == self._logical_cpus:
                hint_tb.config(foreground="green", text=self._cpu_hint + " ✓")
            else:
                hint_tb.config(foreground="gray", text=self._cpu_hint)
        self.threads_batch.trace_add("write", validate_thread_batch)

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
        # (草稿模型下载已整合到「模型」标签页的 ModelScope 区域)
        # --- Server Reliability ---
        # --- Server Reliability ---
        server_rel_group = ttk.Labelframe(parent, text="服务器可靠性", padding="10")
        server_rel_group.pack(fill=tk.X, pady=5)
        self.timeout = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "超时秒数 (--timeout):", self.timeout, "服务器读写超时秒数（默认 600）。", from_=1, to=3600, increment=10, row=0)
        self.sleep_idle = tk.StringVar(value="")
        self.create_spinbox(server_rel_group, "空闲休眠秒数 (--sleep-idle-seconds):", self.sleep_idle, "空闲 N 秒后自动卸载模型释放显存（默认 -1 = 禁用）。", from_=-1, to=86400, increment=60, row=1)
        self.context_shift = tk.BooleanVar(value=False)
        self.create_checkbutton(server_rel_group, "上下文偏移 (--context-shift)", self.context_shift, "无限生成时的上下文偏移策略，避免超出上下文窗口。", row=2)

        
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
        self.ssl_key_file = tk.StringVar()
        self.create_file_entry(net_group, "SSL 私钥 (--ssl-key-file):", self.ssl_key_file, "SSL 私钥文件路径（启用 HTTPS）。", ".key", row=2)
        self.ssl_cert_file = tk.StringVar()
        self.create_file_entry(net_group, "SSL 证书 (--ssl-cert-file):", self.ssl_cert_file, "SSL 证书文件路径。", ".pem", row=3)

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
        
        # Define color tags for keyword highlighting
        self.output_text.tag_configure("error", foreground="#e74c3c")      # red: errors
        self.output_text.tag_configure("speed", foreground="#27ae60")      # green: tokens/s, listening
        self.output_text.tag_configure("warn", foreground="#f39c12")       # orange: warnings
        self.output_text.tag_configure("feature", foreground="#3498db")    # blue: MTP, flash attn, reasoning
        self.output_text.tag_configure("normal", foreground="#7f8c8d")     # gray: default
        
        self._log_patterns = [
            ("error", ["error", "fail", "panic", "fatal", "out of memory",
                        "cudamalloc", "ggml_backend.*error", "rocm error",
                        "could not", "unable to", "segfault", "abort", "exception"]),
            ("speed", ["tokens/s", "server is listening", "eval time",
                        "prompt eval", "prompt eval time", "total time"]),
            ("warn", ["warn", "warning", "deprecated"]),
            ("feature", ["mtp", "draft head registered", "reasoning", "flash att",
                          "speculative", "grammar", "embedding"]),
        ]
        
        clear_btn = ttk.Button(parent, text="清空输出", command=self.clear_output, bootstyle="secondary-outline")
        clear_btn.pack(pady=(10, 0), anchor=tk.E)
        ToolTip(clear_btn, "清除日志输出窗口中的所有文本。")

    # --- 模型仓库 (Model Repository) Tab ---
    def setup_model_repo_tab(self, parent):
        """Model repository tab - browse and manage downloaded models from multiple sources."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)  # main_frame (row 2) should expand
        
        # === Top: ModelScope 在线下载 ===
        dl_frame = ttk.Frame(parent)
        dl_frame.grid(row=0, column=0, sticky=tk.NSEW)
        dl_frame.columnconfigure(1, weight=1)
        
        # --- Main Model Download ---
        ms_group = ttk.Labelframe(dl_frame, text="ModelScope 模型下载", padding="8")
        ms_group.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 5))
        ms_group.columnconfigure(1, weight=1)
        
        self.ms_repo = tk.StringVar()
        self.create_entry(ms_group, "主模型仓库:", self.ms_repo, 
            "ModelScope 模型仓库 ID，例如 unsloth/Qwen3.6-35B-A3B-GGUF。", row=0)
        
        file_ctrl_frame = ttk.Frame(ms_group)
        file_ctrl_frame.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(2, 0))
        file_ctrl_frame.columnconfigure(3, weight=1)
        
        self.browse_ms_btn = ttk.Button(file_ctrl_frame, text="📂 浏览文件", 
            command=self.browse_ms_files, bootstyle="primary")
        self.browse_ms_btn.grid(row=0, column=0, padx=(0, 5))
        ToolTip(self.browse_ms_btn, "查询仓库中的 GGUF 模型文件列表。")
        
        self.download_ms_btn = ttk.Button(file_ctrl_frame, text="⬇ 下载选中", 
            command=self.download_selected_ms_file, state=tk.DISABLED, bootstyle="success")
        self.download_ms_btn.grid(row=0, column=1, padx=(0, 5))
        ToolTip(self.download_ms_btn, "下载已勾选的文件。")
        
        self.cancel_ms_btn = ttk.Button(file_ctrl_frame, text="✕ 取消", 
            command=self.cancel_ms_download, state=tk.DISABLED, bootstyle="danger-outline")
        self.cancel_ms_btn.grid(row=0, column=2, padx=(0, 5))
        ToolTip(self.cancel_ms_btn, "取消正在进行的下载。")
        
        self.ms_status_var = tk.StringVar(value="")
        self.ms_status_label = ttk.Label(file_ctrl_frame, textvariable=self.ms_status_var, foreground="gray")
        self.ms_status_label.grid(row=0, column=3, padx=(5, 0), sticky=tk.W)
        
        self.ms_progress = ttk.Progressbar(ms_group, mode='determinate', value=0)
        self.ms_progress.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(2, 2))
        self.ms_progress_label = ttk.Label(ms_group, text="", font=("", 8))
        self.ms_progress_label.grid(row=3, column=0, columnspan=2, sticky=tk.W)
        
        self.ms_list_frame = ttk.Frame(ms_group)
        self.ms_list_frame.grid(row=4, column=0, columnspan=2, sticky=tk.NSEW, pady=(2, 0))
        ms_group.rowconfigure(4, weight=1)
        
        self.ms_file_canvas = tk.Canvas(self.ms_list_frame, highlightthickness=0)
        self.ms_file_scrollbar = ttk.Scrollbar(self.ms_list_frame, orient=tk.VERTICAL, command=self.ms_file_canvas.yview)
        self.ms_file_checkframe = ttk.Frame(self.ms_file_canvas)
        self.ms_file_checkframe.bind("<Configure>", lambda e: self.ms_file_canvas.configure(scrollregion=self.ms_file_canvas.bbox("all")))
        self.ms_file_canvas.create_window((0, 0), window=self.ms_file_checkframe, anchor="nw")
        self.ms_file_canvas.configure(yscrollcommand=self.ms_file_scrollbar.set)
        self.ms_file_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.ms_file_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Bind mousewheel to canvas and its content area only
        def _on_mw(event):
            self.ms_file_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        self.ms_file_canvas.bind("<MouseWheel>", _on_mw)
        self.ms_file_checkframe.bind("<MouseWheel>", _on_mw)
        
        self.ms_file_vars = []
        
        # --- Draft Model Download ---
        dg = ttk.Labelframe(dl_frame, text="草稿模型下载（推测解码用）", padding="6")
        dg.grid(row=1, column=0, columnspan=2, sticky=tk.EW)
        dg.columnconfigure(1, weight=1)
        
        self.draft_ms_repo = tk.StringVar()
        self.create_entry(dg, "草稿仓库:", self.draft_ms_repo,
            "草稿模型 ModelScope 仓库 ID，例如 unsloth/Qwen2.5-0.5B-GGUF。", row=0)
        
        dc = ttk.Frame(dg)
        dc.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(2, 0))
        self.draft_browse_btn = ttk.Button(dc, text="📂 浏览文件",
            command=self.draft_browse_files, bootstyle="primary")
        self.draft_browse_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.draft_dl_btn = ttk.Button(dc, text="⬇ 下载选中",
            command=self.draft_download, state=tk.DISABLED, bootstyle="success")
        self.draft_dl_btn.pack(side=tk.LEFT)
        self.draft_status_var = tk.StringVar(value="")
        ttk.Label(dc, textvariable=self.draft_status_var, foreground="gray").pack(side=tk.LEFT, padx=(10, 0))
        
        self.draft_listbox = tk.Listbox(dg, height=4, font=("Consolas", 8))
        self.draft_listbox.grid(row=2, column=0, columnspan=2, sticky=tk.EW, pady=(3, 0))
        self.draft_listbox.bind("<<ListboxSelect>>", self._on_draft_select)
        self.draft_file_data = []
        
        # Separator
        ttk.Separator(parent, orient=tk.HORIZONTAL).grid(row=1, column=0, sticky=tk.EW, pady=5)

        # Main container with left tree and right detail
        main_frame = ttk.Frame(parent)
        main_frame.grid(row=2, column=0, sticky=tk.NSEW)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)
        main_frame.rowconfigure(0, weight=1)
        
        # === Left: TreeView ===
        tree_container = ttk.Frame(main_frame)
        tree_container.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 5))
        tree_container.rowconfigure(1, weight=1)
        tree_container.columnconfigure(0, weight=1)
        
        # Toolbar: refresh + add directory
        toolbar = ttk.Frame(tree_container)
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))
        
        self.repo_refresh_btn = ttk.Button(toolbar, text="🔄 刷新", 
            command=self.scan_downloaded_models, bootstyle="primary-outline")
        self.repo_refresh_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        self.repo_add_dir_btn = ttk.Button(toolbar, text="➕ 添加目录", 
            command=self.repo_add_root, bootstyle="info")
        self.repo_add_dir_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.repo_add_dir_btn, "添加包含 GGUF 模型文件的目录。支持 LM Studio、NovaMax 等任意目录。")
        
        self.repo_root_label = ttk.Label(toolbar, text="", foreground="gray", font=("", 8))
        self.repo_root_label.pack(side=tk.LEFT, padx=(5, 0))
        
        # Treeview frame
        tree_frame = ttk.Frame(tree_container)
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        
        self.repo_tree = ttk.Treeview(tree_frame, columns=('size', 'filetype', 'fullpath'),
            show='tree', selectmode='browse', height=12)
        self.repo_tree.heading('#0', text='模型文件')
        self.repo_tree.column('#0', width=400, minwidth=300)
        
        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.repo_tree.yview)
        self.repo_tree.configure(yscrollcommand=tree_scroll.set)
        
        self.repo_tree.grid(row=0, column=0, sticky=tk.NSEW)
        tree_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.repo_tree.bind('<<TreeviewSelect>>', self.on_repo_tree_select)
        self.repo_tree.bind('<Button-3>', self._repo_show_context_menu)  # right-click
        
        # === Right: Detail Panel ===
        detail_container = ttk.Frame(main_frame, width=280)
        detail_container.grid(row=0, column=1, sticky=tk.NSEW, padx=(5, 0))
        detail_container.grid_propagate(False)
        
        # Model detail display
        detail_group = ttk.Labelframe(detail_container, text="模型详情", padding="8")
        detail_group.pack(fill=tk.X, pady=(0, 10))
        
        self.repo_info_vars = {}
        info_fields = [
            ('文件名', 'name', ''),
            ('大小', 'size', ''),
            ('类型', 'type', ''),
            ('来源', 'source', ''),
            ('路径', 'path', ''),
            ('元信息', 'meta', ''),
        ]
        for label, key, default in info_fields:
            row = ttk.Frame(detail_group)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}：", width=6, anchor=tk.E).pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            lbl = ttk.Label(row, textvariable=var, anchor=tk.W, wraplength=200)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.repo_info_vars[key] = var
        
        # Action buttons
        action_group = ttk.Labelframe(detail_container, text="操作", padding="8")
        action_group.pack(fill=tk.X)
        
        self.repo_load_btn = ttk.Button(action_group, text="📥 加载模型", 
            command=self.repo_load_model, state=tk.DISABLED, bootstyle="success")
        self.repo_load_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.repo_load_btn, "将选中的模型填入主配置的模型路径。")
        
        self.repo_load_mmproj_btn = ttk.Button(action_group, text="📷 加载投影器", 
            command=self.repo_load_mmproj, state=tk.DISABLED, bootstyle="info")
        self.repo_load_mmproj_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.repo_load_mmproj_btn, "将选中的 mmproj 文件填入多模态投影器路径。")
        
        self.repo_delete_btn = ttk.Button(action_group, text="🗑 删除文件", 
            command=self.repo_delete_file, state=tk.DISABLED, bootstyle="danger-outline")
        self.repo_delete_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.repo_delete_btn, "从磁盘删除选中的模型文件。")
        
        self.repo_open_btn = ttk.Button(action_group, text="📂 打开目录", 
            command=self.repo_open_folder, state=tk.DISABLED, bootstyle="secondary-outline")
        self.repo_open_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.repo_open_btn, "在资源管理器中打开文件所在目录。")
        
        # Context menu for right-click
        self.repo_context_menu = tk.Menu(self.root, tearoff=0)
        self.repo_context_menu.add_command(label="移除此目录", command=self._repo_remove_selected_root)
        
        # Store file info per tree item
        self.repo_tree_items = {}  # iid -> {name, path, type, size}
        self.repo_root_items = {}  # root_iid -> {path, label, builtin}
        self._repo_selected_path = None  # full path of currently selected file
        
        # Initialize roots
        app_dir = os.path.dirname(self.get_config_path(''))
        default_path = os.path.join(app_dir, 'models')
        self.model_repo_roots = [
            {'path': default_path, 'label': '默认仓库', 'builtin': True}
        ]
        
        # Auto-scan on first load
        self.root.after(100, self.scan_downloaded_models)
    
    def scan_downloaded_models(self):
        """Scan all root directories and populate the tree."""
        for item in self.repo_tree.get_children():
            self.repo_tree.delete(item)
        self.repo_tree_items.clear()
        self.repo_root_items.clear()
        self._clear_repo_detail()
        
        total_files = 0
        for root_info in self.model_repo_roots:
            root_path = root_info['path']
            if not os.path.isdir(root_path):
                continue
            
            root_label = root_info['label']
            builtin = root_info.get('builtin', False)
            marker = "★ " if builtin else "  "
            root_iid = f"root_{id(root_info)}"
            self.repo_tree.insert('', tk.END, text=f"{marker}{root_label}  ({root_path})",
                iid=root_iid, open=True)
            self.repo_root_items[root_iid] = {'path': root_path, 'label': root_label, 'builtin': builtin}
            
            files = self._scan_directory_for_gguf(root_path)
            if files:
                # Group by subdirectory relative to root
                groups = {}
                for fpath, fname in files:
                    rel_dir = os.path.relpath(os.path.dirname(fpath), root_path)
                    if rel_dir == '.':
                        group = ''
                    else:
                        group = rel_dir
                    if group not in groups:
                        groups[group] = []
                    groups[group].append((fpath, fname))
                
                for group_name in sorted(groups.keys()):
                    if group_name:
                        repo_iid = f"repo_{root_iid}_{group_name}"
                        self.repo_tree.insert(root_iid, tk.END, 
                            text=f"📁 {group_name}", iid=repo_iid, open=False)
                        parent_iid = repo_iid
                    else:
                        parent_iid = root_iid
                    
                    for fpath, fname in sorted(groups[group_name], key=lambda x: x[1]):
                        self._add_file_to_tree(parent_iid, fpath, fname, root_label)
                        total_files += 1
            else:
                # Empty root
                empty_iid = f"empty_{root_iid}"
                self.repo_tree.insert(root_iid, tk.END, text="(空)", iid=empty_iid)
        
        # Update label
        n_roots = len([r for r in self.model_repo_roots if os.path.isdir(r['path'])])
        suffix = f" | 共 {total_files} 个文件" if total_files else ""
        self.repo_root_label.config(text=f"{n_roots} 个目录{suffix}")
        
        if not total_files:
            self.repo_tree.insert('', tk.END, text='📭 未找到模型文件。点击「添加目录」导入已有模型。', iid='_empty')
    
    def _scan_directory_for_gguf(self, directory):
        """Recursively scan a directory for .gguf files. Returns list of (full_path, filename)."""
        results = []
        try:
            for entry in os.listdir(directory):
                entry_path = os.path.join(directory, entry)
                if os.path.isfile(entry_path) and (entry.endswith('.gguf') or entry.endswith('.gguf_file')):
                    results.append((entry_path, entry))
                elif os.path.isdir(entry_path):
                    # Don't recurse into directories that look like they might not contain models
                    results.extend(self._scan_directory_for_gguf(entry_path))
        except (PermissionError, OSError):
            pass
        return results
    
    def _add_file_to_tree(self, parent_iid, fpath, fname, source_label):
        """Add a single model file to the tree under the given parent."""
        size = os.path.getsize(fpath)
        size_str = self._format_size(size)
        
        is_mmproj = fname.startswith('mmproj')
        is_imatrix = 'imatrix' in fname.lower()
        icon = "📷" if is_mmproj else ("📊" if is_imatrix else "📄")
        ftype = "mmproj" if is_mmproj else ("imatrix" if is_imatrix else "model")
        
        safe_name = fname.replace('.', '_').replace(' ', '_')
        file_iid = f"file_{parent_iid}_{safe_name}"
        self.repo_tree.insert(parent_iid, tk.END, 
            text=f"{icon}  {size_str:>9s}  {fname}",
            iid=file_iid)
        self.repo_tree_items[file_iid] = {
            'name': fname,
            'path': fpath,
            'size': size,
            'type': ftype,
            'source': source_label
        }
    
    def on_repo_tree_select(self, event):
        """Handle tree selection change."""
        selection = self.repo_tree.selection()
        if not selection:
            self._clear_repo_detail()
            return
        
        iid = selection[0]
        item_info = self.repo_tree_items.get(iid)
        
        if not item_info:
            self._clear_repo_detail()
            return
        
        self._repo_selected_path = item_info['path']
        
        self.repo_info_vars['name'].set(item_info['name'])
        self.repo_info_vars['size'].set(self._format_size(item_info['size']))
        self.repo_info_vars['source'].set(item_info.get('source', ''))
        
        ftype = item_info['type']
        if ftype == 'mmproj':
            type_display = "📷 多模态投影器"
        elif ftype == 'imatrix':
            type_display = "📊 重要性矩阵"
        else:
            type_display = "📄 主模型"
        self.repo_info_vars['type'].set(type_display)
        self.repo_info_vars['path'].set(item_info['path'])
        
        # Show GGUF metadata for model files
        if ftype == 'model' and os.path.isfile(item_info['path']):
            meta_str = self._get_model_metadata_display(item_info['path'])
            self.repo_info_vars['meta'].set(meta_str)
        else:
            self.repo_info_vars['meta'].set('')
        
        self.repo_load_btn.config(state=tk.NORMAL if ftype == 'model' else tk.DISABLED)
        self.repo_load_mmproj_btn.config(state=tk.NORMAL if ftype == 'mmproj' else tk.DISABLED)
        self.repo_delete_btn.config(state=tk.NORMAL)
        self.repo_open_btn.config(state=tk.NORMAL)
    
    def _clear_repo_detail(self):
        self._repo_selected_path = None
        for key, var in self.repo_info_vars.items():
            var.set('')
        self.repo_load_btn.config(state=tk.DISABLED)
        self.repo_load_mmproj_btn.config(state=tk.DISABLED)
        self.repo_delete_btn.config(state=tk.DISABLED)
        self.repo_open_btn.config(state=tk.DISABLED)
    
    def repo_add_root(self):
        """Add a custom directory to scan for models."""
        app_dir = os.path.dirname(self.get_config_path(''))
        chosen = filedialog.askdirectory(
            title="选择包含 GGUF 模型文件的目录",
            initialdir=app_dir
        )
        if not chosen:
            return
        
        # Check for duplicate
        norm_chosen = os.path.normcase(chosen)
        for r in self.model_repo_roots:
            if os.path.normcase(r['path']) == norm_chosen:
                Messagebox.show_warning("该目录已在列表中。", "重复", parent=self.root)
                return
        
        # Auto-generate a label
        dir_name = os.path.basename(chosen)
        label = dir_name
        
        self.model_repo_roots.append({'path': chosen, 'label': label, 'builtin': False})
        self.scan_downloaded_models()
        self.repo_root_label.config(text=f"{len(self.model_repo_roots)} 个目录")
        
        Messagebox.ok(f"已添加目录：{chosen}\n\n点击「刷新」可重新扫描。", "添加成功", parent=self.root)
    
    def _repo_show_context_menu(self, event):
        """Show right-click context menu."""
        iid = self.repo_tree.identify_row(event.y)
        if iid and iid in self.repo_root_items:
            root_info = self.repo_root_items[iid]
            if not root_info.get('builtin', False):
                self._repo_context_iid = iid
                self.repo_context_menu.post(event.x_root, event.y_root)
    
    def _repo_remove_selected_root(self):
        """Remove a custom root directory from the scan list."""
        iid = getattr(self, '_repo_context_iid', None)
        if not iid or iid not in self.repo_root_items:
            return
        root_info = self.repo_root_items[iid]
        
        reply = Messagebox.yesno(
            f"确定将「{root_info['label']}」移出扫描列表？\n文件不会被删除。",
            "确认移除",
            parent=self.root
        )
        if not reply:
            return
        
        # Remove from roots
        self.model_repo_roots = [
            r for r in self.model_repo_roots 
            if os.path.normcase(r['path']) != os.path.normcase(root_info['path'])
        ]
        self.scan_downloaded_models()
    
    def repo_load_model(self):
        """Load the selected model into the main config."""
        if not self._repo_selected_path:
            return
        self.model_path.set(self._repo_selected_path)
        
        # Auto-handle mmproj: clear old one, fill if found in same directory
        repo_dir = os.path.dirname(self._repo_selected_path)
        mmproj_found = None
        if os.path.isdir(repo_dir):
            for f in os.listdir(repo_dir):
                if f.startswith('mmproj') and f.endswith('.gguf'):
                    mmproj_found = os.path.join(repo_dir, f)
                    break
        if mmproj_found:
            self.mmproj_path.set(mmproj_found)
        else:
            self.mmproj_path.set("")
        # Also fill alias immediately (context slider debounce may be delayed)
        self._auto_fill_alias(force=True)
    
    def repo_load_mmproj(self):
        """Load the selected mmproj into the config."""
        if not self._repo_selected_path:
            return
        self.mmproj_path.set(self._repo_selected_path)
        Messagebox.ok(f"多模态投影器路径已设为：\n{self._repo_selected_path}", "已加载", parent=self.root)
    
    def repo_delete_file(self):
        """Delete the selected file from disk."""
        if not self._repo_selected_path:
            return
        fname = os.path.basename(self._repo_selected_path)
        reply = Messagebox.yesno(
            f"确定要删除 {fname}？\n此操作不可撤销！",
            "确认删除",
            parent=self.root
        )
        if not reply:
            return
        
        try:
            os.remove(self._repo_selected_path)
            Messagebox.ok(f"已删除：{fname}", "删除成功", parent=self.root)
            self.scan_downloaded_models()  # Refresh tree
        except Exception as e:
            Messagebox.show_error(f"删除失败：{e}", "错误", parent=self.root)
    
    def repo_open_folder(self):
        """Open the file's directory in file explorer."""
        if not self._repo_selected_path:
            return
        folder = os.path.dirname(self._repo_selected_path)
        try:
            os.startfile(folder)
        except Exception as e:
            Messagebox.show_error(f"打开目录失败：{e}", "错误", parent=self.root)

    # --- 引擎管理 (Engine Management) Tab ---
    def setup_engine_tab(self, parent):
        """Engine management tab - manage llama-server engine versions."""
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)
        
        # Main split: engine list (left) | detail (right)
        main_frame = ttk.Frame(parent)
        main_frame.grid(row=0, column=0, sticky=tk.NSEW)
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=0)
        main_frame.rowconfigure(0, weight=1)
        
        # === Left: Engine List ===
        list_container = ttk.Frame(main_frame)
        list_container.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 5))
        list_container.rowconfigure(1, weight=1)
        list_container.columnconfigure(0, weight=1)
        
        # Toolbar
        toolbar = ttk.Frame(list_container)
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))
        self.engine_refresh_btn = ttk.Button(toolbar, text="🔄 刷新", 
            command=self.scan_engines, bootstyle="primary-outline")
        self.engine_refresh_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.engine_add_btn = ttk.Button(toolbar, text="➕ 添加引擎目录", 
            command=self.engine_add_directory, bootstyle="info")
        self.engine_add_btn.pack(side=tk.LEFT)
        ToolTip(self.engine_add_btn, "选择一个包含 llama-server.exe 的目录。")
        
        # Engine list (using Treeview for single-column list with icons)
        list_frame = ttk.Frame(list_container)
        list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)
        
        self.engine_tree = ttk.Treeview(list_frame, columns=('source', 'dirpath'),
            show='tree', selectmode='browse', height=8)
        self.engine_tree.heading('#0', text='已安装引擎')
        self.engine_tree.column('#0', width=400, minwidth=300)
        # Tag for default engine highlight
        self.engine_tree.tag_configure('default', background='#FFE4B5', foreground='#8B4513', font=('TkDefaultFont', 9, 'bold'))
        
        engine_scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.engine_tree.yview)
        self.engine_tree.configure(yscrollcommand=engine_scroll.set)
        self.engine_tree.grid(row=0, column=0, sticky=tk.NSEW)
        engine_scroll.grid(row=0, column=1, sticky=tk.NS)
        self.engine_tree.bind('<<TreeviewSelect>>', self.on_engine_select)
        
        # === Right: Detail Panel ===
        detail_container = ttk.Frame(main_frame, width=280)
        detail_container.grid(row=0, column=1, sticky=tk.NSEW, padx=(5, 0))
        detail_container.grid_propagate(False)
        
        # Engine detail
        det_group = ttk.Labelframe(detail_container, text="引擎详情", padding="8")
        det_group.pack(fill=tk.X, pady=(0, 10))
        
        self.engine_info_vars = {}
        for label, key in [('名称', 'name'), ('版本', 'version'), ('来源', 'source'), ('路径', 'dir')]:
            row = ttk.Frame(det_group)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=f"{label}：", width=6, anchor=tk.E).pack(side=tk.LEFT)
            var = tk.StringVar(value='')
            lbl = ttk.Label(row, textvariable=var, anchor=tk.W, wraplength=200)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True)
            self.engine_info_vars[key] = var
        
        # Default indicator
        self.engine_default_label = ttk.Label(det_group, text="", foreground="green", font=("", 9, "bold"))
        self.engine_default_label.pack(anchor=tk.W, pady=(5, 0))
        
        # Action buttons
        act_group = ttk.Labelframe(detail_container, text="操作", padding="8")
        act_group.pack(fill=tk.X)
        
        self.engine_set_default_btn = ttk.Button(act_group, text="⭐ 设为默认",
            command=self.engine_set_default, state=tk.DISABLED, bootstyle="warning")
        self.engine_set_default_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.engine_set_default_btn, "使用此引擎启动服务器。")
        
        self.engine_delete_btn = ttk.Button(act_group, text="🗑 移出列表",
            command=self.engine_delete, state=tk.DISABLED, bootstyle="danger-outline")
        self.engine_delete_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.engine_delete_btn, "从引擎列表中移除此条目（不删除文件）。")
        
        self.engine_open_btn = ttk.Button(act_group, text="📂 打开目录",
            command=self.engine_open_folder, state=tk.DISABLED, bootstyle="secondary-outline")
        self.engine_open_btn.pack(fill=tk.X, pady=2)
        ToolTip(self.engine_open_btn, "在资源管理器中打开引擎目录。")
        
        # Status bar
        self.engine_status_var = tk.StringVar(value="")
        self.engine_status = ttk.Label(parent, textvariable=self.engine_status_var, foreground="gray")
        self.engine_status.grid(row=1, column=0, sticky=tk.W, pady=(5, 0))
        
        # Store engine tree item data
        self.engine_tree_items = {}  # iid -> engine_info_dict
        
        # Auto-scan on load
        self.root.after(150, self.scan_engines)
    
    def scan_engines(self):
        """Scan for installed engines and populate the list."""
        for item in self.engine_tree.get_children():
            self.engine_tree.delete(item)
        self.engine_tree_items.clear()
        self._clear_engine_detail()
        
        app_dir = os.path.dirname(self.get_config_path(''))
        engines = []
        seen_dirs = set()
        
        # 1. Scan 'engines/' directory at app root
        engines_dir = os.path.join(app_dir, 'engines')
        if os.path.isdir(engines_dir):
            for entry in sorted(os.listdir(engines_dir)):
                eng_dir = os.path.join(engines_dir, entry)
                exe_path = os.path.join(eng_dir, 'llama-server.exe')
                if os.path.isdir(eng_dir) and os.path.isfile(exe_path):
                    eng_info = self._get_engine_info(entry, eng_dir, exe_path, '本地')
                    engines.append(eng_info)
                    seen_dirs.add(os.path.normcase(eng_dir))
        
        # 2. Scan NovaMax engine directory if it exists
        novamax_engines = os.path.join('C:\\LingLong\\NovaStudio\\NovaMax', 'external', 'llamacpp')
        if os.path.isdir(novamax_engines):
            for entry in sorted(os.listdir(novamax_engines)):
                eng_dir = os.path.join(novamax_engines, entry)
                exe_path = os.path.join(eng_dir, 'llama-server.exe')
                if os.path.isdir(eng_dir) and os.path.isfile(exe_path):
                    norm = os.path.normcase(eng_dir)
                    if norm not in seen_dirs:
                        eng_info = self._get_engine_info(entry, eng_dir, exe_path, 'NovaMax')
                        engines.append(eng_info)
                        seen_dirs.add(norm)
        
        self.engine_dirs = engines
        
        # Populate tree
        for eng in engines:
            is_default = (os.path.normcase(eng['dir']) == os.path.normcase(self.selected_engine_dir))
            marker = "⭐ " if is_default else "  "
            icon = "🖥" if 'ROCm' in eng.get('version', '') or 'hip' in eng.get('name', '').lower() else "⚡"
            label = f"{eng['name']}  [默认]" if is_default else eng['name']
            iid = self.engine_tree.insert('', tk.END, 
                text=f"{marker}{icon}  {label}",
                iid=eng['name'],
                tags=('default',) if is_default else ())
            self.engine_tree_items[eng['name']] = eng
        
        # Restore default selection
        if self.selected_engine_dir:
            for eng in engines:
                if os.path.normcase(eng['dir']) == os.path.normcase(self.selected_engine_dir):
                    self.engine_tree.selection_set(eng['name'])
                    self.engine_tree.see(eng['name'])
                    self._show_engine_detail(eng)
                    break
        
        if engines:
            count_rocm = sum(1 for e in engines if 'ROCm' in e.get('version', '') or 'hip' in e.get('name', '').lower())
            count_vk = sum(1 for e in engines if 'vulkan' in e.get('name', '').lower())
            parts = [f"✅ 找到 {len(engines)} 个引擎"]
            if count_rocm: parts.append(f"{count_rocm} 个 ROCm")
            if count_vk: parts.append(f"{count_vk} 个 Vulkan")
            self.engine_status_var.set(" | ".join(parts))
        else:
            self.engine_status_var.set("⚠ 未找到引擎，将使用系统 PATH 中的 llama-server")
    
    def _get_engine_info(self, name, eng_dir, exe_path, source):
        """Extract engine info from directory."""
        # Try to read version from exe or directory name
        version = name  # fallback: use directory name
        exe_size = os.path.getsize(exe_path) if os.path.exists(exe_path) else 0
        
        # Detect backend type from directory contents
        has_rocm = any(f.startswith('roc') or f.startswith('hip') or 'amd' in f.lower() 
            for f in os.listdir(eng_dir) if os.path.isfile(os.path.join(eng_dir, f)))
        has_vulkan = any('vulkan' in f.lower() or 'vk' in f.lower()
            for f in os.listdir(eng_dir) if os.path.isfile(os.path.join(eng_dir, f)))
        
        if has_rocm:
            backend = "ROCm"
        elif has_vulkan:
            backend = "Vulkan"
        else:
            backend = "CPU"
        
        return {
            'name': name,
            'dir': eng_dir,
            'exe': exe_path,
            'exe_size': exe_size,
            'source': source,
            'version': f"{name} ({backend})",
            'backend': backend
        }
    
    def _clear_engine_detail(self):
        for var in self.engine_info_vars.values():
            var.set('')
        self.engine_default_label.config(text="")
        self.engine_set_default_btn.config(state=tk.DISABLED)
        self.engine_delete_btn.config(state=tk.DISABLED)
        self.engine_open_btn.config(state=tk.DISABLED)
    
    def _show_engine_detail(self, eng):
        self.engine_info_vars['name'].set(eng['name'])
        self.engine_info_vars['version'].set(eng.get('version', eng['name']))
        self.engine_info_vars['source'].set(eng['source'])
        self.engine_info_vars['dir'].set(eng['dir'])
        
        is_default = (os.path.normcase(eng['dir']) == os.path.normcase(self.selected_engine_dir))
        self.engine_default_label.config(
            text="⭐ 当前默认引擎" if is_default else "",
            foreground="green")
        
        self.engine_set_default_btn.config(state=tk.NORMAL if not is_default else tk.DISABLED)
        self.engine_delete_btn.config(state=tk.NORMAL)
        self.engine_open_btn.config(state=tk.NORMAL)
    
    def on_engine_select(self, event):
        selection = self.engine_tree.selection()
        if not selection:
            self._clear_engine_detail()
            return
        iid = selection[0]
        eng = self.engine_tree_items.get(iid)
        if eng:
            self._show_engine_detail(eng)
    
    def engine_set_default(self):
        """Set the selected engine as default."""
        selection = self.engine_tree.selection()
        if not selection:
            return
        iid = selection[0]
        eng = self.engine_tree_items.get(iid)
        if not eng:
            return
        
        self.selected_engine_dir = eng['dir']
        
        # Update tree markers and tags
        for child in self.engine_tree.get_children():
            e = self.engine_tree_items.get(child)
            if not e:
                continue
            is_default = os.path.normcase(e['dir']) == os.path.normcase(self.selected_engine_dir)
            marker = "⭐ " if is_default else "  "
            icon = "🖥" if 'ROCm' in e.get('version', '') or 'hip' in e.get('name', '').lower() else "⚡"
            label = f"{e['name']}  [默认]" if is_default else e['name']
            self.engine_tree.item(child,
                text=f"{marker}{icon}  {label}",
                tags=('default',) if is_default else ())
        
        self.engine_status_var.set(f"✅ 默认引擎：{eng['name']}")
        Messagebox.ok(f"默认引擎已设为：\n{eng['dir']}", "已设置", parent=self.root)
    
    def engine_add_directory(self):
        """Browse and add an engine directory."""
        app_dir = os.path.dirname(self.get_config_path(''))
        chosen = filedialog.askdirectory(
            title="选择包含 llama-server.exe 的目录",
            initialdir=app_dir
        )
        if not chosen:
            return
        
        exe_path = os.path.join(chosen, 'llama-server.exe')
        if not os.path.isfile(exe_path):
            Messagebox.show_error("所选目录中没有找到 llama-server.exe！", "错误", parent=self.root)
            return
        
        name = os.path.basename(chosen)
        norm_chosen = os.path.normcase(chosen)
        for eng in self.engine_dirs:
            if os.path.normcase(eng['dir']) == norm_chosen:
                Messagebox.show_warning("该引擎已在列表中。", "重复", parent=self.root)
                return
        
        eng = self._get_engine_info(name, chosen, exe_path, '自定义')
        self.engine_dirs.append(eng)
        self.engine_tree_items[eng['name']] = eng
        
        marker = "⭐ " if os.path.normcase(chosen) == os.path.normcase(self.selected_engine_dir) else "  "
        icon = "🖥" if 'ROCm' in eng.get('version', '') else "⚡"
        self.engine_tree.insert('', tk.END, text=f"{marker}{icon}  {eng['name']}", iid=eng['name'])
        
        self.engine_status_var.set(f"✅ 已添加：{name}")
    
    def engine_delete(self):
        """Remove engine from list (doesn't delete files)."""
        selection = self.engine_tree.selection()
        if not selection:
            return
        iid = selection[0]
        eng = self.engine_tree_items.get(iid)
        if not eng:
            return
        
        reply = Messagebox.yesno(
            f"确定将「{eng['name']}」移出列表？\n文件不会被删除。",
            "确认移除",
            parent=self.root
        )
        if not reply:
            return
        
        # Remove from data structures
        self.engine_dirs = [e for e in self.engine_dirs if e['name'] != eng['name']]
        if iid in self.engine_tree_items:
            del self.engine_tree_items[iid]
        self.engine_tree.delete(iid)
        
        # If it was the default, clear default
        if os.path.normcase(eng['dir']) == os.path.normcase(self.selected_engine_dir):
            self.selected_engine_dir = ""
            self.engine_status_var.set("⚠ 默认引擎已被移除，将使用系统 PATH 中的 llama-server")
        
        self._clear_engine_detail()
    
    def engine_open_folder(self):
        selection = self.engine_tree.selection()
        if not selection:
            return
        iid = selection[0]
        eng = self.engine_tree_items.get(iid)
        if eng and os.path.isdir(eng['dir']):
            try:
                os.startfile(eng['dir'])
            except Exception as e:
                Messagebox.show_error(f"打开目录失败：{e}", "错误", parent=self.root)
    
    def engine_get_path(self):
        """Get the full path to llama-server.exe for the selected engine.
        Returns None if using system PATH."""
        if self.selected_engine_dir:
            exe_path = os.path.join(self.selected_engine_dir, 'llama-server.exe')
            if os.path.isfile(exe_path):
                return exe_path
        return None

    # --- ModelScope Download Methods ---
    def _ms_get_repo_dir(self):
        """Parse repo ID and return the save directory path.
        E.g. 'unsloth/Qwen3.6-35B-A3B-GGUF' → 'models/unsloth/Qwen3.6-35B-A3B-GGUF/'
        """
        repo = self.ms_repo.get().strip()
        app_dir = os.path.dirname(self.get_config_path(''))
        # Replace / with \ for windows, normalize path
        safe_name = repo.replace('/', os.sep).replace('\\', os.sep)
        return os.path.join(app_dir, 'models', safe_name)
    
    def browse_ms_files(self):
        """Query ModelScope API to list GGUF files in the specified repo."""
        repo = self.ms_repo.get().strip()
        if not repo:
            Messagebox.show_error("请先输入 ModelScope 仓库 ID！", "输入错误")
            return
        
        self.browse_ms_btn.config(state=tk.DISABLED)
        self.ms_status_var.set("正在查询...")
        self.cancel_ms_btn.config(state=tk.DISABLED)
        # Clear checkbox frame
        for w in self.ms_file_checkframe.winfo_children():
            w.destroy()
        self.ms_file_vars.clear()
        self.download_ms_btn.config(state=tk.DISABLED)
        
        def fetch():
            try:
                url = f"https://www.modelscope.cn/api/v1/models/{repo}/repo/files"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                if not data.get('Success'):
                    err_msg = data.get('Message', '未知错误')
                    self.root.after(0, lambda: self._ms_fetch_complete(False, f"查询失败：{err_msg}"))
                    return
                
                files = data.get('Data', {}).get('Files', [])
                all_files = []
                for f in files:
                    if f.get('Type') != 'blob':
                        continue
                    name = f.get('Name', '')
                    is_gguf = name.endswith('.gguf')
                    is_mmproj = is_gguf and name.startswith('mmproj')
                    is_imatrix = 'imatrix' in name.lower()
                    if is_gguf or name.endswith('.gguf_file') or name.endswith('.txt'):
                        all_files.append({
                            'name': name,
                            'path': f.get('Path', name),
                            'size': f.get('Size', 0),
                            'type': 'mmproj' if is_mmproj else ('imatrix' if is_imatrix else 'model')
                        })
                
                # Sort: mmproj first, then models, then others
                def sort_key(x):
                    order = {'mmproj': 0, 'model': 1, 'imatrix': 2}
                    return (order.get(x['type'], 9), x['name'])
                all_files.sort(key=sort_key)
                self.root.after(0, lambda: self._ms_fetch_complete(True, all_files))
            except urllib.error.URLError as e:
                self.root.after(0, lambda: self._ms_fetch_complete(False, f"网络错误：{e.reason}"))
            except Exception as e:
                self.root.after(0, lambda: self._ms_fetch_complete(False, str(e)))
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def _ms_fetch_complete(self, success, result):
        self.browse_ms_btn.config(state=tk.NORMAL)
        # Clear previous
        for w in self.ms_file_checkframe.winfo_children():
            w.destroy()
        self.ms_file_vars.clear()
        
        if not success:
            self.ms_status_var.set(f"❌ {result}")
            return
        
        if not result:
            self.ms_status_var.set("⚠ 未找到模型文件")
            return
        
        model_count = sum(1 for f in result if f['type'] == 'model')
        mmproj_count = sum(1 for f in result if f['type'] == 'mmproj')
        
        # Auto-tick: find the first BF16 mmproj (fallback to F16)
        auto_tick_name = None
        for f in result:
            if f['type'] == 'mmproj':
                name_lower = f['name'].lower()
                if 'bf16' in name_lower:
                    auto_tick_name = f['name']
                    break
        if not auto_tick_name:
            for f in result:
                if f['type'] == 'mmproj':
                    auto_tick_name = f['name']
                    break
        
        # Build checkbox rows
        for f in result:
            var = tk.BooleanVar(value=False)
            size_str = self._format_size(f['size'])
            
            # Auto-tick mmproj
            if f['name'] == auto_tick_name:
                var.set(True)
            
            # Create row
            row = ttk.Frame(self.ms_file_checkframe)
            row.pack(fill=tk.X, padx=2, pady=1)
            
            cb = ttk.Checkbutton(row, variable=var, bootstyle="round-toggle")
            cb.pack(side=tk.LEFT)
            
            # Determine file type label for tooltip
            if f['type'] == 'mmproj':
                type_label = "多模态投影器"
            elif f['type'] == 'imatrix':
                type_label = "重要性矩阵"
            else:
                type_label = "主模型"
            ToolTip(cb, f"勾选以下载此{type_label} ({self._format_size(f['size'])})")
            
            # Icon + file info
            if f['type'] == 'mmproj':
                icon = "📷"
                type_tag = "  (多模态投影器)"
            elif f['type'] == 'imatrix':
                icon = "📊"
                type_tag = "  (重要性矩阵)"
            else:
                icon = "  "
                type_tag = ""
            
            info_text = f"{icon} {size_str:>10s}  {f['name']}{type_tag}"
            lbl = ttk.Label(row, text=info_text, font=("Consolas", 9), anchor=tk.W)
            lbl.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5, 0))
            
            self.ms_file_vars.append((var, f))
        
        # Enable download button if any files are checked
        self._ms_update_dl_button()
        
        status_parts = [f"✅ 找到 {model_count} 个模型"]
        if mmproj_count:
            status_parts.append(f"{mmproj_count} 个投影器")
        if auto_tick_name:
            status_parts.append("投影器已预勾选")
        self.ms_status_var.set(" | ".join(status_parts))
    
    def _ms_update_dl_button(self):
        """Enable download button if any checkbox is ticked."""
        has_checked = any(var.get() for var, _ in self.ms_file_vars)
        self.download_ms_btn.config(state=tk.NORMAL if has_checked else tk.DISABLED)
    
    def download_selected_ms_file(self):
        # Gather checked files
        files_to_dl = []
        for var, fi in self.ms_file_vars:
            if var.get():
                files_to_dl.append(fi)
        
        if not files_to_dl:
            Messagebox.show_error("请先勾选要下载的文件！", "提示")
            return
        
        repo = self.ms_repo.get().strip()
        repo_dir = self._ms_get_repo_dir()
        os.makedirs(repo_dir, exist_ok=True)
        
        # Check existing files
        for fi in files_to_dl:
            save_path = os.path.join(repo_dir, fi['name'])
            if os.path.exists(save_path):
                reply = Messagebox.yesno(
                    f"文件 {fi['name']} 已存在于\n{save_path}\n是否覆盖？",
                    "文件已存在",
                    parent=self.root
                )
                if not reply:
                    return
        
        # Setup cancel event
        self._ms_cancel_event = threading.Event()
        
        self.browse_ms_btn.config(state=tk.DISABLED)
        self.download_ms_btn.config(state=tk.DISABLED)
        self.cancel_ms_btn.config(state=tk.NORMAL)
        self.ms_progress['value'] = 0
        
        # Start download queue
        self._ms_dl_queue = list(files_to_dl)
        self._ms_dl_results = {}
        self._ms_dl_repo = repo
        self._ms_dl_dir = repo_dir
        
        self._download_next_in_queue()
    
    def cancel_ms_download(self):
        """Cancel the current download."""
        self._ms_cancel_event.set()
        self.cancel_ms_btn.config(state=tk.DISABLED)
        self.ms_progress_label.config(text="⏹ 正在取消...")
    
    def _download_next_in_queue(self):
        """Download the next file in the queue, or finish."""
        if self._ms_cancel_event.is_set():
            self._dl_cleanup_cancelled()
            return
        
        if not self._ms_dl_queue:
            self._all_downloads_done()
            return
        
        file_info = self._ms_dl_queue.pop(0)
        repo = self._ms_dl_repo
        filename = file_info['name']
        save_path = os.path.join(self._ms_dl_dir, filename)
        
        idx = len(self._ms_dl_results) + 1
        total = len(self._ms_dl_results) + len(self._ms_dl_queue) + 1
        self.ms_progress_label.config(text=f"({idx}/{total}) 正在下载 {filename}...")
        
        def download():
            try:
                url = f"https://www.modelscope.cn/models/{repo}/resolve/main/{file_info['path']}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=600) as resp:
                    total_size = int(resp.headers.get('Content-Length', 0))
                    chunk_size = 8 * 1024 * 1024
                    downloaded = 0
                    
                    with open(save_path + '.tmp', 'wb') as f:
                        while True:
                            if self._ms_cancel_event.is_set():
                                self.root.after(0, self._dl_cleanup_cancelled)
                                return  # cancelled
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                            downloaded += len(chunk)
                            if total_size > 0:
                                pct = int(downloaded * 100 / total_size)
                                self.root.after(0, lambda p=pct, d=downloaded, t=total_size, fn=filename:
                                    self._update_dl_progress(p, d, t, fn))
                
                # Rename .tmp to final name on success
                os.replace(save_path + '.tmp', save_path)
                self._ms_dl_results[file_info['type']] = save_path
                self.root.after(0, self._download_next_in_queue)
            except urllib.error.URLError as e:
                self.root.after(0, lambda: self._dl_queue_failed(f"网络错误：{e.reason}", save_path + '.tmp'))
            except Exception as e:
                self.root.after(0, lambda: self._dl_queue_failed(str(e), save_path + '.tmp'))
        
        threading.Thread(target=download, daemon=True).start()
    
    def _dl_cleanup_cancelled(self):
        """Clean up after user cancelled."""
        self.browse_ms_btn.config(state=tk.NORMAL)
        self.download_ms_btn.config(state=tk.NORMAL)
        self.cancel_ms_btn.config(state=tk.DISABLED)
        self.ms_progress['value'] = 0
        self.ms_progress_label.config(text="⏹ 已取消")
        self.ms_status_var.set("⏹ 下载已取消")
        # Clean up all completed files from this batch
        for fi_path in list(self._ms_dl_results.values()):
            if os.path.exists(fi_path):
                try:
                    os.remove(fi_path)
                except OSError:
                    pass
        # Clean up all .tmp files in the download directory
        if os.path.exists(self._ms_dl_dir):
            for fname in os.listdir(self._ms_dl_dir):
                if fname.endswith('.tmp'):
                    try:
                        os.remove(os.path.join(self._ms_dl_dir, fname))
                    except OSError:
                        pass
    
    def _dl_queue_failed(self, error_msg, partial_path):
        """Handle a download failure in the queue."""
        self._ms_cancel_event.set()  # Stop any queued downloads
        self.browse_ms_btn.config(state=tk.NORMAL)
        self.download_ms_btn.config(state=tk.NORMAL)
        self.cancel_ms_btn.config(state=tk.DISABLED)
        self.ms_progress['value'] = 0
        self.ms_progress_label.config(text=f"❌ 下载失败：{error_msg}")
        self.ms_status_var.set("❌ 下载失败")
        if os.path.exists(partial_path):
            try:
                os.remove(partial_path)
            except OSError:
                pass
        # Clean up already-downloaded files from this batch
        for fi_path in list(self._ms_dl_results.values()):
            if os.path.exists(fi_path):
                try:
                    os.remove(fi_path)
                except OSError:
                    pass
    
    def _update_dl_progress(self, pct, downloaded, total, filename):
        self.ms_progress['value'] = pct
        d = self._format_size(downloaded)
        t = self._format_size(total)
        self.ms_progress_label.config(text=f"{filename}  {d} / {t}  ({pct}%)")
    
    def _all_downloads_done(self):
        """All files in the queue have been downloaded."""
        self.browse_ms_btn.config(state=tk.NORMAL)
        self.download_ms_btn.config(state=tk.NORMAL)
        self.cancel_ms_btn.config(state=tk.DISABLED)
        self.ms_progress['value'] = 0
        
        model_path = self._ms_dl_results.get('model', '')
        mmproj_path = self._ms_dl_results.get('mmproj', '')
        
        # Build status message
        parts = []
        if model_path:
            self.model_path.set(model_path)
            parts.append(f"模型: {os.path.basename(model_path)}")
        if mmproj_path:
            self.mmproj_path.set(mmproj_path)
            parts.append(f"投影器: {os.path.basename(mmproj_path)}")
        if self._ms_dl_results.get('imatrix'):
            parts.append("(+重要性矩阵)")
        
        status = " | ".join(parts) if parts else "下载完成"
        self.ms_progress_label.config(text="✅ 全部下载完成！")
        self.ms_status_var.set(f"✅ {status}")
        
        # Show the save directory
        repo_dir = self._ms_get_repo_dir()
        self.ms_status_var.set(f"✅ 已保存至: {os.path.basename(os.path.dirname(repo_dir))}/{os.path.basename(repo_dir)}/")
        
        def show_msg():
            lines = []
            for fi_path in self._ms_dl_results.values():
                lines.append(f"  📄 {os.path.basename(fi_path)}")
            msg = "已下载文件：\n" + "\n".join(lines) + f"\n\n保存目录：{repo_dir}\n\n模型路径和投影器路径已自动填入。"
            Messagebox.ok(msg, "下载完成", parent=self.root)
        self.root.after(100, show_msg)
    
    @staticmethod
    def _format_size(bytes_val):
        if bytes_val < 1024:
            return f"{bytes_val}B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val/1024:.1f}KB"
        elif bytes_val < 1024 * 1024 * 1024:
            return f"{bytes_val/1024/1024:.1f}MB"
        else:
            return f"{bytes_val/1024/1024/1024:.2f}GB"

    # --- Draft Model Download Methods ---
    def draft_browse_files(self):
        """Query ModelScope API for draft model files."""
        repo = self.draft_ms_repo.get().strip()
        if not repo:
            Messagebox.show_error("请先输入草稿模型仓库 ID！", "输入错误")
            return
        
        self.draft_browse_btn.config(state=tk.DISABLED)
        self.draft_status_var.set("正在查询...")
        self.draft_listbox.delete(0, tk.END)
        self.draft_file_data.clear()
        self.draft_dl_btn.config(state=tk.DISABLED)
        
        def fetch():
            try:
                url = f"https://www.modelscope.cn/api/v1/models/{repo}/repo/files"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                files = data.get('Data', {}).get('Files', [])
                ggufs = []
                for f in files:
                    if f.get('Type') != 'blob':
                        continue
                    name = f.get('Name', '')
                    if name.endswith('.gguf') and not name.startswith('mmproj'):
                        ggufs.append({
                            'name': name, 'path': f.get('Path', name),
                            'size': f.get('Size', 0)
                        })
                ggufs.sort(key=lambda x: x['name'])
                self.root.after(0, lambda: self._draft_fetch_done(True, ggufs))
            except urllib.error.URLError as e:
                self.root.after(0, lambda: self._draft_fetch_done(False, f"网络错误：{e.reason}"))
            except Exception as e:
                self.root.after(0, lambda: self._draft_fetch_done(False, str(e)))
        
        threading.Thread(target=fetch, daemon=True).start()
    
    def _draft_fetch_done(self, success, result):
        self.draft_browse_btn.config(state=tk.NORMAL)
        if not success:
            self.draft_status_var.set(f"❌ {result}")
            return
        self.draft_file_data = result
        self.draft_listbox.delete(0, tk.END)
        if not result:
            self.draft_status_var.set("⚠ 未找到模型文件")
            return
        for f in result:
            size = self._format_size(f['size'])
            self.draft_listbox.insert(tk.END, f"{size:>10s}  {f['name']}")
        self.draft_status_var.set(f"✅ {len(result)} 个模型")
    
    def _on_draft_select(self, event):
        self.draft_dl_btn.config(state=tk.NORMAL if self.draft_listbox.curselection() else tk.DISABLED)
    
    def draft_download(self):
        selection = self.draft_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx >= len(self.draft_file_data):
            return
        
        file_info = self.draft_file_data[idx]
        repo = self.draft_ms_repo.get().strip()
        filename = file_info['name']
        
        # Save to same directory structure
        app_dir = os.path.dirname(self.get_config_path(''))
        safe_name = repo.replace('/', os.sep)
        dest_dir = os.path.join(app_dir, 'models', safe_name)
        os.makedirs(dest_dir, exist_ok=True)
        save_path = os.path.join(dest_dir, filename)
        
        if os.path.exists(save_path):
            reply = Messagebox.yesno(f"文件 {filename} 已存在。\n是否覆盖？", "文件已存在", parent=self.root)
            if not reply:
                return
        
        self.draft_browse_btn.config(state=tk.DISABLED)
        self.draft_dl_btn.config(state=tk.DISABLED)
        self.draft_status_var.set(f"正在下载 {filename}...")
        
        def download():
            try:
                url = f"https://www.modelscope.cn/models/{repo}/resolve/main/{file_info['path']}"
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=600) as resp:
                    chunk_size = 8 * 1024 * 1024
                    with open(save_path + '.tmp', 'wb') as f:
                        while True:
                            chunk = resp.read(chunk_size)
                            if not chunk:
                                break
                            f.write(chunk)
                    os.replace(save_path + '.tmp', save_path)
                self.root.after(0, lambda: self._draft_dl_done(True, save_path, filename))
            except urllib.error.URLError as e:
                self.root.after(0, lambda: self._draft_dl_done(False, f"网络错误：{e.reason}", filename))
            except Exception as e:
                self.root.after(0, lambda: self._draft_dl_done(False, str(e), filename))
        
        threading.Thread(target=download, daemon=True).start()
    
    def _draft_dl_done(self, success, result, filename):
        self.draft_browse_btn.config(state=tk.NORMAL)
        self.draft_dl_btn.config(state=tk.NORMAL)
        if not success:
            self.draft_status_var.set(f"❌ 下载失败：{result}")
            app_dir = os.path.dirname(self.get_config_path(''))
            partial = os.path.join(app_dir, 'models', self.draft_ms_repo.get().strip().replace('/', os.sep), filename + '.tmp')
            if os.path.exists(partial):
                try: os.remove(partial)
                except OSError: pass
            return
        
        # Auto-fill draft model path in the Advanced tab
        self.draft_model_path.set(result)
        self.draft_status_var.set(f"✅ {filename} 下载完成！已填入草稿模型路径。")
        
        def show_msg():
            Messagebox.ok(f"草稿模型已下载至：\n{result}\n\n已自动填入「草稿模型路径 (-md)」。\n\n前往「高级 → 推测解码」设置推测解码类型。", "下载完成", parent=self.root)
        self.root.after(100, show_msg)

    def _auto_fill_alias(self, force=False):
        """Auto-fill alias from the parent directory name of the current model path.
        force=True: always overwrite (used when loading from repo).
        force=False: only fill if alias is empty (used on startup path changes)."""
        path = self.model_path.get().strip()
        if not path:
            return
        parent_dir = os.path.basename(os.path.dirname(path))
        if parent_dir and (force or not self.alias.get().strip()):
            self.alias.set(parent_dir)

    def _auto_adjust_ctx_slider(self):
        """Read model's context length from GGUF header and adjust slider max."""
        path = self.model_path.get().strip()
        if not path or not os.path.isfile(path):
            return
        
        self._auto_fill_alias()
        
        meta = self._read_gguf_metadata(path)
        if not meta:
            return
        ctx = meta.get(f"{meta.get('general.architecture', '')}.context_length")
        if not ctx:
            ctx = meta.get('general.context_length')
        if ctx and isinstance(ctx, (int, float)) and ctx > 0:
            ctx = int(ctx)
            new_max = max(ctx, 131072)
            for key, refs in self.slider_refs.items():
                if '上下文大小' in key:
                    refs['slider'].configure(to=new_max)
                    if refs['var'].get() > ctx:
                        refs['var'].set(ctx)
                        self.update_slider_label(refs['var'], refs['label'], refs['resolution'])
                    break

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

    @staticmethod
    def _read_gguf_metadata(filepath):
        """Read basic GGUF metadata from the file header.
        Returns dict with architecture, context_length, file_type, etc."""
        import struct
        
        def read_string(f):
            """Read a GGUF string: length (uint64) + UTF-8 data."""
            length = struct.unpack('<Q', f.read(8))[0]
            return f.read(length).decode('utf-8', errors='replace')
        
        def read_value(f):
            """Read a GGUF value based on its type.
            Returns (key, value)."""
            val_type = struct.unpack('<I', f.read(4))[0]
            # GGUF value types
            TYPES = {0: 'UINT8', 1: 'INT8', 2: 'UINT16', 3: 'INT16',
                     4: 'UINT32', 5: 'INT32', 6: 'FLOAT32', 7: 'BOOL',
                     8: 'STRING', 9: 'ARRAY', 10: 'UINT64', 11: 'INT64',
                     12: 'FLOAT64', 13: 'BF16'}
            
            if val_type == 8:  # STRING
                return read_string(f)
            elif val_type == 7:  # BOOL
                return struct.unpack('<?', f.read(1))[0]
            elif val_type in (0, 1):  # UINT8, INT8
                return struct.unpack('<b', f.read(1))[0]
            elif val_type in (4, 5):  # UINT32, INT32
                return struct.unpack('<i', f.read(4))[0]
            elif val_type in (10, 11):  # UINT64, INT64
                return struct.unpack('<q', f.read(8))[0]
            elif val_type == 6:  # FLOAT32
                return struct.unpack('<f', f.read(4))[0]
            elif val_type == 12:  # FLOAT64
                return struct.unpack('<d', f.read(8))[0]
            elif val_type == 9:  # ARRAY - skip
                arr_type = struct.unpack('<I', f.read(4))[0]
                arr_len = struct.unpack('<Q', f.read(8))[0]
                for _ in range(arr_len):
                    if arr_type == 8:
                        read_string(f)
                    elif arr_type == 4:
                        f.read(4)
                    else:
                        f.read(8)
                return None
            else:
                return None
        
        try:
            with open(filepath, 'rb') as f:
                magic = f.read(4)
                if magic != b'GGUF':
                    return None
                
                version = struct.unpack('<I', f.read(4))[0]
                tensor_count = struct.unpack('<Q', f.read(8))[0]
                metadata_count = struct.unpack('<Q', f.read(8))[0]
                
                meta = {}
                for _ in range(min(metadata_count, 100)):
                    try:
                        key = read_string(f)
                        val = read_value(f)
                        if key and val is not None:  # filter to relevant keys only
                            meta[key] = val
                    except Exception:
                        break
                
                return meta
        except Exception:
            return None

    def _get_model_metadata_display(self, filepath):
        """Get a human-readable string of model metadata from GGUF header."""
        meta = self._read_gguf_metadata(filepath)
        if not meta:
            return "无法读取元信息"
        
        lines = []
        arch = meta.get('general.architecture', '')
        if arch:
            lines.append(f"架构: {arch}")
        
        # Context length - try architecture-specific keys
        ctx = meta.get(f'{arch}.context_length') if arch else None
        if not ctx:
            for k, v in meta.items():
                if 'context_length' in k:
                    ctx = v
                    break
        if ctx:
            lines.append(f"上下文: {ctx:,} tokens")
        
        ftype = meta.get('general.file_type', '')
        if ftype:
            type_names = {1: 'F32', 2: 'F16', 3: 'Q4_0', 5: 'Q4_1', 7: 'Q8_0', 
                         8: 'Q5_0', 9: 'Q5_1', 10: 'Q2_K', 12: 'Q3_K', 
                         13: 'Q4_K', 14: 'Q5_K', 15: 'Q6_K', 16: 'Q8_K'}
            lines.append(f"量化: {type_names.get(ftype, f'Type {ftype}')}")
        
        params = meta.get('general.size_label', '')
        if not params and arch:
            n_layer = meta.get(f'{arch}.block_count', 0)
            if n_layer:
                lines.append(f"层数: {n_layer}")
        
        name = meta.get('general.name', '')
        if name:
            lines.insert(0, f"模型: {name}")
        
        return " | ".join(lines) if lines else "基本元信息"


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
        
        # Use selected engine or fallback to PATH
        engine_path = self.engine_get_path()
        if engine_path:
            cmd = [engine_path, "-m", self.model_path.get().strip()]
        else:
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
            '--n-cpu-moe': self.moe_cpu_layers,
            '--reasoning-format': self.reasoning_format, '-ub': self.ubatch_size,
            '-n': self.n_predict, '--temp': self.temp, '--top-k': self.top_k,
            '--top-p': self.top_p, '--repeat-penalty': self.repeat_penalty,
            '--pooling': self.pooling,
            '--sleep-idle-seconds': self.sleep_idle,
            '-to': self.timeout,
            '--threads-batch': self.threads_batch,
            '--repeat-last-n': self.repeat_last_n,
            '--frequency-penalty': self.frequency_penalty,
            '--presence-penalty': self.presence_penalty,
            '--min-p': self.min_p,
            '--seed': self.seed,
            '--mirostat': self.mirostat,
            '--mirostat-lr': self.mirostat_lr,
            '--mirostat-ent': self.mirostat_ent,
            '--xtc-probability': self.xtc_probability,
            '--xtc-threshold': self.xtc_threshold,
            '--dynatemp-range': self.dynatemp_range,
            '--dynatemp-exp': self.dynatemp_exp,
            '--typical-p': self.typical_p,
            '--dry-multiplier': self.dry_multiplier,
            '--dry-base': self.dry_base,
            '--dry-allowed-length': self.dry_allowed_length,
            '--dry-penalty-last-n': self.dry_penalty_last_n,
            '--dry-sequence-breaker': self.dry_sequence_breaker,
            '--grammar-file': self.grammar_file,
            '--json-schema': self.json_schema,
            '--ssl-key-file': self.ssl_key_file,
            '--ssl-cert-file': self.ssl_cert_file,
            '--reasoning-budget': self.reasoning_budget,
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
            '--ignore-eos': self.ignore_eos,
            '--context-shift': self.context_shift
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
        self._health_check_active = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.browser_button.config(state=tk.NORMAL)
        self.server_status_var.set("⏳ 启动中...")
        self.server_status_label.config(foreground="orange")
        
        import time
        self._startup_start_time = time.perf_counter()
        if hasattr(self, '_startup_sec'):
            del self._startup_sec  # reset for new run
        
        # Capture connection info at launch time (thread-safe)
        health_host = self.host.get().strip()
        if health_host == '0.0.0.0': health_host = 'localhost'
        health_port = self.port.get().strip()
        
        # Start health check thread
        threading.Thread(target=self._health_check_loop, 
            args=(health_host, health_port), daemon=True).start()

    def stop_server(self):
        if self.server_process and self.is_running:
            try:
                self.server_process.terminate()
                self.update_output("\n" + "="*80 + "\n⏹️ 正在停止服务器...\n")
            except Exception as e:
                self.update_output(f"\n⚠ 停止服务器错误：{e}\n")

    def server_stopped(self):
        self.is_running = False
        self._health_check_active = False
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.browser_button.config(state=tk.DISABLED)
        self.server_status_var.set("⏹ 已停止")
        self.server_status_label.config(foreground="gray")
        self.update_output("\n" + "=" * 80 + "\n⏹️ 服务器进程已终止。\n" + "=" * 80 + "\n", tag="normal")

    def update_output(self, text, tag=None):
        """Append text to output with optional keyword highlighting.
        
        Lines matching known keywords are automatically colored:
        - error patterns -> red
        - speed/listening -> green
        - warnings -> orange
        - feature keywords -> blue
        - everything else -> gray
        If 'tag' is provided, the entire text block uses that single tag.
        """
        if tag:
            self.output_text.insert(tk.END, text, tag)
            self.output_text.see(tk.END)
            return
        
        import re
        # Split into lines to apply per-line coloring
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i > 0:
                self.output_text.insert(tk.END, "\n")
            if not line.strip():
                self.output_text.insert(tk.END, line)
                continue
            
            # Check against patterns (first match wins)
            matched = False
            lower = line.lower()
            for tag_name, patterns in self._log_patterns:
                for pat in patterns:
                    if re.search(pat, lower):
                        self.output_text.insert(tk.END, line, tag_name)
                        matched = True
                        break
                if matched:
                    break
            if not matched:
                self.output_text.insert(tk.END, line, "normal")
        
        self.output_text.see(tk.END)
    
    def _health_check_loop(self, host, port):
        """Periodically ping the server's health endpoint.
        Waits indefinitely for the model to load — no false timeout for large models."""
        import time
        url = f"http://{host}:{port}/health"
        
        # Phase 1: Quick retry (every 1s, first 30 attempts)
        for attempt in range(1, 31):
            if not self.is_running:
                return
            try:
                req = urllib.request.Request(url)
                start = time.time()
                with urllib.request.urlopen(req, timeout=2) as resp:
                    elapsed = int((time.time() - start) * 1000)
                    if resp.status == 200:
                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                        # Continue monitoring (phase 3)
                        while self.is_running:
                            time.sleep(5)
                            try:
                                req = urllib.request.Request(url)
                                start = time.time()
                                with urllib.request.urlopen(req, timeout=2) as resp:
                                    elapsed = int((time.time() - start) * 1000)
                                    if resp.status == 200:
                                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                            except Exception:
                                self.root.after(0, self._set_server_unhealthy)
                                time.sleep(3)
                        return
            except Exception:
                if attempt == 1:
                    self.root.after(0, lambda: self.server_status_var.set("⏳ 启动中…"))
                time.sleep(1)
        
        # Phase 2: Extended wait — model is still loading (every 3s)
        self.root.after(0, lambda: self.server_status_var.set("⏳ 启动中（模型加载中…）"))
        while self.is_running:
            time.sleep(3)
            try:
                req = urllib.request.Request(url)
                start = time.time()
                with urllib.request.urlopen(req, timeout=5) as resp:
                    elapsed = int((time.time() - start) * 1000)
                    if resp.status == 200:
                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                        # Enter monitoring phase
                        while self.is_running:
                            time.sleep(5)
                            try:
                                req = urllib.request.Request(url)
                                start = time.time()
                                with urllib.request.urlopen(req, timeout=2) as resp:
                                    elapsed = int((time.time() - start) * 1000)
                                    if resp.status == 200:
                                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                            except Exception:
                                self.root.after(0, self._set_server_unhealthy)
                                time.sleep(3)
                        return
            except Exception:
                pass
        # Process stopped while waiting
        self.root.after(0, lambda: self.server_status_var.set("⏹ 已停止"))
    
    def _set_server_healthy(self, response_ms):
        import time
        self.server_status_label.config(foreground="green")
        # Only record startup time on the very first health check success
        if not hasattr(self, '_startup_sec'):
            if hasattr(self, '_startup_start_time'):
                self._startup_sec = int(time.perf_counter() - self._startup_start_time)
            else:
                self._startup_sec = None
            if self._startup_sec is not None:
                self.update_output(f"✓ 服务器就绪！启动耗时 {self._startup_sec}s\n", tag="speed")
                self.server_status_var.set(f"✓ 运行中 ({response_ms}ms) · 启动耗时 {self._startup_sec}s")
                return
        self.server_status_var.set(f"✓ 运行中 ({response_ms}ms)")
    
    def _set_server_unhealthy(self):
        self.server_status_var.set("⚠ 连接中断")
        self.server_status_label.config(foreground="red")

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
            'spec_type': self.spec_type.get(), 'spec_draft_n_min': self.spec_draft_n_min.get(),
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
            'engine_dir': self.selected_engine_dir,
            'model_repo_roots': [r for r in self.model_repo_roots if not r.get('builtin')],
            'cache_type_k': self.cache_type_k.get(), 'cache_type_v': self.cache_type_v.get(),
            'mirostat': self.mirostat.get(), 'mirostat_lr': self.mirostat_lr.get(),
            'mirostat_ent': self.mirostat_ent.get(),
            'xtc_probability': self.xtc_probability.get(), 'xtc_threshold': self.xtc_threshold.get(),
            'dynatemp_range': self.dynatemp_range.get(), 'dynatemp_exp': self.dynatemp_exp.get(),
            'typical_p': self.typical_p.get(),
            'dry_multiplier': self.dry_multiplier.get(), 'dry_base': self.dry_base.get(),
            'dry_allowed_length': self.dry_allowed_length.get(),
            'dry_penalty_last_n': self.dry_penalty_last_n.get(),
            'dry_sequence_breaker': self.dry_sequence_breaker.get(),
            'grammar_file': self.grammar_file.get(), 'json_schema': self.json_schema.get(),
            'ssl_key_file': self.ssl_key_file.get(), 'ssl_cert_file': self.ssl_cert_file.get(),
            'reasoning_budget': self.reasoning_budget.get(),
            'context_shift': self.context_shift.get()
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
            self.spec_type.set(config.get('spec_type', ''))
            self.spec_draft_n_min.set(config.get('spec_draft_n_min', ''))
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
            self.repeat_last_n.set(config.get('repeat_last_n', ''))
            self.frequency_penalty.set(config.get('frequency_penalty', ''))
            self.presence_penalty.set(config.get('presence_penalty', ''))
            self.min_p.set(config.get('min_p', ''))
            self.seed.set(config.get('seed', ''))
            self.mirostat.set(config.get('mirostat', ''))
            self.mirostat_lr.set(config.get('mirostat_lr', ''))
            self.mirostat_ent.set(config.get('mirostat_ent', ''))
            self.xtc_probability.set(config.get('xtc_probability', ''))
            self.xtc_threshold.set(config.get('xtc_threshold', ''))
            self.dynatemp_range.set(config.get('dynatemp_range', ''))
            self.dynatemp_exp.set(config.get('dynatemp_exp', ''))
            self.typical_p.set(config.get('typical_p', ''))
            self.dry_multiplier.set(config.get('dry_multiplier', ''))
            self.dry_base.set(config.get('dry_base', ''))
            self.dry_allowed_length.set(config.get('dry_allowed_length', ''))
            self.dry_penalty_last_n.set(config.get('dry_penalty_last_n', ''))
            self.dry_sequence_breaker.set(config.get('dry_sequence_breaker', ''))
            self.grammar_file.set(config.get('grammar_file', ''))
            self.json_schema.set(config.get('json_schema', ''))
            self.ssl_key_file.set(config.get('ssl_key_file', ''))
            self.ssl_cert_file.set(config.get('ssl_cert_file', ''))
            self.reasoning_budget.set(config.get('reasoning_budget', ''))
            self.context_shift.set(config.get('context_shift', False))
            # Load cache type settings (default: none / empty)
            try:
                self.cache_type_k.set(config.get('cache_type_k', ''))
            except Exception:
                self.cache_type_k.set('')
            try:
                self.cache_type_v.set(config.get('cache_type_v', ''))
            except Exception:
                self.cache_type_v.set('')
            
            # Restore engine selection
            eng_dir = config.get('engine_dir', '')
            if eng_dir and os.path.isdir(eng_dir) and os.path.isfile(os.path.join(eng_dir, 'llama-server.exe')):
                self.selected_engine_dir = eng_dir
            
            # Restore custom model repo roots
            saved_roots = config.get('model_repo_roots', [])
            if saved_roots and hasattr(self, 'model_repo_roots'):
                for r in saved_roots:
                    if os.path.isdir(r.get('path', '')):
                        r['builtin'] = False
                        self.model_repo_roots.append(r)
                        if 'label' not in r:
                            r['label'] = os.path.basename(r['path'])
            
            # Update pointer to currently-loaded config
            self.config_file = load_path

            self.update_all_sliders()
            
            # Sync config dropdown to show the loaded config name
            configs_dir = self._get_configs_dir()
            try:
                rel = os.path.relpath(load_path, configs_dir)
                if rel.endswith('.json'):
                    self.config_combo.set(rel[:-5])
            except (ValueError, OSError):
                pass
            
            # Refresh model repo tree (custom roots may have changed)
            if hasattr(self, 'scan_downloaded_models'):
                self.scan_downloaded_models()
            # Refresh engine list to show correct default engine marker
            if hasattr(self, 'scan_engines'):
                self.scan_engines()
        except Exception as e:
            Messagebox.show_error(f"加载配置失败： {e}", "错误")
    
    # --- 配置管理 (Named Configs) ---
    def _get_configs_dir(self):
        app_dir = os.path.dirname(self.get_config_path(''))
        return os.path.join(app_dir, 'configs')
    
    def _refresh_config_list(self):
        """Scan configs/ directory and update the dropdown."""
        configs_dir = self._get_configs_dir()
        os.makedirs(configs_dir, exist_ok=True)
        names = []
        for f in sorted(os.listdir(configs_dir)):
            if f.endswith('.json'):
                name = f[:-5]  # remove .json
                names.append(name)
        self.config_combo['values'] = names
    
    def _on_config_select(self, event):
        """Auto-load the selected named config."""
        name = self.config_combo.get()
        if not name:
            return
        configs_dir = self._get_configs_dir()
        path = os.path.join(configs_dir, name + '.json')
        if os.path.isfile(path):
            self.load_config(path=path)
            # Refresh config list (might have updated from another session)
            self._refresh_config_list()
    
    def save_named_config(self):
        """Save current settings as a named config."""
        name = self.config_combo.get().strip()
        if not name:
            # Ask for a new name
            dialog = ttk.Toplevel(self.root)
            dialog.title("保存配置")
            dialog.geometry("350x130")
            dialog.transient(self.root)
            dialog.grab_set()
            
            ttk.Label(dialog, text="配置名称:", padding="10 10 0 5").pack(anchor=tk.W)
            name_var = tk.StringVar()
            entry = ttk.Entry(dialog, textvariable=name_var, width=30)
            entry.pack(padx=10, pady=5, fill=tk.X)
            entry.focus_set()
            
            def do_save():
                n = name_var.get().strip()
                if n:
                    dialog.destroy()
                    self._do_save_named(n)
                else:
                    Messagebox.show_error("名称不能为空！", "错误", parent=dialog)
            
            def on_key(e):
                if e.keysym == 'Return':
                    do_save()
                elif e.keysym == 'Escape':
                    dialog.destroy()
            
            entry.bind('<Return>', on_key)
            entry.bind('<Escape>', on_key)
            btn_frame = ttk.Frame(dialog)
            btn_frame.pack(pady=10)
            ttk.Button(btn_frame, text="确定", command=do_save, bootstyle="success").pack(side=tk.LEFT, padx=5)
            ttk.Button(btn_frame, text="取消", command=dialog.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=5)
        else:
            self._do_save_named(name)
    
    def _do_save_named(self, name):
        """Save config with the given name."""
        if not name:
            return
        configs_dir = self._get_configs_dir()
        path = os.path.join(configs_dir, name + '.json')
        self.save_config(path=path)
        self._refresh_config_list()
        self.config_combo.set(name)
    
    def delete_named_config(self):
        """Delete the currently selected named config."""
        name = self.config_combo.get().strip()
        if not name:
            Messagebox.show_warning("请先在配置下拉框中选择要删除的配置。", "提示")
            return
        reply = Messagebox.yesno(
            f"确定删除配置「{name}」？\n此操作不可撤销。",
            "确认删除",
            parent=self.root
        )
        if not reply:
            return
        
        configs_dir = self._get_configs_dir()
        path = os.path.join(configs_dir, name + '.json')
        try:
            os.remove(path)
            self._refresh_config_list()
            self.config_combo.set('')
            Messagebox.ok(f"配置「{name}」已删除。", "删除成功", parent=self.root)
        except Exception as e:
            Messagebox.show_error(f"删除失败：{e}", "错误", parent=self.root)

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