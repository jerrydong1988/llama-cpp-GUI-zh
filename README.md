# LLaMA 服务器管理器（中文版）

> 基于 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 汉化 — 图形化管理 llama.cpp 服务器

一个功能完整的图形界面程序，用于管理和配置 `llama-server` 可执行文件。告别复杂的命令行参数，通过直观的界面轻松启动、停止和监控你的本地 LLaMA 模型服务器。

## 界面预览

| 选项卡 | 功能 |
|--------|------|
| 📁 **模型** | 加载 GGUF 模型、LoRA 适配器、多模态投影器 |
| ⚙️ **生成参数** | 温度、Top-K/P、重复惩罚等采样参数 |
| 🚀 **性能** | 上下文大小、GPU 层数、批处理、持续批处理 |
| 🔬 **高级** | Flash Attention、内存锁定、NUMA、推测解码 |
| 🌐 **服务器与API** | 网络配置、API 密钥、自定义参数 |
| 📊 **服务器输出** | 实时日志监控 |

## 功能特性

- **完整配置管理** — 可视化配置所有 llama-server 参数
- **一键启停** — 轻松管理服务器进程
- **实时日志** — 服务器输出实时监控
- **配置保存/加载** — JSON 格式配置持久化
- **浏览器集成** — 一键打开 Web UI
- **系统托盘** — 支持最小化到托盘后台运行
- **自定义参数** — 支持 GUI 未覆盖的额外参数

## 下载与使用

### 方案一：直接下载可执行文件

从 [Releases](https://github.com/jerrydong1988/llama-cpp-GUI-zh/releases) 页面下载最新版本：

1. 下载 `LLaMA-Server-GUI.exe`
2. 将 `llama-server.exe` 放在同一目录或添加到系统 PATH
3. 双击运行 `LLaMA-Server-GUI.exe`

> ⚠ `llama-server.exe` 是 llama.cpp 项目的一部分，可从 [llama.cpp releases](https://github.com/ggml-org/llama.cpp/releases) 下载。

### 方案二：从源码运行

```bash
# 克隆仓库
git clone https://github.com/jerrydong1988/llama-cpp-GUI-zh.git
cd llama-cpp-GUI-zh

# 安装依赖
pip install ttkbootstrap pillow pystray

# 运行
python llama-server_gui_new.py
```

### 方案三：自行编译 exe

```bash
pip install pyinstaller ttkbootstrap pillow pystray
python build_exe.py
```

编译后的 exe 位于 `dist/` 目录。

## 系统要求

- Windows / Linux / macOS
- Python 3.7+（从源码运行时）
- `llama-server` 可执行文件

## 涉及的中文汉化

本仓库在原始项目基础上做了完整的中文本地化：

- ✅ 窗口标题、选项卡名称
- ✅ 所有按钮和标签
- ✅ 参数分组标题
- ✅ 所有 tooltip 提示文字
- ✅ 消息框信息
- ✅ 系统托盘菜单
- ✅ 服务器运行状态提示

所有 CLI 参数名（`-m`, `--temp`, `-ngl` 等）及标准术语（Flash Attention、Top-K/P、NUMA、MoE 等）保留英文，确保与 llama.cpp 官方文档兼容。

汉化脚本见 `translate_zh.py`，可复用于其他版本。

## 原项目

本仓库是 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 的中文汉化分支，感谢原作者的出色工作。

## 许可证

MIT
