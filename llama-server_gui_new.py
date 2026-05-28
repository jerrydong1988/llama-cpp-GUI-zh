import sys
import tkinter as tk
import ttkbootstrap as ttk
from ttkbootstrap.dialogs import Messagebox
from ttkbootstrap.scrolled import ScrolledText, ScrolledFrame
from ttkbootstrap.tooltip import ToolTip
from tkinter import filedialog

import subprocess
import threading
import shlex
import os
import json
import webbrowser
import urllib.request
import urllib.error
import time
import re
from functools import lru_cache
from collections import deque
import signal
import locale

try:
    import pystray
    from pystray import MenuItem as item
    from PIL import Image
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False

# Application version
__version__ = "1.9.1"

class LlamaServerGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("LLaMA 服务器管理器")
        self.root.geometry("1080x720")
        self.root.minsize(1080, 720)

        # Server process management
        self.is_running = False
        # System encoding for subprocess output decoding (cross-platform)
        self._sys_encoding = locale.getpreferredencoding() or 'utf-8'

        # System tray setup
        self.tray_icon = None
        self.is_in_tray = False

        # Use user's directory for portable config file in configs/ subdirectory
        self.config_file = self._get_configs_path("instances.json")
        
        # ModelScope download root (empty = default: {app_dir}/models/)
        self.ms_download_root = ""
        
        # Theme state
        self.current_theme = "darkly"
        self._theme_btn = None  # reference for toggle button

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

        # Embedding mode support — must init before setup_ui (which creates tabs)
        self._embedding_frames = []
        self._param_frames = []
        # Multi-instance management
        self._instances = {}
        self._instances_lock = threading.Lock()
        self._active_instance_id = ""
        self._is_switching = False
        self._instance_logs = {}
        self.setup_ui()
        self.load_config()
        # Auto-migrate from single to multi-instance if needed
        if not self._instances:
            self._migrate_single_to_instance()
        if self._instances and not os.path.exists(self.config_file):
            self._auto_save_instances()
        self.root.after(1000, self._restore_running_instances)
        
        # Auto-adjust context slider when model path changes (debounced)
        self._ctx_slider_timer = None
        self._emb_mode_timer = None
        def on_model_path_change(*_):
            if self._ctx_slider_timer:
                self.root.after_cancel(self._ctx_slider_timer)
            self._ctx_slider_timer = self.root.after(500, self._auto_adjust_ctx_slider)
            if self._emb_mode_timer:
                self.root.after_cancel(self._emb_mode_timer)
            self._emb_mode_timer = self.root.after(300, self._check_embedding_mode)
        self.model_path.trace_add('write', on_model_path_change)
        # Also trigger on startup (if model already loaded)
        self.root.after(600, self._auto_adjust_ctx_slider)
        self.root.after(800, self._check_embedding_mode)

    def get_config_path(self, filename):
        """Get the path for config file that works with PyInstaller."""
        return os.path.join(self._get_app_dir(), filename)

    def _get_app_dir(self):
        """Application root directory (where exe lives)."""
        if getattr(sys, 'frozen', False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_configs_path(self, filename):
        """Get path for a config file in the configs/ subdirectory."""
        d = os.path.join(self._get_app_dir(), 'configs')
        os.makedirs(d, exist_ok=True)
        return os.path.join(d, filename)

    def _is_windows(self):
        return os.name == 'nt'

    def _exe_name(self, base="llama-server"):
        return base + (".exe" if self._is_windows() else "")

    def _open_file_explorer(self, path):
        try:
            if self._is_windows():
                os.startfile(path)
            elif sys.platform == 'darwin':
                subprocess.run(['open', path], check=False)
            else:
                subprocess.run(['xdg-open', path], check=False)
        except Exception as e:
            Messagebox.show_error(f"打开目录失败：{e}", "错误", parent=self.root)

    def _startupinfo(self):
        if self._is_windows():
            si = subprocess.STARTUPINFO()
            si.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            return si
        return None

    # ── 统一参数注册表 (单一数据源，取代 generate_command/save_config/load_config 三处重复) ──
    # format: (config_key, attr_name, cli_flag, kind, default)
    _PARAM_DEFS = [
        ("model_path",    "model_path",    "-m",         "str",  ""),
        ("alias",         "alias",         "-a",         "str",  ""),
        ("lora_path",     "lora_path",     "--lora",     "str",  ""),
        ("mmproj_path",   "mmproj_path",   "--mmproj",   "str",  ""),
        ("chat_template", "chat_template", "--chat-template", "str", ""),
        ("reasoning_format","reasoning_format","--reasoning-format","str",""),
        ("reasoning_effort","reasoning_effort","--reasoning-effort","str",""),
        ("reasoning",     "reasoning",     "--reasoning","str",  ""),
        ("jinja",         "jinja",         "--jinja",    "bool", False),
        ("reasoning_budget","reasoning_budget","--reasoning-budget","str",""),
        ("ctx_size",      "ctx_size",      "-c",         "int",  4096),
        ("gpu_layers",    "gpu_layers",    "-ngl",       "int",  99),
        ("threads",       "threads",       "-t",         "str",  ""),
        ("batch_size",    "batch_size",    "-b",         "str",  ""),
        ("ubatch_size",   "ubatch_size",   "-ub",        "str",  ""),
        ("parallel",      "parallel",      "-np",        "str",  ""),
        ("cont_batching", "cont_batching", "-cb",        "bool", False),
        ("cache_prompt",  "cache_prompt",  "--cache-prompt", "bool", True),
        ("threads_batch", "threads_batch", "--threads-batch", "str", ""),
        ("flash_attn",    "flash_attn",    "-fa",        "str",  "auto"),
        ("moe_cpu_layers","moe_cpu_layers","--n-cpu-moe","str",  ""),
        ("mlock",         "mlock",         "--mlock",    "bool", False),
        ("no_mmap",       "no_mmap",       "--no-mmap",  "bool", False),
        ("numa",          "numa",          "--numa",     "bool", False),
        ("cache_type_k",  "cache_type_k",  "-ctk",       "str",  ""),
        ("cache_type_v",  "cache_type_v",  "-ctv",       "str",  ""),
        ("draft_model_path","draft_model_path","-md",    "str",  ""),
        ("draft_gpu_layers","draft_gpu_layers","-ngld",  "str",  ""),
        ("draft_tokens",  "draft_tokens",  "--spec-draft-n-max","str",""),
        ("spec_draft_n_min","spec_draft_n_min","--spec-draft-n-min","str",""),
        ("spec_type",     "spec_type",     "--spec-type","str",  ""),
        ("host",          "host",          "--host",     "str",  "127.0.0.1"),
        ("port",          "port",          "--port",     "str",  "8080"),
        ("api_key",       "api_key",       "--api-key",  "str",  ""),
        ("ssl_key_file",  "ssl_key_file",  "--ssl-key-file","str",""),
        ("ssl_cert_file", "ssl_cert_file", "--ssl-cert-file","str",""),
        ("no_ui",         "no_ui",         "--no-ui",    "bool", False),
        ("embedding",     "embedding",     "--embedding","bool", False),
        ("pooling",       "pooling",       "--pooling",  "str",  ""),
        ("reranking",     "reranking",     "--reranking","bool", False),
        ("verbose",       "verbose",       "-v",         "bool", False),
        ("timeout",       "timeout",       "-to",        "str",  ""),
        ("sleep_idle",    "sleep_idle",    "--sleep-idle-seconds","str",""),
        ("context_shift", "context_shift", "--context-shift","bool",False),
        ("n_predict",     "n_predict",     "-n",         "str",  ""),
        ("ignore_eos",    "ignore_eos",    "--ignore-eos","bool", False),
        ("json_schema",   "json_schema",   "--json-schema","str", ""),
        ("grammar_file",  "grammar_file",  "--grammar-file","str",""),
        ("temp",          "temp",          "--temp",     "str",  ""),
        ("top_k",         "top_k",         "--top-k",    "str",  ""),
        ("top_p",         "top_p",         "--top-p",    "str",  ""),
        ("repeat_penalty","repeat_penalty","--repeat-penalty","str",""),
        ("seed",          "seed",          "--seed",     "str",  ""),
        ("min_p",         "min_p",         "--min-p",    "str",  ""),
        ("presence_penalty","presence_penalty","--presence-penalty","str",""),
        ("frequency_penalty","frequency_penalty","--frequency-penalty","str",""),
        ("repeat_last_n", "repeat_last_n", "--repeat-last-n","str",""),
        ("mirostat",      "mirostat",      "--mirostat", "str",  ""),
        ("mirostat_lr",   "mirostat_lr",   "--mirostat-lr","str", ""),
        ("mirostat_ent",  "mirostat_ent",  "--mirostat-ent","str",""),
        ("xtc_probability","xtc_probability","--xtc-probability","str",""),
        ("xtc_threshold", "xtc_threshold", "--xtc-threshold","str",""),
        ("dynatemp_range","dynatemp_range","--dynatemp-range","str",""),
        ("dynatemp_exp",  "dynatemp_exp",  "--dynatemp-exp","str",""),
        ("typical_p",     "typical_p",     "--typical-p","str",  ""),
        ("dry_multiplier","dry_multiplier","--dry-multiplier","str",""),
        ("dry_base",      "dry_base",      "--dry-base", "str",  ""),
        ("dry_allowed_length","dry_allowed_length","--dry-allowed-length","str",""),
        ("dry_penalty_last_n","dry_penalty_last_n","--dry-penalty-last-n","str",""),
        ("dry_sequence_breaker","dry_sequence_breaker","--dry-sequence-breaker","str",""),
    ]

    # Parameters not auto-generated in generate_command (handled individually)
    _SPECIAL_PARAMS = {"model_path", "ctx_size", "gpu_layers", "flash_attn",
                       "reasoning_effort", "cache_prompt", "numa"}

    # ── Embedding mode --------------------------------------------------------
    # Param keys (from _PARAM_DEFS) to skip in generate_command when --embedding is on
    _EMBEDDING_SKIP_PARAMS = frozenset({
        'lora_path', 'mmproj_path', 'grammar_file',
        'chat_template', 'reasoning_format',
        'reasoning', 'jinja', 'reasoning_budget',
        'n_predict', 'ignore_eos', 'json_schema',
        'temp', 'top_k', 'top_p', 'repeat_penalty', 'min_p',
        'presence_penalty', 'frequency_penalty', 'repeat_last_n',
        'seed', 'mirostat',
        'draft_model_path', 'draft_gpu_layers', 'draft_tokens',
        'spec_draft_n_min', 'spec_type',
        'moe_cpu_layers',
        'context_shift',
    })

    @staticmethod
    def _set_state_recursive(widget, state):
        """Recursively enable/disable a widget tree."""
        try:
            widget.config(state=state)
        except tk.TclError:
            pass
        for child in widget.winfo_children():
            LlamaServerGUI._set_state_recursive(child, state)

    def _set_embedding_mode(self, enabled: bool):
        """Enable/disable UI controls for embedding mode."""
        state = tk.DISABLED if enabled else tk.NORMAL

        # 1. Embedding checkbox itself — auto-set + lock
        self.embedding.set(enabled)
        if hasattr(self, 'embedding_cb') and self.embedding_cb:
            self.embedding_cb.config(state=tk.DISABLED if enabled else tk.NORMAL)

        # 2. Pooling: auto-recommend
        if enabled and hasattr(self, 'pooling') and not self.pooling.get():
            self.pooling.set('mean')

        # 3. Toggle registered Labelframes
        for frame in self._embedding_frames:
            try:
                self._set_state_recursive(frame, state)
                frame.config(text=frame['text'].replace(' 🛑', '') + (' 🛑' if enabled else ''))
            except Exception:
                pass

        # 4b. MoE CPU layers — single widget inside a shared frame
        moe_spin = getattr(self, 'moe_cpu_layers_spin', None)
        if moe_spin:
            try:
                moe_spin.config(state=state)
            except tk.TclError:
                pass

        # 5. Status indicator in server tab
        if hasattr(self, '_embedding_status') and self._embedding_status:
            if enabled:
                self._embedding_status.config(
                    text="📊 Embedding Mode 已激活 — 采样/推测解码/对话行为等生成参数已自动禁用，仅向量模型相关的参数可配置。取消勾选 ──embedding 可恢复",
                    bootstyle="info")
                self._embedding_status.pack(fill=tk.X, pady=(0, 5))
            else:
                self._embedding_status.pack_forget()

    def _check_embedding_mode(self):
        """Check current model path and update embedding mode."""
        path = self.model_path.get().strip()
        if path:
            is_emb = self._is_embedding_model(filepath=path, fname=os.path.basename(path))
            self._set_embedding_mode(is_emb)
        else:
            self._set_embedding_mode(False)

    def _get_var(self, attr_name):
        return getattr(self, attr_name, None)

    def _params_to_dict(self):
        """Build a config dict from all registered parameters (replaces save_config repetition)."""
        d = {}
        for ck, an, flag, kind, default in self._PARAM_DEFS:
            var = self._get_var(an)
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

    def _params_from_dict(self, config):
        """Restore parameters from a config dict (replaces load_config repetition)."""
        for ck, an, flag, kind, default in self._PARAM_DEFS:
            var = self._get_var(an)
            if var is None:
                continue
            val = config.get(ck, default)
            if kind == "bool":
                var.set(bool(val))
            elif kind == "int":
                try:
                    v = int(val)
                    var.set(v)
                except (ValueError, TypeError):
                    var.set(default)
            else:
                var.set(str(val) if val is not None else str(default))

    def setup_ui(self):
        """Sets up the main UI: sidebar navigation + content panels + bottom bar."""
        # ── Theme (dark) ──
        self.root.style.theme_use("darkly")
        
        # ── Top Header Bar ──
        header = ttk.Frame(self.root, padding="10 8")
        header.pack(fill=tk.X)
        ttk.Label(header, text="🔧 LLaMA 服务器管理器", font=("", 14, "bold")).pack(side=tk.LEFT)
        ttk.Label(header, text=f"v{__version__}", foreground="gray", font=("", 9)).pack(side=tk.LEFT, padx=(8, 0))
        
        # Theme toggle button (right side)
        theme_frame = ttk.Frame(header)
        theme_frame.pack(side=tk.RIGHT)
        self._theme_btn = ttk.Button(theme_frame, text="☀ 明亮", command=self.toggle_theme,
            bootstyle="secondary-link", takefocus=False)
        self._theme_btn.pack()
        
        # ── Main: Sidebar + Content ──
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 0))
        
        # Left: Sidebar navigation (narrow)
        sidebar = ttk.Frame(main_frame, width=180)
        sidebar.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 8))
        sidebar.pack_propagate(False)
        
        # Sidebar header
        ttk.Label(sidebar, text="导航", font=("", 9, "bold")).pack(anchor=tk.W, padx=5, pady=(0, 8))
        
        # Navigation tree
        self.nav_tree = ttk.Treeview(sidebar, columns=(), show='tree', selectmode='browse', height=20)
        self.nav_tree.pack(fill=tk.BOTH, expand=True)
        
        # Define sections: (iid, text, parent, setup_method, pack_direction)
        self._nav_sections = {}
        sections = [
            ("instances", "📋 实例管理", "", "setup_instance_tab", "pack"),
            ("repo",      "🏪 模型仓库",       "",              "setup_model_repo_tab",         "grid"),
            ("engine",    "🖥 引擎管理",       "",              "setup_engine_tab",             "grid"),
            ("models",    "📁 模型与参数",    "",              "setup_model_tab",              "pack"),
            ("gen",       "⚙️ 生成参数",      "",              "setup_generation_tab",         "pack"),
            ("perf",      "🚀 性能",          "",              "setup_performance_core_tab",   "pack"),
            ("advanced",  "🔬 高级",          "",              "setup_performance_advanced_tab","pack"),
            ("api",       "🌐 网络与API",     "",              "setup_server_api_tab",         "grid"),
            ("output",    "📊 服务器输出",     "",              "setup_output_tab",             "pack"),
        ]
        
        for iid, text, parent, method, _ in sections:
            self.nav_tree.insert(parent, tk.END, iid=iid, text=text)
        
        self.nav_tree.bind("<<TreeviewSelect>>", self._on_nav_select)
        # Refresh instance display after UI is fully set up
        self.root.after(150, self._refresh_instance_tree)
        self.root.after(250, self._sync_bottom_bar_for_active_instance)
        
        # Right: Content area (panels stacked, one visible at a time)
        self.content_frame = ttk.Frame(main_frame)
        self.content_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Create all content panels (initially hidden)
        self._panels = {}
        for iid, text, parent, method, _ in sections:
            panel = ttk.Frame(self.content_frame, padding="10")
            self._panels[iid] = panel
            # Populate via the original setup method
            getattr(self, method)(panel)
        
        # Collect Labelframes from parameter tabs for run-lock
        self._param_frames = []
        for pid in ('models', 'gen', 'perf', 'advanced', 'api'):
            if pid not in self._panels:
                continue
            panel = self._panels[pid]
            stack = [panel]
            while stack:
                child = stack.pop()
                for c in child.winfo_children():
                    if isinstance(c, ttk.Labelframe):
                        self._param_frames.append(c)
                    stack.append(c)
        
        # Show first panel by default
        first_iid = 'instances'  # Show instance panel by default
        self.nav_tree.selection_set(first_iid)
        self._show_panel(first_iid)
        
        # ── Bottom: Fixed control bar ──
        bottom_bar = ttk.Frame(self.root, padding="10 10")
        bottom_bar.pack(side=tk.BOTTOM, fill=tk.X)
        
        # Left: generate command
        left_grp = ttk.Frame(bottom_bar)
        left_grp.pack(side=tk.LEFT)
        self.create_button(left_grp, "⚡ 生成命令", self.show_command, "显示当前实例的完整 llama-server 命令行。", bootstyle="info")
        
        # Right: start/stop/browser
        right_grp = ttk.Frame(bottom_bar)
        right_grp.pack(side=tk.RIGHT)
        self.server_status_var = tk.StringVar(value="")
        self.server_status_label = ttk.Label(right_grp, textvariable=self.server_status_var,
            font=("", 9), foreground="gray")
        self.server_status_label.pack(side=tk.LEFT, padx=(0, 8))
        self.browser_button = self.create_button(right_grp, "打开浏览器 🌐", self.open_browser,
            "打开服务器 API 页面。新版 llama.cpp 已无内置聊天界面，推荐使用外部客户端连接。", state=tk.DISABLED, bootstyle="primary-outline")
        self.stop_button = self.create_button(right_grp, "停止 ⏹", self.stop_server,
            "停止服务器。", state=tk.DISABLED, bootstyle="danger")
        self.start_button = self.create_button(right_grp, "▶ 启动", self.start_server,
            "启动当前实例。运行后参数面板将自动锁定。", bootstyle="success")
        
        self.root.bind('<Control-s>', lambda e: self._auto_save_instances())
        # Sync download dir display after UI is set up
        self.root.after(50, self._sync_dl_dir_display)
        self.root.bind('<Control-Shift-S>', lambda e: self.start_server() if not self.is_running else None)
    
    def _on_nav_select(self, event):
        selection = self.nav_tree.selection()
        if selection:
            panel_id = selection[0]
            self._show_panel(panel_id)
            # Refresh instance tree whenever navigating to it
            if panel_id == "instances" and hasattr(self, '_refresh_instance_tree'):
                self._refresh_instance_tree()
                inst = self._instances.get(self._active_instance_id)
                if inst and hasattr(self, '_set_run_lock'):
                    self._set_run_lock(inst.get("is_running", False))
    
    def _show_panel(self, iid):
        """Show the selected content panel, hide all others."""
        for name, panel in self._panels.items():
            if name == iid:
                panel.pack(fill=tk.BOTH, expand=True)
            else:
                panel.pack_forget()
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
        self._embedding_frames.append(ext_group)
        self._embedding_frames.append(chat_group)
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
        # Scrollable wrapper to prevent bottom bar being pushed off-screen
        sf = ScrolledFrame(parent, autohide=True)
        sf.pack(fill=tk.BOTH, expand=True)
        
        # --- Output Control ---
        output_group = ttk.Labelframe(sf, text="输出控制", padding="10")
        self._embedding_frames.append(output_group)
        output_group.pack(fill=tk.X, pady=5, side=tk.TOP)
        
        self.n_predict = tk.StringVar(value="")
        self.create_spinbox(output_group, "生成令牌数 (-n, --n-predict):", self.n_predict, "生成的令牌数（默认 -1 = 无限）。", from_=-1, to=131072, increment=1, row=0)
        
        self.ignore_eos = tk.BooleanVar(value=False)
        self.create_checkbutton(output_group, "忽略结束标记 (--ignore-eos)", self.ignore_eos, "防止模型提前停止。", row=1)
        self.json_schema = tk.StringVar(value="")
        self.create_entry(output_group, "JSON 约束 (--json-schema):", self.json_schema, "JSON Schema 约束，限制输出为合法 JSON 格式。", row=2)
        
        # --- Sampling Parameters ---
        sampling_group = ttk.Labelframe(sf, text="采样参数", padding="10")
        self._embedding_frames.append(sampling_group)
        sampling_group.pack(fill=tk.X, pady=5)
        
        # Side-by-side layout: basic params on left, advanced on right
        left_frame = ttk.Frame(sampling_group)
        right_frame = ttk.Frame(sampling_group)
        left_frame.grid(row=0, column=0, sticky=tk.NSEW)
        right_frame.grid(row=0, column=1, sticky=tk.NSEW, padx=(10, 0))
        sampling_group.columnconfigure(0, weight=1)
        sampling_group.columnconfigure(1, weight=1)
        
        self.temp = tk.StringVar(value="")
        self.create_spinbox(left_frame, "温度 (--temp):", self.temp, "创造力级别（默认 0.8）。越低越确定，越高越有创造力。", from_=0, to=2, increment=0.1, row=0)

        self.top_k = tk.StringVar(value="")
        self.create_spinbox(left_frame, "Top-K (--top-k):", self.top_k, "采样时仅保留 top-k 个令牌（默认 40）。", from_=0, to=1000, increment=1, row=1)
        
        self.top_p = tk.StringVar(value="")
        self.create_spinbox(left_frame, "Top-P (--top-p):", self.top_p, "核采样（默认 0.9）。", from_=0, to=1, increment=0.1, row=2)

        self.repeat_penalty = tk.StringVar(value="")
        self.create_spinbox(left_frame, "重复惩罚 (--repeat-penalty):", self.repeat_penalty, "重复惩罚（默认 1.0）。增加以减少重复循环。", from_=0, to=2, increment=0.1, row=3)
        self.seed = tk.StringVar(value="")
        self.create_spinbox(left_frame, "随机种子 (--seed):", self.seed, "RNG 种子（默认 -1 = 随机）。设为固定值可重现结果。", from_=-1, to=2147483647, increment=1, row=4)
        self.min_p = tk.StringVar(value="")
        self.create_spinbox(left_frame, "Min-P (--min-p):", self.min_p, "最小概率采样（默认 0.05，0.0 = 禁用）。比 top-p 更新更好的采样方式。", from_=0, to=1, increment=0.05, row=5)
        self.presence_penalty = tk.StringVar(value="")
        self.create_spinbox(left_frame, "存在惩罚 (--presence-penalty):", self.presence_penalty, "话题存在惩罚（默认 0.0）。降低重复讨论相同话题。", from_=0, to=2, increment=0.1, row=6)
        self.frequency_penalty = tk.StringVar(value="")
        self.create_spinbox(left_frame, "频率惩罚 (--frequency-penalty):", self.frequency_penalty, "词频惩罚（默认 0.0）。降低高频词重复出现。", from_=0, to=2, increment=0.1, row=7)
        self.repeat_last_n = tk.StringVar(value="")
        self.create_spinbox(left_frame, "惩罚窗口 (--repeat-last-n):", self.repeat_last_n, "重复惩罚考虑的最近令牌数（默认 64，0 = 禁用，-1 = 上下文大小）。", from_=-1, to=4096, increment=1, row=8)

        # --- Advanced Sampling (side-by-side) ---
        self.adv_sampling_visible = tk.BooleanVar(value=False)
        adv_toggle_frame = ttk.Frame(left_frame)
        adv_toggle_frame.grid(row=9, column=0, columnspan=2, sticky=tk.W, pady=(10, 0))
        adv_toggle = ttk.Checkbutton(adv_toggle_frame, text="▸ 高级采样", variable=self.adv_sampling_visible, bootstyle="round-toggle")
        adv_toggle.pack(side=tk.LEFT)
        ToolTip(adv_toggle, "展开高级采样参数。建议一次只开一组：日常用 Mirostat，长文防重复用 DRY，创意写作加 XTC。")

        self.adv_sampling_frame = ttk.Frame(right_frame)
        # hidden by default; packed when toggled

        def toggle_adv_sampling():
            if self.adv_sampling_visible.get():
                self.adv_sampling_frame.pack(fill=tk.BOTH, expand=True)
            else:
                self.adv_sampling_frame.pack_forget()
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
        self.create_entry(dry_group, "分隔符 (--dry-sequence-breaker):", self.dry_sequence_breaker, 'DRY 序列分隔符。写入后遇到此字符视为打断重复（如 "\\\\n" 遇换行重置计数）。按需设置。', row=4)




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
        self.moe_cpu_layers_spin = self.create_spinbox(mem_group, "MoE CPU 层数 (--n-cpu-moe):", self.moe_cpu_layers, "GPU 放不下时保留在 CPU 上的 MoE 层数。", row=1, from_=0, to=99, increment=1)
        self.mlock = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "内存锁定 (--mlock)", self.mlock, "将模型锁定在 RAM 中防止交换。", row=2)
        self.no_mmap = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "禁用内存映射 (--no-mmap)", self.no_mmap, "禁用模型文件的内存映射。", row=3)
        self.numa = tk.BooleanVar(value=False)
        self.create_checkbutton(mem_group, "NUMA 优化 (--numa)", self.numa, "启用 NUMA 感知优化。仅多路 CPU 服务器需要（如双路 Xeon/EPYC），单 CPU 系统（如本机 Strix Halo）开启无效果。", row=4)
        # --- Cache Type for Draft K/V (moved here from Speculative Decoding)
        cache_types = ["", "f32", "f16", "bf16", "q8_0", "q4_0", "q4_1", "iq4_nl", "q5_0", "q5_1"]
        self.cache_type_k = tk.StringVar(value="")
        self.create_combobox(mem_group, "K 缓存类型 (-ctk):", self.cache_type_k, "K 的 KV 缓存数据类型（默认 f16）。", cache_types, row=5)
        self.cache_type_v = tk.StringVar(value="")
        self.create_combobox(mem_group, "V 缓存类型 (-ctv):", self.cache_type_v, "V 的 KV 缓存数据类型（默认 f16）。", cache_types, row=6)

        # --- Speculative Decoding ---
        spec_group = ttk.Labelframe(parent, text="推测解码", padding="10")
        self._embedding_frames.append(spec_group)
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
        spec_types = ["", "none", "mtp", "draft-mtp", "draft-simple", "draft-eagle3", "ngram-cache", "ngram-simple", "ngram-map-k", "ngram-map-k4v", "ngram-mod"]
        self.create_combobox(spec_group, "推测解码类型 (--spec-type):", self.spec_type, "推测解码类型。无草稿模型时（模型自带MTP头）可选：none / ngram-cache / ngram-mod 等；有草稿模型时（-md 指定）可选：draft-mtp / draft-simple / draft-eagle3。可组合多个，用逗号分隔。", spec_types, row=4)
        # (草稿模型下载已整合到「模型」标签页的 ModelScope 区域)
        # --- Server Reliability ---
        server_rel_group = ttk.Labelframe(parent, text="服务器可靠性", padding="10")
        self._embedding_frames.append(server_rel_group)
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
        
        # --- Embedding Mode Status ---
        self._embedding_status = ttk.Label(parent, text="", bootstyle="info")
        # hidden by default; shown by _set_embedding_mode

        # --- Network Configuration ---
        net_group = ttk.Labelframe(parent, text="网络配置", padding="10")
        net_group.grid(row=0, column=0, sticky=tk.EW, pady=5)
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
        access_group.grid(row=1, column=0, sticky=tk.EW, pady=5)
        access_group.columnconfigure(1, weight=1)
        self.api_key = tk.StringVar()
        self.create_entry(access_group, "API 密钥 (--api-key):", self.api_key, "API 密钥，用于令牌认证（可选）。", row=0)
        self.no_ui = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "禁用内置 UI (--no-ui)", self.no_ui, "新版 llama-server 默认已嵌入 WebUI，勾选后禁用。不勾选即可在浏览器访问 http://host:port 使用内置界面。", row=1)
        self.embedding = tk.BooleanVar(value=False)
        self.embedding_cb = ttk.Checkbutton(access_group, text="仅嵌入模式 (--embedding)",
            variable=self.embedding, bootstyle="round-toggle")
        self.embedding_cb.grid(row=2, column=0, columnspan=2, sticky=tk.W, padx=5, pady=5)
        ToolTip(self.embedding_cb, text="启用仅嵌入模式（禁用聊天和生成功能）。加载向量模型（如 Qwen3-Embedding、BGE）时自动勾选，取消勾选可恢复文本生成模式。")
        # Sync UI when user manually toggles the checkbox
        self.embedding.trace_add('write', lambda *_: self._set_embedding_mode(self.embedding.get()))
        self.pooling = tk.StringVar()
        pooling_options = ["", "none", "mean", "cls", "last", "rank"]
        self.create_combobox(access_group, "嵌入池化 (--pooling):", self.pooling, "Embedding 模型的池化策略。mean=全局平均（通用推荐），cls=首令牌（BGE 适用），last=末令牌，rank=排序专用。留空则使用模型默认。", pooling_options, row=3)
        self.reranking = tk.BooleanVar(value=False)
        self.create_checkbutton(access_group, "重排序端点 (--reranking)", self.reranking, "启用 /v1/rerank 端点（RAG 检索重排序）。仅 cross-encoder/rerank 模型需要，如 BGE-Reranker。", row=4)


        # --- Custom Arguments Management ---
        custom_group = ttk.Labelframe(parent, text="自定义参数管理", padding="10")
        custom_group.grid(row=2, column=0, sticky=tk.NSEW, pady=5)
        custom_group.columnconfigure(0, weight=1)
        custom_group.rowconfigure(1, weight=1)

        # Input for new argument
        add_arg_frame = ttk.Frame(custom_group)
        add_arg_frame.grid(row=0, column=0, sticky=tk.EW, pady=(0, 10))
        add_arg_frame.columnconfigure(0, weight=1)
        self.new_arg_entry = ttk.Entry(add_arg_frame)
        self.new_arg_entry.grid(row=0, column=0, sticky=tk.EW, padx=(0, 5))
        ToolTip(self.new_arg_entry, "输入完整参数及其值（例如 --my-flag value），然后点击添加。")
        add_button = ttk.Button(add_arg_frame, text="添加", command=self.add_custom_argument, bootstyle="success-outline")
        add_button.grid(row=0, column=1, sticky=tk.E)

        # Scrollable list for existing arguments
        self.custom_args_list_frame = ScrolledFrame(custom_group, autohide=True, bootstyle="round")
        self.custom_args_list_frame.grid(row=1, column=0, sticky=tk.NSEW)
        
        # Other options below the list
        other_options_frame = ttk.Frame(custom_group)
        other_options_frame.grid(row=2, column=0, sticky=tk.EW, pady=(10, 0))
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
        self.output_text.tag_configure("info", foreground="#1abc9c")       # teal: info
        
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
        
        # --- Download directory picker ---
        dl_dir_frame = ttk.Frame(dl_frame)
        dl_dir_frame.grid(row=0, column=0, columnspan=2, sticky=tk.EW, pady=(0, 2))
        dl_dir_frame.columnconfigure(1, weight=1)
        ttk.Label(dl_dir_frame, text="下载目录:", font=("", 8)).grid(row=0, column=0, padx=(0, 5))
        self._dl_dir_display = ttk.Label(dl_dir_frame, text="", foreground="gray", font=("", 8), anchor=tk.W)
        self._dl_dir_display.grid(row=0, column=1, sticky=tk.EW)
        ToolTip(self._dl_dir_display, "模型下载后保存的目录。点击右侧按钮更改。")
        dl_dir_btn = ttk.Button(dl_dir_frame, text="📂 更改", command=self._change_ms_download_root,
            bootstyle="secondary-link", takefocus=False)
        dl_dir_btn.grid(row=0, column=2, padx=(5, 0))
        
        # --- Main Model Download ---
        ms_group = ttk.Labelframe(dl_frame, text="ModelScope 模型下载", padding="8")
        ms_group.grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=(0, 5))
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
        dg.grid(row=2, column=0, columnspan=2, sticky=tk.EW)
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
        
        self.repo_remove_dir_btn = ttk.Button(toolbar, text="✖ 移除目录",
            command=self.repo_remove_selected_root_btn, bootstyle="secondary")
        self.repo_remove_dir_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.repo_remove_dir_btn, "移除选中的自定义目录（仅限非内置目录）。")
        
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
        
        ftype = self._classify_gguf_file(filepath=fpath, fname=fname)
        icon = "📷" if ftype == 'mmproj' else ("📊" if ftype == 'imatrix' else "📄")
        
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
    
    def _repo_remove_root_by_iid(self, iid):
        """Remove a custom root directory by tree item ID."""
        if not iid or iid not in self.repo_root_items:
            return
        root_info = self.repo_root_items[iid]
        if root_info.get('builtin', False):
            Messagebox.show_warning("内置目录不可移除。", "提示", parent=self.root)
            return
        
        reply = tk.messagebox.askokcancel(
            "确认移除",
            f"确定将「{root_info['label']}」移出扫描列表？\n文件不会被删除。",
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
    
    def _repo_remove_selected_root(self):
        """Remove a custom root directory (called from right-click context menu)."""
        self._repo_remove_root_by_iid(getattr(self, '_repo_context_iid', None))
    
    def repo_remove_selected_root_btn(self):
        """Remove the currently selected root directory (called from toolbar button)."""
        sel = self.repo_tree.selection()
        if not sel:
            Messagebox.show_warning("请先在左侧模型树中选中要移除的目录（根节点）。\n\n提示：点击目录名即可选中。", "提示", parent=self.root)
            return
        self._repo_remove_root_by_iid(sel[0])
    
    def repo_load_model(self):
        """Load the selected model into the main config."""
        if not self._repo_selected_path:
            return
        self.model_path.set(self._repo_selected_path)
        
        # Auto-handle mmproj: clear old one, fill if found in same directory
        repo_dir = os.path.dirname(self._repo_selected_path)
        mmproj_found = None
        if os.path.isdir(repo_dir):
            for f in sorted(os.listdir(repo_dir)):
                if not f.endswith('.gguf'):
                    continue
                fpath = os.path.join(repo_dir, f)
                ftype = self._classify_gguf_file(filepath=fpath, fname=f)
                if ftype == 'mmproj':
                    mmproj_found = fpath
                    break
        if mmproj_found:
            self.mmproj_path.set(mmproj_found)
        else:
            self.mmproj_path.set("")
        # Also fill alias immediately (context slider debounce may be delayed)
        self._auto_fill_alias(force=True)
        # Check embedding mode
        self._check_embedding_mode()
    
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
        reply = tk.messagebox.askyesno(
            "确认删除",
            f"确定要删除 {fname}？\n此操作不可撤销！",
            parent=self.root
        )
        if not reply:
            return
        
        try:
            os.remove(self._repo_selected_path)
            LlamaGUIClass._gguf_cache.pop(self._repo_selected_path, None)
            Messagebox.ok(f"已删除：{fname}", "删除成功", parent=self.root)
            self.scan_downloaded_models()  # Refresh tree
        except Exception as e:
            Messagebox.show_error(f"删除失败：{e}", "错误", parent=self.root)
    
    def repo_open_folder(self):
        """Open the file's directory in file explorer."""
        if not self._repo_selected_path:
            return
        folder = os.path.dirname(self._repo_selected_path)
        self._open_file_explorer(folder)

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
        ToolTip(self.engine_add_btn, f"选择一个包含 {self._exe_name('llama-server')} 的目录。")
        
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
                exe_path = os.path.join(eng_dir, self._exe_name())
                if os.path.isdir(eng_dir) and os.path.isfile(exe_path):
                    eng_info = self._get_engine_info(entry, eng_dir, exe_path, '本地')
                    engines.append(eng_info)
                    seen_dirs.add(os.path.normcase(eng_dir))
        
        # 2. Include all config-saved custom engine directories (multi-engine support)
        custom_dirs = []
        if self.selected_engine_dir:
            custom_dirs.append(self.selected_engine_dir)
        for d in getattr(self, '_custom_engine_dirs', []):
            if os.path.normcase(d) not in [os.path.normcase(c) for c in custom_dirs]:
                custom_dirs.append(d)
        for eng_dir in custom_dirs:
            norm = os.path.normcase(eng_dir)
            if norm not in seen_dirs:
                exe_path = os.path.join(eng_dir, self._exe_name())
                if os.path.isfile(exe_path):
                    name = os.path.basename(os.path.normpath(eng_dir))
                    eng_info = self._get_engine_info(name, eng_dir, exe_path, '自定义')
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
                # Auto-select as default engine on click (replaces need for explicit "设为默认")
            if os.path.normcase(eng['dir']) != os.path.normcase(self.selected_engine_dir):
                self.selected_engine_dir = eng['dir']
                self._refresh_engine_tree_markers()
    
    def _refresh_engine_tree_markers(self):
        """Update engine tree icons, markers, and default tags."""
        for child in self.engine_tree.get_children():
            e = self.engine_tree_items.get(child)
            if not e:
                continue
            is_default = os.path.normcase(e['dir']) == os.path.normcase(self.selected_engine_dir)
            marker = "⭐ " if is_default else "  "
            icon = "🖥" if 'ROCm' in e.get('version', '') or 'hip' in e.get('name', '').lower() else "⚡"
            label = f"{e['name']}  [默认]" if is_default else e['name']
            self.engine_tree.item(child, text=f"{marker}{icon}  {label}",
                tags=('default',) if is_default else ())
    
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
        self._refresh_engine_tree_markers()
        self.engine_status_var.set(f"✅ 默认引擎：{eng['name']}")
        Messagebox.ok(f"默认引擎已设为：\n{eng['dir']}", "已设置", parent=self.root)
    
    def engine_add_directory(self):
        """Browse and add an engine directory."""
        app_dir = os.path.dirname(self.get_config_path(''))
        chosen = filedialog.askdirectory(
            title=f"选择包含 {self._exe_name('llama-server')} 的目录",
            initialdir=app_dir
        )
        if not chosen:
            return
        
        exe_path = os.path.join(chosen, self._exe_name())
        if not os.path.isfile(exe_path):
            Messagebox.show_error(f"所选目录中没有找到 {self._exe_name('llama-server')}！", "错误", parent=self.root)
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
        
        reply = tk.messagebox.askyesno(
            "确认移除",
            f"确定将「{eng['name']}」移出列表？\n文件不会被删除。",
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
            self._open_file_explorer(eng['dir'])
    
    def engine_get_path(self):
        """Get the full path to the llama-server binary for the selected engine.
        Returns None if using system PATH."""
        if self.selected_engine_dir:
            exe_path = os.path.join(self.selected_engine_dir, self._exe_name())
            if os.path.isfile(exe_path):
                return exe_path
        return None

    # --- ModelScope Download Methods ---
    def _change_ms_download_root(self):
        """Let user choose a custom download root directory."""
        app_dir = os.path.dirname(self.get_config_path(''))
        default_dir = os.path.join(app_dir, 'models')
        initial = self.ms_download_root if self.ms_download_root else default_dir
        chosen = filedialog.askdirectory(
            title="选择模型下载根目录（选中的仓库会下载到其子目录）",
            initialdir=initial if os.path.isdir(initial) else app_dir
        )
        if not chosen:
            return
        self.ms_download_root = chosen
        self._sync_dl_dir_display()
        # Auto-register as a repo root, but skip if already covered by an existing root
        if hasattr(self, 'model_repo_roots') and self.model_repo_roots:
            norm_chosen = os.path.normcase(chosen) + os.sep
            is_covered = False
            for r in self.model_repo_roots:
                norm_root = os.path.normcase(r['path']) + os.sep
                if norm_chosen == norm_root or norm_chosen.startswith(norm_root):
                    is_covered = True
                    break
            if not is_covered:
                self.model_repo_roots.append({'path': chosen, 'label': os.path.basename(chosen), 'builtin': False})
                if hasattr(self, 'scan_downloaded_models'):
                    self.scan_downloaded_models()
                Messagebox.ok(f"已添加「{os.path.basename(chosen)}」到模型仓库扫描列表。", "已同步", parent=self.root)

    def _sync_dl_dir_display(self):
        """Update the download directory label."""
        app_dir = os.path.dirname(self.get_config_path(''))
        default_dir = os.path.join(app_dir, 'models')
        path = self.ms_download_root if self.ms_download_root else default_dir
        # Show shortened display
        if len(path) > 50:
            display = "..." + path[-47:]
        else:
            display = path
        self._dl_dir_display.config(text=display)

    def _ms_get_repo_dir(self, repo=None):
        """Parse repo ID and return the save directory path.
        E.g. 'unsloth/Qwen3.6-35B-A3B-GGUF' → '{root}/unsloth/Qwen3.6-35B-A3B-GGUF/'
        Root is self.ms_download_root if set, else default {app_dir}/models/.
        If repo is None, uses self.ms_repo (main model repo).
        """
        if repo is None:
            repo = self.ms_repo.get().strip()
        app_dir = os.path.dirname(self.get_config_path(''))
        root = self.ms_download_root if self.ms_download_root else os.path.join(app_dir, 'models')
        # Replace / with \ for windows, normalize path
        safe_name = repo.replace('/', os.sep).replace('\\', os.sep)
        return os.path.join(root, safe_name)
    
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
                url = f"https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true"
                req = urllib.request.Request(url, headers={"User-Agent": "llama-cpp-GUI-zh/1.0"})
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
                    ftype = self._classify_gguf_file(fname=name)
                    if is_gguf or name.endswith('.gguf_file') or name.endswith('.txt'):
                        all_files.append({
                            'name': name,
                            'path': f.get('Path', name),
                            'size': f.get('Size', 0),
                            'type': ftype
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
            
            cb = ttk.Checkbutton(row, variable=var, bootstyle="round-toggle", command=self._ms_update_dl_button)
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
        
        # Check existing files — skip those user declines to overwrite
        remaining = []
        for fi in files_to_dl:
            save_path = os.path.join(repo_dir, fi['path'])
            if os.path.exists(save_path):
                reply = tk.messagebox.askyesno(
                    "文件已存在",
                    f"文件 {fi['name']} 已存在于\n{save_path}\n是否覆盖？",
                    parent=self.root)
                if not reply:
                    continue
            remaining.append(fi)
        if not remaining:
            return
        files_to_dl = remaining
        
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
        file_rel_path = file_info['path']
        save_path = os.path.join(self._ms_dl_dir, file_rel_path)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        
        filename = file_info.get('name', os.path.basename(file_rel_path))
        idx = len(self._ms_dl_results) + 1
        total = len(self._ms_dl_results) + len(self._ms_dl_queue) + 1
        self.ms_progress_label.config(text=f"({idx}/{total}) 正在下载 {filename}...")
        
        def download():
            tmp_path = save_path + '.tmp'
            try:
                url = f"https://www.modelscope.cn/models/{repo}/resolve/main/{file_info['path']}"
                req = urllib.request.Request(url, headers={"User-Agent": "llama-cpp-GUI-zh/1.0"})
                with urllib.request.urlopen(req, timeout=600) as resp:
                    total_size = int(resp.headers.get('Content-Length', 0))
                    chunk_size = 8 * 1024 * 1024
                    downloaded = 0
                    
                    with open(tmp_path, 'wb') as f:
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
                os.replace(tmp_path, save_path)
                self._ms_dl_results[file_info['type']] = save_path
                self.root.after(0, self._download_next_in_queue)
            except urllib.error.URLError as e:
                self.root.after(0, lambda: self._dl_queue_failed(f"网络错误：{e.reason}", tmp_path))
            except Exception as e:
                self.root.after(0, lambda: self._dl_queue_failed(str(e), tmp_path))
            finally:
                # Clean up .tmp file if it still exists (e.g., cancelled mid-write)
                if not os.path.exists(save_path) and os.path.exists(tmp_path):
                    try:
                        os.remove(tmp_path)
                    except OSError:
                        pass
        
        threading.Thread(target=download, daemon=True).start()
    
    def _dl_cleanup_cancelled(self):
        """Clean up after user cancelled."""
        self.browse_ms_btn.config(state=tk.NORMAL)
        self.download_ms_btn.config(state=tk.NORMAL)
        self.cancel_ms_btn.config(state=tk.DISABLED)
        self.ms_progress['value'] = 0
        self.ms_progress_label.config(text="⏹ 已取消")
        self.ms_status_var.set("⏹ 下载已取消")
        # Clean up all .tmp files in the download directory
        if os.path.exists(self._ms_dl_dir):
            for root, dirs, files in os.walk(self._ms_dl_dir):
                for fname in files:
                    if fname.endswith('.tmp'):
                        try:
                            os.remove(os.path.join(root, fname))
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
                url = f"https://www.modelscope.cn/api/v1/models/{repo}/repo/files?Recursive=true"
                req = urllib.request.Request(url, headers={"User-Agent": "llama-cpp-GUI-zh/1.0"})
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
                
                files = data.get('Data', {}).get('Files', [])
                ggufs = []
                for f in files:
                    if f.get('Type') != 'blob':
                        continue
                    name = f.get('Name', '')
                    if name.endswith('.gguf') and self._classify_gguf_file(fname=name) != 'mmproj':
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
        
        # Save to same directory structure (respects custom download root)
        dest_dir = self._ms_get_repo_dir(repo=repo)
        os.makedirs(dest_dir, exist_ok=True)
        save_path = os.path.join(dest_dir, filename)
        
        if os.path.exists(save_path):
            reply = tk.messagebox.askyesno(
                "文件已存在",
                f"文件 {filename} 已存在。\n是否覆盖？",
                parent=self.root)
            if not reply:
                return
        
        self.draft_browse_btn.config(state=tk.DISABLED)
        self.draft_dl_btn.config(state=tk.DISABLED)
        self.draft_status_var.set(f"正在下载 {filename}...")
        
        def download():
            try:
                url = f"https://www.modelscope.cn/models/{repo}/resolve/main/{file_info['path']}"
                req = urllib.request.Request(url, headers={"User-Agent": "llama-cpp-GUI-zh/1.0"})
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
            dest_dir = self._ms_get_repo_dir(repo=self.draft_ms_repo.get().strip())
            partial = os.path.join(dest_dir, filename + '.tmp')
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

    _gguf_cache = {}
    _gguf_cache_lock = threading.Lock()

    @staticmethod
    def _read_gguf_metadata(filepath):
        with LlamaGUIClass._gguf_cache_lock:
            if filepath in LlamaGUIClass._gguf_cache:
                return LlamaGUIClass._gguf_cache[filepath]
        """Read basic GGUF metadata from the file header.
        Returns dict with architecture, context_length, file_type, etc.
        Cached via lru_cache to avoid repeated file I/O."""
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
                for _ in range(min(metadata_count, 500)):
                    try:
                        key = read_string(f)
                        val = read_value(f)
                        if key and val is not None:  # filter to relevant keys only
                            meta[key] = val
                    except Exception:
                        break
                
                result = meta
        except Exception:
            result = None
        with LlamaGUIClass._gguf_cache_lock:
            if len(LlamaGUIClass._gguf_cache) >= 256:
                oldest = next(iter(LlamaGUIClass._gguf_cache))
                del LlamaGUIClass._gguf_cache[oldest]
            LlamaGUIClass._gguf_cache[filepath] = result
        return result

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

    # ------------------------------------------------------------------
    # file classification — shared between local tree + ModelScope
    # ------------------------------------------------------------------

    @staticmethod
    @lru_cache(maxsize=256)
    def _read_gguf_type(filepath):
        """Cached helper: read general.type from GGUF header."""
        meta = LlamaServerGUI._read_gguf_metadata(filepath)
        return meta.get('general.type', 'unknown') if meta else 'unknown'

    @staticmethod
    @lru_cache(maxsize=256)
    def _read_gguf_embedding_check(filepath):
        """Cached helper: check if GGUF model is an embedding model."""
        meta = LlamaServerGUI._read_gguf_metadata(filepath)
        if not meta:
            return False
        arch = meta.get('general.architecture', '')
        if arch and arch.lower() in LlamaServerGUI._EMBEDDING_ARCHS:
            return True
        basename = meta.get('general.basename', '')
        if basename and 'embed' in basename.lower():
            return True
        name = meta.get('general.name', '')
        if name and 'embed' in name.lower():
            return True
        return False

    def _classify_gguf_file(self, filepath=None, fname=None):
        """Determine if a GGUF file is a multimodal projector (mmproj).

        Priority:
        1. If *filepath* points to a local file → read GGUF header ``general.type`` (definitive).
        2. If only *fname* is available (ModelScope remote) → filename heuristic.

        Returns ``"mmproj"``, ``"model"``, ``"imatrix"``, or ``"unknown"``.
        """
        # --- Filename heuristic (always checked — imatrix is detected by name, not header) ---
        if fname:
            lower = fname.lower()
            if 'imatrix' in lower:
                return 'imatrix'

        # --- GGUF header (authoritative for mmproj vs model) ---
        if filepath and os.path.isfile(filepath):
            cached = self._read_gguf_type(filepath)
            if cached in ('mmproj', 'model'):
                return cached

        # --- Filename heuristic (mmproj fallback for ModelScope remote) ---
        if fname:
            lower = fname.lower()
            if 'mmproj' in lower:
                return 'mmproj'
            # If the file ends with .gguf or .gguf_file and doesn't match any special type, it's a model
            if lower.endswith('.gguf') or lower.endswith('.gguf_file'):
                return 'model'

        return 'unknown'

    # ------------------------------------------------------------------
    # embedding model detection
    # ------------------------------------------------------------------
    _EMBEDDING_ARCHS = frozenset({'bge', 'gte', 'e5', 'text-embedding', 'sentence-bert', 'sentence-t5', 'instructor'})

    def _is_embedding_model(self, filepath=None, fname=None):
        """Detect if a GGUF file is an embedding/vector model.

        Priority:
        1. Local file → read GGUF header for ``general.architecture`` / ``general.basename``.
        2. ModelScope remote → filename heuristic (``"embed"`` in name).

        Uses an LRU-cached helper to avoid redundant file I/O.
        """
        # --- GGUF header (authoritative for local files) ---
        if filepath and os.path.isfile(filepath):
            if self._read_gguf_embedding_check(filepath):
                return True

        # --- Filename heuristic (ModelScope remote / fallback) ---
        if fname:
            lower = fname.lower()
            # Must NOT be mmproj or imatrix
            if 'mmproj' in lower or 'imatrix' in lower:
                return False
            if 'embed' in lower:
                return True

        return False

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
        if not hasattr(self, 'custom_args_list_frame'):
            return
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
        """Build llama-server CLI args from current parameter settings.
        
        Uses _PARAM_DEFS as single source of truth — no more manual arg dicts.
        """
        if not self.model_path.get().strip():
            Messagebox.show_error("请选择模型路径！", "错误")
            return None
        
        engine_path = self.engine_get_path()
        if engine_path:
            cmd = [engine_path, "-m", self.model_path.get().strip()]
        else:
            cmd = ["llama-server", "-m", self.model_path.get().strip()]
        
        # ── auto-generated from _PARAM_DEFS ──
        is_emb = self.embedding.get()
        for ck, an, flag, kind, default in self._PARAM_DEFS:
            if ck in self._SPECIAL_PARAMS:
                continue  # handled specially below
            if is_emb and ck in self._EMBEDDING_SKIP_PARAMS:
                continue  # not applicable in embedding mode
            
            var = self._get_var(an)
            if var is None:
                continue
            val = var.get()
            val_s = str(val).strip() if val is not None else ""
            
            if kind == "bool" and val:
                cmd.append(flag)
            elif kind == "str" and val_s and val_s != "auto":
                cmd.extend([flag, val_s])
            elif kind == "int" and val_s:
                cmd.extend([flag, val_s])
        
        # ── special cases ──
        # ctx_size: only if not auto
        if not self.ctx_size_auto.get():
            cmd.extend(["-c", str(self.ctx_size.get())])
        cmd.extend(["-ngl", str(self.gpu_layers.get())])
        
        # flash_attn: only if not auto
        fa_val = self.flash_attn.get().strip()
        if fa_val and fa_val != "auto":
            cmd.extend(["-fa", fa_val])
        
        # reasoning_effort: JSON wrapper
        re_val = self.reasoning_effort.get().strip()
        if re_val:
            cmd.extend(["--chat-template-kwargs", json.dumps({"reasoning_effort": re_val})])
        
        # cache_prompt: inverted (default True, unchecked → --no-cache-prompt)
        if not self.cache_prompt.get():
            cmd.append("--no-cache-prompt")
        
        # numa: extends to ["--numa", "distribute"]
        if self.numa.get():
            cmd.extend(["--numa", "distribute"])
        
        # custom arguments (user-defined, not in PARAM_DEFS)
        _dangerous_re = re.compile(r'[;|&$`@!(){}<>]')
        for arg_item in self.custom_arguments:
            if arg_item.get("enabled", False) and arg_item.get("value", "").strip():
                val = arg_item["value"].strip()
                if _dangerous_re.search(val):
                    self.update_output(f"[警告] 自定义参数含危险字符已跳过: {val}\n", tag="error")
                    continue
                try:
                    cmd.extend(shlex.split(val))
                except ValueError:
                    cmd.extend(val.split())
        
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
        # Save current instance config first
        self._save_active_instance()
        inst = self._instances.get(self._active_instance_id)
        if not inst:
            self.update_output("[错误] 没有活动的实例\n", tag="error")
            return
        if inst.get("is_running", False):
            return
        
        eng_dir = inst.get("engine_dir", "")
        params = inst.get("params", {})
        
        cmd = self.generate_command()
        if not cmd:
            return
        
        self.output_text.delete(1.0, tk.END)
        command_str = " ".join(f'"{arg}"' if " " in arg else arg for arg in cmd)
        self.update_output(f"▶ Starting server with command:\n{command_str}\n\n" + "="*80 + "\n")
        
        # Popen on main thread so running_pid is set before _auto_save_instances
        startupinfo = self._startupinfo()
        try:
            process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                universal_newlines=False, bufsize=1, startupinfo=startupinfo
            )
        except FileNotFoundError:
            self.update_output("\n⚠ 错误：找不到 llama-server 可执行文件，请确保它在 PATH 或同目录下。\n")
            self.server_stopped(self._active_instance_id)
            return
        except Exception as e:
            self.update_output(f"\n⚠ 启动服务器错误：{e}\n")
            self.server_stopped(self._active_instance_id)
            return
        
        inst["process"] = process
        inst["running_pid"] = str(process.pid)
        inst["_stop_event"] = threading.Event()
        stopped_inst_id = self._active_instance_id
        
        def run_server():
            try:
                while True:
                    line_bytes = process.stdout.readline()
                    if not line_bytes:
                        break
                    try:
                        line = line_bytes.decode(self._sys_encoding)
                    except UnicodeDecodeError:
                        line = line_bytes.decode('latin-1', errors='replace')
                    self.root.after(0, self.update_output, line)
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
                self.root.after(0, lambda sid=stopped_inst_id: self.server_stopped(sid))
            except Exception as e:
                self.root.after(0, self.update_output, f"\n⚠ 服务器输出读取错误：{e}\n")
                self.root.after(0, lambda sid=stopped_inst_id: self.server_stopped(sid))
        
        threading.Thread(target=run_server, daemon=True).start()
        
        inst["is_running"] = True
        inst["running_port"] = params.get("port", "8080")
        inst["running_host"] = params.get("host", "127.0.0.1")
        self.is_running = True
        self.start_button.config(state=tk.DISABLED)
        self.stop_button.config(state=tk.NORMAL)
        self.browser_button.config(state=tk.NORMAL)
        self.server_status_var.set("⏳ 启动中...")
        self.server_status_label.config(foreground="orange")
        
        self._startup_start_time = time.perf_counter()
        if hasattr(self, '_startup_sec'):
            del self._startup_sec
        
        # Capture connection info at launch time (thread-safe)
        health_host = inst["running_host"]
        if health_host == '0.0.0.0': health_host = 'localhost'
        health_port = inst["running_port"]
        health_inst_id = self._active_instance_id
        
        # Start health monitor thread
        threading.Thread(target=self._health_check_loop,
            args=(health_host, health_port, health_inst_id), daemon=True).start()
        
        self._refresh_instance_tree()
        self._sync_bottom_bar_for_active_instance()
        self._auto_save_instances()

    def stop_server(self):
        inst = self._instances.get(self._active_instance_id)
        if not inst:
            self.update_output("[错误] 没有活动的实例\n", tag="error")
            return
        if not inst.get("is_running", False):
            return
        
        port = inst.get("running_port", "") or inst.get("params", {}).get("port", "")
        killed = False
        
        startupinfo = self._startupinfo()
        
        # Method 1: process object (for instances started in this session)
        proc = inst.get("process")
        stop_event = inst.get("_stop_event")
        if proc:
            try:
                # Signal the run_server thread to stop reading
                if stop_event:
                    stop_event.set()
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
                killed = True
                self.update_output("\n" + "="*80 + "\n⏹️ 正在停止服务器...\n")
            except Exception as e:
                self.update_output(f"\n⚠ 终止进程对象失败：{e}，尝试 PID 方式...\n")
        
        # Method 2: PID-based kill (for PID-recovered instances)
        if not killed:
            pid = inst.get("running_pid", "")
            if pid:
                try:
                    if self._is_windows():
                        r = subprocess.run(
                            ["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=5, startupinfo=startupinfo
                        )
                        if r.returncode == 0:
                            killed = True
                            self.update_output(f"\n⏹️ 已通过 PID {pid} 终止进程\n")
                        else:
                            err = r.stderr.decode(self._sys_encoding, errors='replace').strip()
                            self.update_output(f"\n⚠ PID {pid} 终止失败: {err}\n")
                    else:
                        os.kill(int(pid), signal.SIGTERM)
                        killed = True
                        self.update_output(f"\n⏹️ 已通过 PID {pid} 终止进程\n")
                except Exception as e:
                    self.update_output(f"\n⚠ PID {pid} 终止异常：{e}\n")
        
        # Method 3: port-based fallback (find any process on the instance's port)
        if not killed and port:
            try:
                if self._is_windows():
                    r = subprocess.run(
                        ["powershell", "-NoProfile", "-Command",
                         f"try{{$p=Get-NetTCPConnection -LocalPort {port} -ErrorAction Stop|Select-Object -First 1 -ExpandProperty OwningProcess;Stop-Process -Id $p -Force;Write-Output $p}}catch{{}}"],
                        capture_output=True, timeout=5, startupinfo=startupinfo
                    )
                    out = r.stdout.decode(self._sys_encoding, errors='replace').strip()
                else:
                    r = subprocess.run(
                        ["lsof", "-ti", f"-i:{port}"],
                        capture_output=True, timeout=5
                    )
                    pids = r.stdout.decode(self._sys_encoding, errors='replace').strip().split()
                    out = ""
                    for pid in pids:
                        if pid:
                            try:
                                os.kill(int(pid), signal.SIGTERM)
                                out = pid
                            except (OSError, ValueError):
                                pass
                if out:
                    killed = True
                    self.update_output(f"\n⏹️ 已通过端口 {port} 终止进程 (PID {out})\n")
                else:
                    self.update_output(f"\n⚠ 端口 {port} 上未发现监听进程\n")
            except FileNotFoundError:
                self.update_output(f"\n⚠ 需要安装 lsof 或 netstat 以支持端口查杀\n")
            except Exception as e:
                self.update_output(f"\n⚠ 端口 {port} 查杀异常：{e}\n")
        
        if not killed:
            self.update_output("\n⚠ 无法终止进程，请手动检查后台进程。\n", tag="error")
            return
        
        # Clear run state (only after successful kill)
        with self._instances_lock:
            inst["is_running"] = False
            inst["process"] = None
            inst["_stop_event"] = None
            inst["running_pid"] = ""
            inst["health_active"] = False
        self.is_running = any(inst.get("is_running") for inst in self._instances.values())
        self._refresh_instance_tree()
        self._sync_bottom_bar_for_active_instance()
        self._auto_save_instances()
    
    def server_stopped(self, inst_id=None):
        inst_id = inst_id or self._active_instance_id
        with self._instances_lock:
            inst = self._instances.get(inst_id)
            if inst:
                inst["is_running"] = False
                inst["process"] = None
                inst["running_pid"] = ""
                inst["health_active"] = False
        self.is_running = any(inst.get("is_running") for inst in self._instances.values())
        self.start_button.config(state=tk.NORMAL)
        self.stop_button.config(state=tk.DISABLED)
        self.browser_button.config(state=tk.DISABLED)
        self.server_status_var.set("⏹ 已停止")
        self.server_status_label.config(foreground="gray")
        self.update_output("\n" + "=" * 80 + "\n⏹️ 服务器进程已终止。\n" + "=" * 80 + "\n", tag="normal")
        self._refresh_instance_tree()
        self._sync_bottom_bar_for_active_instance()
        self._auto_save_instances()

    def update_output(self, text, tag=None, inst_id=None):
        """Append text to output with optional keyword highlighting.
        
        Lines matching known keywords are automatically colored:
        - error patterns -> red
        - speed/listening -> green
        - warnings -> orange
        - feature keywords -> blue
        - everything else -> gray
        If 'tag' is provided, the entire text block uses that single tag.
        """
        # If inst_id is None, use active instance (or global if no active)
        if inst_id is None and hasattr(self, '_active_instance_id') and self._active_instance_id:
            inst_id = self._active_instance_id
        if tag:
            self.output_text.insert(tk.END, text, tag)
            self.output_text.see(tk.END)
            # Store in per-instance log buffer
            if inst_id and hasattr(self, '_instance_logs'):
                if inst_id not in self._instance_logs:
                    self._instance_logs[inst_id] = deque(maxlen=2000)
                self._instance_logs[inst_id].append((text, tag))
                self._append_instance_log_file(inst_id, text, tag)
            return
        
        # Split into lines to apply per-line coloring
        lines = text.split("\n")
        for i, line in enumerate(lines):
            if i > 0:
                self.output_text.insert(tk.END, "\n")
            if not line.strip():
                self.output_text.insert(tk.END, line)
                continue
            
            # Check against patterns (first match wins)
            resolved_tag = self._resolve_log_tag(line)
            if resolved_tag:
                self.output_text.insert(tk.END, line, resolved_tag)
            else:
                self.output_text.insert(tk.END, line, "normal")
        
        self.output_text.see(tk.END)
        # Store in per-instance log buffer
        if inst_id and hasattr(self, '_instance_logs'):
            if inst_id not in self._instance_logs:
                self._instance_logs[inst_id] = deque(maxlen=2000)
            self._instance_logs[inst_id].append((text, tag))
            self._append_instance_log_file(inst_id, text, tag)
    
    def _monitor_loop(self, url, interval=5, inst_id=None):
        """Continuous health monitoring — ping every `interval` seconds.
        Uses per-instance running flag when inst_id is provided."""
        is_active = lambda: self._instances.get(inst_id, {}).get("is_running", False) if inst_id else self.is_running
        while is_active():
            time.sleep(interval)
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

    def _health_check_loop(self, host, port, inst_id):
        """Periodically ping the server's health endpoint.
        Waits indefinitely for the model to load — no false timeout for large models.
        Uses per-instance running flag for thread-safe sentinel."""
        url = f"http://{host}:{port}/health"
        _is_still_active = lambda: self._instances.get(inst_id, {}).get("is_running", False)
        
        # Phase 1: Quick retry (every 1s, first 30 attempts)
        for attempt in range(1, 31):
            if not _is_still_active():
                return
            try:
                req = urllib.request.Request(url)
                start = time.time()
                with urllib.request.urlopen(req, timeout=2) as resp:
                    elapsed = int((time.time() - start) * 1000)
                    if resp.status == 200:
                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                        self._monitor_loop(url, inst_id=inst_id)
                        return
            except Exception:
                if attempt == 1:
                    self.root.after(0, lambda: self.server_status_var.set("⏳ 启动中…"))
                time.sleep(1)
        
        # Phase 2: Extended wait — model is still loading (every 3s)
        self.root.after(0, lambda: self.server_status_var.set("⏳ 启动中（模型加载中…）"))
        while _is_still_active():
            time.sleep(3)
            try:
                req = urllib.request.Request(url)
                start = time.time()
                with urllib.request.urlopen(req, timeout=5) as resp:
                    elapsed = int((time.time() - start) * 1000)
                    if resp.status == 200:
                        self.root.after(0, lambda ms=elapsed: self._set_server_healthy(ms))
                        self._monitor_loop(url)
                        return
            except Exception:
                pass
        # Process stopped while waiting
        self.root.after(0, lambda: self.server_status_var.set("⏹ 已停止"))
    
    def _set_server_healthy(self, response_ms):
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

    def _build_global_config(self):
        config = {"version": 2, "instances": {}}
        with self._instances_lock:
            for inst_id, inst in list(self._instances.items()):
                data = dict(inst)
                data.pop("process", None)
                data.pop("_logs", None)
                config["instances"][inst_id] = data
        config["_active_instance"] = self._active_instance_id
        config["engine_dirs"] = self.engine_dirs
        config["ms_download_root"] = self.ms_download_root
        config["current_theme"] = self.current_theme
        config["model_repo_roots"] = getattr(self, 'model_repo_roots', [])
        return config
    
    def _auto_save_instances(self):
        try:
            config = self._build_global_config()
            self.config_file = self._get_configs_path("instances.json")
            tmp = self.config_file + ".tmp"
            with open(tmp, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.config_file)
        except Exception as e:
            self.update_output(f"[保存失败] {e}\n", tag="error")
    
    def load_config(self, path=None, browse=False):
        if path is None:
            path = self._get_configs_path("instances.json")
        # Migration: check old location (app dir) and copy to configs/
        if not os.path.isfile(path):
            old_loc = self.get_config_path("instances.json")
            if os.path.isfile(old_loc):
                import shutil
                shutil.copy2(old_loc, path)
        if not os.path.isfile(path):
            # Try old format migration (llama_server_config.json in app dir)
            old_path = self.get_config_path("llama_server_config.json")
            if os.path.isfile(old_path):
                try:
                    with open(old_path, 'r', encoding='utf-8') as f:
                        old = json.load(f)
                    if "version" in old and old.get("version") == 2:
                        self._instances = {}
                        for k, v in old.get("instances", {}).items():
                            self._instances[k] = v
                            self._instances[k]["process"] = None
                        self._active_instance_id = old.get("_active_instance", "")
                        self.engine_dirs = old.get("engine_dirs", [])
                        self.ms_download_root = old.get("ms_download_root", "")
                        theme = old.get("current_theme", "darkly")
                        if theme != self.current_theme:
                            self.toggle_theme()
                        if hasattr(self, 'model_repo_roots'):
                            self.model_repo_roots = old.get("model_repo_roots", [self.model_repo_roots[0]] if self.model_repo_roots else [])
                    else:
                        self._migrate_single_to_instance()
                    return
                except Exception:
                    self._migrate_single_to_instance()
                return
            self._migrate_single_to_instance()
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            if "version" in config and config.get("version") == 2:
                self._instances = {}
                for k, v in config.get("instances", {}).items():
                    self._instances[k] = v
                    self._instances[k]["process"] = None
                self._active_instance_id = config.get("_active_instance", "")
                self.engine_dirs = config.get("engine_dirs", [])
                self.ms_download_root = config.get("ms_download_root", "")
                theme = config.get("current_theme", "darkly")
                if theme != self.current_theme:
                    self.toggle_theme()
                if hasattr(self, 'model_repo_roots'):
                    loaded_roots = config.get("model_repo_roots", [])
                    if loaded_roots:
                        self.model_repo_roots = loaded_roots
            else:
                self._migrate_single_to_instance()
            # Switch to loaded instance
            if self._active_instance_id in self._instances:
                self._params_from_dict(self._instances[self._active_instance_id].get("params", {}))
                inst = self._instances[self._active_instance_id]
                self.selected_engine_dir = inst.get("engine_dir", "")
                self.ctx_size_auto.set(inst.get("ctx_size_auto", False))
                self.custom_arguments = list(inst.get("custom_arguments", []))
        except Exception as e:
            self._migrate_single_to_instance()
    
    def toggle_theme(self):
        """Toggle between darkly (dark) and flatly (light) themes."""
        new_theme = "flatly" if self.current_theme == "darkly" else "darkly"
        self.root.style.theme_use(new_theme)
        self.current_theme = new_theme
        self._theme_btn.config(
            text="🌙 暗色" if new_theme == "flatly" else "☀ 明亮"
        )
    
    # --- 配置管理 (Named Configs) ---


    def open_browser(self):
        inst = self._instances.get(self._active_instance_id)
        if not inst:
            return
        port = inst.get("running_port") or inst.get("params", {}).get("port", "8080")
        host = inst.get("running_host") or inst.get("params", {}).get("host", "127.0.0.1")
        if host == '0.0.0.0': host = 'localhost'
        url = f"http://{host}:{port}"
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

    def _stop_all_instances(self):
        """Kill all running server processes (multi-instance safe)."""
        for inst_id, inst in list(self._instances.items()):
            proc = inst.get("process")
            if proc:
                try:
                    proc.terminate()
                    proc.wait(timeout=3)
                except Exception:
                    pass
            pid = inst.get("running_pid", "")
            if pid:
                try:
                    if self._is_windows():
                        subprocess.run(["taskkill", "/F", "/PID", str(pid)],
                            capture_output=True, timeout=3, startupinfo=self._startupinfo())
                    else:
                        os.kill(int(pid), signal.SIGTERM)
                except Exception:
                    pass
            inst["is_running"] = False
            inst["process"] = None
            inst["running_pid"] = ""
            inst["health_active"] = False

    def quit_application(self, icon=None, item=None):
        """Quit app from tray."""
        self._stop_all_instances()
        if self.tray_icon:
            self.tray_icon.stop()
        self.root.after(0, self.root.destroy)

    def hide_to_tray(self):
        """Hide window and show tray icon."""
        self.root.withdraw()
        if self.tray_icon is None:
            self.tray_icon = self.create_tray_icon()
            threading.Thread(target=self.tray_icon.run, daemon=True).start()

    def _release_switch_lock(self):
        """Release the instance switch lock."""
        self._is_switching = False

    def _get_logs_dir(self):
        d = os.path.join(self._get_app_dir(), "logs")
        os.makedirs(d, exist_ok=True)
        return d

    def _append_instance_log_file(self, inst_id, text, tag):
        try:
            path = os.path.join(self._get_logs_dir(), f"{inst_id}.log")
            with open(path, "a", encoding="utf-8") as f:
                f.write(f"{tag or ''}|{text}")
        except Exception:
            pass

    def _load_instance_log_file(self, inst_id):
        try:
            path = os.path.join(self._get_logs_dir(), f"{inst_id}.log")
            if not os.path.isfile(path):
                return
            buf = deque(maxlen=2000)
            with open(path, "r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.rstrip("\n\r")
                    if "|" in raw:
                        tag, line = raw.split("|", 1)
                    else:
                        tag, line = "", raw
                    buf.append((line.rstrip('\r') + '\n', tag or None))
            self._instance_logs[inst_id] = buf
        except Exception:
            pass

    _log_patterns = None

    def _resolve_log_tag(self, text):
        if self._log_patterns is None:
            self._log_patterns = [
                ("error", re.compile(r'\berror\b|\btraceback\b|\bexception\b', re.I)),
                ("warn", re.compile(r'\bwarn\b|注意|\bfailed\b|\bfail\b', re.I)),
                ("speed", re.compile(r'\btoken\b|\btok/s\b|\btokens/s\b', re.I)),
                ("info", re.compile(r'\binfo\b|\bstart\b|\bbuilding\b|\brunning\b', re.I)),
            ]
        for tag_name, pattern in self._log_patterns:
            if pattern.search(text):
                return tag_name
        return None

    def _replay_instance_log(self, inst_id):
        self.output_text.delete(1.0, tk.END)
        lines = self._instance_logs.get(inst_id, [])
        for line, tag in lines:
            if tag is None:
                tag = self._resolve_log_tag(line)
            self.output_text.insert(tk.END, line, tag)
        self.output_text.see(tk.END)

    def _sync_bottom_bar_for_active_instance(self):
        inst = self._instances.get(self._active_instance_id)
        if not inst:
            self.server_status_var.set("")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.browser_button.config(state=tk.DISABLED)
            return
        running = inst.get("is_running", False)
        if running:
            port = inst.get("running_port") or inst.get("params", {}).get("port", "?")
            self.server_status_var.set(f"▶ {inst['name']}·运行中 ({port})")
            self.server_status_label.config(foreground="green")
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.browser_button.config(state=tk.NORMAL)
        else:
            self.server_status_var.set(f"⏹ {inst['name']}·已停止")
            self.server_status_label.config(foreground="gray")
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.browser_button.config(state=tk.DISABLED)

    def _migrate_single_to_instance(self):
        with self._instances_lock:
            inst_id = "instance_1"
            self._instances[inst_id] = {
                "id": inst_id,
                "name": "LLaMA 1",
                "params": self._params_to_dict(),
                "engine_dir": self.selected_engine_dir,
                "ctx_size_auto": self.ctx_size_auto.get(),
                "custom_arguments": list(self.custom_arguments),
                "process": None,
                "is_running": False,
                "health_active": False,
                "running_port": "",
                "running_host": "",
            }
        self._active_instance_id = inst_id

    def _save_active_instance(self):
        with self._instances_lock:
            inst = self._instances.get(self._active_instance_id)
            if not inst:
                return
            inst["params"] = self._params_to_dict()
            inst["engine_dir"] = self.selected_engine_dir
            inst["ctx_size_auto"] = self.ctx_size_auto.get()
            inst["custom_arguments"] = list(self.custom_arguments)

    def _switch_to_instance(self, instance_id):
        with self._instances_lock:
            if instance_id not in self._instances:
                return
            self._is_switching = True
            self._active_instance_id = instance_id
            inst = self._instances[instance_id]
            params_copy = dict(inst.get("params", {}))
            eng_dir = inst.get("engine_dir", "")
            ctx_auto = inst.get("ctx_size_auto", False)
            cust_args = list(inst.get("custom_arguments", []))
            is_running = inst.get("is_running", False)
        self._params_from_dict(params_copy)
        self.selected_engine_dir = eng_dir
        self.ctx_size_auto.set(ctx_auto)
        self.custom_arguments = cust_args
        self.rebuild_custom_args_list()
        self.update_all_sliders()
        self.root.after_idle(lambda: self.scan_engines() if hasattr(self, 'scan_engines') else None)
        self.root.after_idle(lambda: self.scan_downloaded_models() if hasattr(self, 'scan_downloaded_models') else None)
        self._sync_bottom_bar_for_active_instance()
        self._replay_instance_log(instance_id)
        self.update_output(f"\n[切换到 {instance_id}]\n")
        self.root.after(0, self._auto_save_instances)
        if hasattr(self, '_set_run_lock'):
            self._set_run_lock(is_running)
        self.root.after(200, lambda: self._release_switch_lock())

    def _restore_running_instances(self):
        self.update_output("检查后台进程... ")
        for inst_id, inst in list(self._instances.items()):
            self._load_instance_log_file(inst_id)
            with self._instances_lock:
                pid = inst.get("running_pid", "")
            self.update_output(f"{inst['name']}: PID={pid} ")
            if not pid:
                continue
            still_running = False
            try:
                pid_int = int(pid)
                if self._is_windows():
                    r = subprocess.run(
                        ["tasklist", "/FI", f"PID eq {pid_int}", "/NH"],
                        capture_output=True, timeout=5, startupinfo=self._startupinfo()
                    )
                    still_running = str(pid_int) in r.stdout.decode(self._sys_encoding, errors='replace')
                else:
                    os.kill(pid_int, 0)
                    still_running = True
            except (OSError, ValueError):
                still_running = False
            except Exception as e:
                self.update_output(f"错误:{e} ")
                still_running = False
            
            if still_running:
                self.update_output("→存活\n")
                params = inst.get("params", {})
                host = params.get("host", "127.0.0.1")
                port = params.get("port", "")
                if port:
                    with self._instances_lock:
                        inst["is_running"] = True
                        inst["running_port"] = port
                        inst["running_host"] = host
                        inst["health_active"] = True
                    self.update_output(f"✓ 恢复 {inst['name']}·后台进程 (PID {pid}, 端口 {port})\n", tag="speed")
                    url = f"http://{host}:{port}/health"
                    threading.Thread(
                        target=self._monitor_loop,
                        args=(url, 5, inst_id),
                        daemon=True
                    ).start()
            else:
                with self._instances_lock:
                    inst["running_pid"] = ""
        self._refresh_instance_tree()
        self._sync_bottom_bar_for_active_instance()

    def setup_instance_tab(self, parent):
        # ── Toolbar ──
        toolbar = ttk.Frame(parent)
        toolbar.grid(row=0, column=0, sticky=tk.EW, pady=(0, 5))
        self.inst_add_btn = ttk.Button(toolbar, text="➕ 添加实例",
            command=self._instance_add, bootstyle="success")
        self.inst_add_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.inst_add_btn, "创建新实例。")
        self.inst_clone_btn = ttk.Button(toolbar, text="📋 克隆",
            command=self._instance_clone, state=tk.DISABLED, bootstyle="info")
        self.inst_clone_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.inst_clone_btn, "复制选中实例的配置为新实例。")
        self.inst_rename_btn = ttk.Button(toolbar, text="✏ 重命名",
            command=self._instance_rename, state=tk.DISABLED, bootstyle="secondary")
        self.inst_rename_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.inst_rename_btn, "修改选中实例的名称。")
        self.inst_delete_btn = ttk.Button(toolbar, text="🗑 删除",
            command=self._instance_delete, state=tk.DISABLED, bootstyle="danger-outline")
        self.inst_delete_btn.pack(side=tk.LEFT, padx=(0, 5))
        ToolTip(self.inst_delete_btn, "删除选中实例（需先停止该实例）。")
        self.inst_help = ttk.Label(toolbar, text="", foreground="gray", font=("", 8))
        self.inst_help.pack(side=tk.RIGHT, padx=(5, 0))

        # ── Instance TreeView ──
        tree_frame = ttk.Frame(parent)
        tree_frame.grid(row=1, column=0, sticky=tk.NSEW)
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)

        cols = ('status', 'port', 'model', 'engine')
        style = ttk.Style()
        style.configure("Instance.Treeview")
        style.map("Instance.Treeview",
            background=[("selected", "#2c6496")],
            foreground=[("selected", "white")])
        self.instance_tree = ttk.Treeview(tree_frame, columns=cols, show='tree headings',
            selectmode='browse', height=10, style="Instance.Treeview")
        self.instance_tree.heading('#0', text='实例名称')
        self.instance_tree.column('#0', width=200, minwidth=140)
        self.instance_tree.heading('status', text='状态')
        self.instance_tree.column('status', width=90)
        self.instance_tree.heading('port', text='端口')
        self.instance_tree.column('port', width=70)
        self.instance_tree.heading('model', text='模型')
        self.instance_tree.column('model', width=250, minwidth=150)
        self.instance_tree.heading('engine', text='引擎')
        self.instance_tree.column('engine', width=180, minwidth=100)

        tree_scroll = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.instance_tree.yview)
        self.instance_tree.configure(yscrollcommand=tree_scroll.set)
        self.instance_tree.grid(row=0, column=0, sticky=tk.NSEW)
        tree_scroll.grid(row=0, column=1, sticky=tk.NS)

        self.instance_tree.bind('<<TreeviewSelect>>', self._on_instance_tree_select)
        self.instance_tree.tag_configure('running', foreground='#27ae60')

        # ── Status bar ──
        self.inst_status_var = tk.StringVar(value="")
        self.inst_status = ttk.Label(parent, textvariable=self.inst_status_var, foreground="gray")
        self.inst_status.grid(row=2, column=0, sticky=tk.W, pady=(5, 0))

        # Configure grid weights
        parent.rowconfigure(1, weight=1)
        parent.columnconfigure(0, weight=1)

    def _refresh_instance_tree(self):
        if not hasattr(self, 'instance_tree'):
            return
        for item in self.instance_tree.get_children():
            self.instance_tree.delete(item)

        for inst_id, inst in self._instances.items():
            is_active = (inst_id == self._active_instance_id)
            running = inst.get("is_running", False)
            status_str = "● 运行中" if running else "○ 已停止"
            port_str = inst.get("running_port") or inst.get("params", {}).get("port", "")
            model_str = ""
            engine_str = ""
            params = inst.get("params", {})
            if params.get("model_path", ""):
                model_str = os.path.basename(params["model_path"])
            elif inst.get("engine_dir", ""):
                model_str = f"(引擎: {os.path.basename(inst['engine_dir'])})"
            else:
                model_str = "(未配置)"
            eng_dir = inst.get("engine_dir", "")
            if eng_dir:
                engine_str = os.path.basename(eng_dir)
            else:
                engine_str = "(默认)"

            display_name = f"⭐ {inst['name']}" if is_active else f"   {inst['name']}"
            tags = []
            if running:
                tags.append('running')
            if is_active:
                tags.append('active')
            self.instance_tree.insert('', tk.END, iid=inst_id,
                text=display_name, values=(status_str, port_str, model_str, engine_str),
                tags=tags)

        running_count = sum(1 for inst in self._instances.values() if inst.get("is_running"))
        total = len(self._instances)
        self.inst_status_var.set(f"共 {total} 个实例，{running_count} 个运行中")
        self.inst_help.config(text="选中实例自动切换为当前配置，可在底部栏启动/停止。")
        if self._active_instance_id in self._instances:
            try:
                self.instance_tree.selection_set(self._active_instance_id)
                self.instance_tree.see(self._active_instance_id)
                self.instance_tree.focus(self._active_instance_id)
            except tk.TclError:
                pass

    def _update_star_markers(self, active_iid):
        if not hasattr(self, 'instance_tree'):
            return
        for item in self.instance_tree.get_children():
            d = self._instances.get(item)
            if d:
                prefix = "⭐ " if item == active_iid else "   "
                try:
                    self.instance_tree.item(item, text=f"{prefix}{d['name']}")
                except tk.TclError:
                    pass

    def _on_instance_tree_select(self, event):
        if self._is_switching:
            return
        sel = self.instance_tree.selection()
        if not sel:
            return
        self._is_switching = True
        try:
            inst_id = sel[0]
            if inst_id not in self._instances:
                return
            inst = self._instances[inst_id]
            running = inst.get("is_running", False)
            self.inst_clone_btn.config(state=tk.NORMAL)
            self.inst_rename_btn.config(state=tk.NORMAL)
            self.inst_delete_btn.config(state=tk.DISABLED if running else tk.NORMAL)
            if inst_id != self._active_instance_id:
                self._save_active_instance()
                self._active_instance_id = inst_id
                self._switch_to_instance(inst_id)
                self._sync_bottom_bar_for_active_instance()
                if hasattr(self, '_update_star_markers'):
                    self._update_star_markers(inst_id)
        finally:
            self.root.after(200, lambda: self._release_switch_lock())

    def _instance_add(self):
        with self._instances_lock:
            n = 1
            while f"instance_{n}" in self._instances:
                n += 1
            inst_id = f"instance_{n}"
            used_ports = set()
            for inst in self._instances.values():
                p = inst.get("params", {}).get("port", "")
                if p:
                    used_ports.add(p)
            default_port = "8082"
            if default_port in used_ports:
                for p in range(8090, 9000):
                    if str(p) not in used_ports:
                        default_port = str(p)
                        break

            self._instances[inst_id] = {
                "id": inst_id,
                "name": f"LLaMA {n}",
                "params": dict((ck, default) for ck, an, flag, kind, default in self._PARAM_DEFS),
                "engine_dir": self.selected_engine_dir,
                "ctx_size_auto": False,
                "custom_arguments": [],
                "process": None,
                "is_running": False,
                "health_active": False,
                "running_port": "",
                "running_host": "",
                "running_pid": "",
            }
            self._instances[inst_id]["params"]["port"] = default_port
            self._instances[inst_id]["params"]["host"] = "127.0.0.1"
        self._switch_to_instance(inst_id)
        self._refresh_instance_tree()
        Messagebox.ok(
            f"已添加实例「{self._instances[inst_id]['name']}」\n"
            f"端口预设为 {default_port}，可在「网络与API」标签页修改。",
            "添加成功", parent=self.root)

    def _instance_clone(self):
        sel = self.instance_tree.selection()
        if not sel:
            return
        src_id = sel[0]
        with self._instances_lock:
            if src_id not in self._instances:
                return
            src = self._instances[src_id]
            n = 1
            while f"instance_{n}" in self._instances:
                n += 1
            new_id = f"instance_{n}"
            new_params = dict(src["params"])
            old_port = src["params"].get("port", "8082")
            try:
                new_params["port"] = str(int(old_port) + 1)
            except ValueError:
                new_params["port"] = "8083"
            self._instances[new_id] = {
                "id": new_id,
                "name": f"{src['name']} (副本)",
                "params": new_params,
                "engine_dir": src.get("engine_dir", ""),
                "ctx_size_auto": src.get("ctx_size_auto", False),
                "custom_arguments": list(src.get("custom_arguments", [])),
                "process": None,
                "is_running": False,
                "health_active": False,
                "running_port": "",
                "running_host": "",
                "running_pid": "",
            }
        self._switch_to_instance(new_id)
        self._refresh_instance_tree()
        self.scan_engines()
        self.scan_downloaded_models()
        Messagebox.ok(
            f"已克隆实例「{src['name']}」为「{self._instances[new_id]['name']}」\n"
            f"端口已自动 +1。",
            "克隆成功", parent=self.root)

    def _instance_rename(self):
        sel = self.instance_tree.selection()
        if not sel:
            return
        inst_id = sel[0]
        if inst_id not in self._instances:
            return
        inst = self._instances[inst_id]
        dialog = ttk.Toplevel(self.root)
        dialog.title("重命名实例")
        dialog.geometry("350x130")
        dialog.transient(self.root)
        dialog.grab_set()
        ttk.Label(dialog, text="新实例名称:", padding="10 10 0 5").pack(anchor=tk.W)
        name_var = tk.StringVar(value=inst["name"])
        entry = ttk.Entry(dialog, textvariable=name_var, width=30)
        entry.pack(padx=10, pady=5, fill=tk.X)
        entry.focus_set()
        entry.selection_range(0, tk.END)
        def do_rename():
            n = name_var.get().strip()
            if n:
                if any(v["name"] == n and k != inst_id for k, v in self._instances.items()):
                    Messagebox.show_warning("该名称已被其他实例使用。", "重复名称", parent=dialog)
                    return
                dialog.destroy()
                inst["name"] = n
                self._refresh_instance_tree()
                self._sync_bottom_bar_for_active_instance()
                self._auto_save_instances()
            else:
                Messagebox.show_error("名称不能为空！", "错误", parent=dialog)
        entry.bind('<Return>', lambda e: do_rename())
        entry.bind('<Escape>', lambda e: dialog.destroy())
        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=10)
        ttk.Button(btn_frame, text="确定", command=do_rename, bootstyle="success").pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy, bootstyle="secondary").pack(side=tk.LEFT, padx=5)

    def _instance_delete(self):
        sel = self.instance_tree.selection()
        if sel:
            inst_id = sel[0]
        else:
            inst_id = self._active_instance_id
        with self._instances_lock:
            if not inst_id or inst_id not in self._instances:
                return
            inst = self._instances[inst_id]
            if inst.get("is_running"):
                self.root.after(0, lambda: Messagebox.show_warning(
                    "无法删除正在运行的实例。请先停止该实例。", "提示", parent=self.root))
                return
            if len(self._instances) <= 1:
                self.root.after(0, lambda: Messagebox.show_warning(
                    "至少保留一个实例。", "提示", parent=self.root))
                return
        reply = tk.messagebox.askokcancel(
            "确认删除",
            f"确定删除实例「{inst['name']}」？\n此操作不可撤销。",
            parent=self.root
        )
        if not reply:
            return
        with self._instances_lock:
            del self._instances[inst_id]
            need_switch = self._active_instance_id == inst_id
            if need_switch:
                new_active = next(iter(self._instances.keys()))
        try:
            if need_switch:
                self._switch_to_instance(new_active)
        finally:
            self._refresh_instance_tree()
            self._auto_save_instances()

    def _set_run_lock(self, locked):
        state = tk.DISABLED if locked else tk.NORMAL
        for frame in getattr(self, '_param_frames', []):
            try:
                self._set_state_recursive(frame, state)
                txt = frame.cget('text')
                if locked and ' 🔒' not in txt:
                    frame.config(text=txt + ' 🔒')
                elif not locked:
                    frame.config(text=txt.replace(' 🔒', ''))
            except Exception:
                pass
        if locked:
            inst = self._instances.get(self._active_instance_id)
            if inst:
                self.start_button.config(text=f"▶ {inst['name']}")
        else:
            self.start_button.config(text="▶ 启动")

    def _check_port_conflict(self, port, exclude_instance=None):
        for inst_id, inst in self._instances.items():
            if inst_id == exclude_instance:
                continue
            if not inst.get("is_running"):
                continue
            rp = inst.get("running_port", "")
            if rp and rp == str(port):
                return inst_id
        return None


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
        if any(inst.get("is_running") for inst in app._instances.values()) and TRAY_AVAILABLE:
            app.hide_to_tray()
        else:
            app._stop_all_instances()
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_closing)
    root.mainloop()



if __name__ == "__main__":
    main()