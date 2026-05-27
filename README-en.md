# LLaMA Server Manager (English)

> [🇨🇳 中文](README.md)
>
> ⚠️ **v1.9.0 Breaking Change**: Cross-platform support (Linux/macOS), GitHub Actions CI/CD, and major code quality improvements. `llama-server.exe` is no longer hardcoded; port killing now works on Linux; multiple logic defects fixed. All users are recommended to upgrade.
>
> Fork of [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) with deep customization — graphical management for llama.cpp servers.

![CI/CD](https://github.com/jerrydong1988/llama-cpp-GUI-zh/actions/workflows/build.yml/badge.svg)

A full-featured GUI application to manage the complete `llama-server` lifecycle: **Download model → Select engine → Configure parameters → Start & monitor**. No more complex command-line arguments.

---

## Tab Overview

| Tab | Function |
|-----|----------|
| 🏪 **Model Repository** | Download models (ModelScope), browse downloaded models, multi-directory scanning (LM Studio / NovaMax) |
| 🖥 **Engine** | Manage multiple llama.cpp engine versions, multi-engine directory persistence, cross-platform exe auto-detection |
| 📁 **Model** | Model path, LoRA, multimodal projector, chat template, reasoning toggle |
| ⚙️ **Generation** | Temperature, Top-K/P, repetition penalty, and advanced sampling parameters |
| 🚀 **Performance** | Context size, GPU layers, batch processing |
| 🔬 **Advanced** | Flash Attention, speculative decoding (MTP/draft), cache type, server reliability |
| 🌐 **Server & API** | Network config, API keys, SSL, custom parameters |
| 📊 **Server Output** | Real-time logs | Running status |

---

## Features

### ⬇ ModelScope Download
- **China-first**: Download from ModelScope — fast, stable, no API key required
- **Checkbox selection**: Intuitive checkboxes for quantized versions
- **Auto mmproj association**: Auto-selects BF16 multimodal projector
- **Draft model download**: Supports downloading draft models for speculative decoding
- **Directory structure**: Saved to `models/{namespace}/{repo}/` — no name collisions
- **Cancel support**: Cancel anytime during download, auto-cleanup temp files

### 🏪 Model Repository
- **Multi-directory scanning**: Default `models/` directory + any custom directories (LM Studio, NovaMax, etc.)
- **Tree structure**: Display organized by repo name / directory structure
- **Metadata reading**: Show architecture, context length, quantization type on selection (LRU-cached for performance)
- **One-click load**: Load model path / mmproj path into config instantly
- **Delete files**: Confirm then delete from disk, list auto-refreshes
- **Open directory**: Locate files in file explorer

### 🖥 Engine Management
- **Multi-engine switching**: Browse installed llama.cpp engines, select default
- **Auto-discovery**: Automatically scan `engines/` directory, custom engine directories persisted across restarts
- **Backend detection**: Auto-identify ROCm / Vulkan backend types
- **Cross-platform**: Auto-adapts to `llama-server.exe` (Windows) or `llama-server` (Linux/macOS)

### ⚡ Server Operation
- **One-click start/stop**: Easily manage server processes
- **Health check**: Auto-ping `/health` endpoint after startup, real-time response time display
- **Status monitoring**: Running / Disconnected indicators
- **Real-time logs**: Live server output monitoring
- **Cross-platform process kill**: tasklist/powershell on Windows, lsof/os.kill on Linux, signal on macOS
- **API access**: One-click open API URL

### 🎛 Configuration Management
- **Multi-instance management**: Create, clone, rename, and delete instances, each with independent parameters
- **Auto-load**: Instance switching restores all parameters + model repo directories
- **JSON persistence**: Configs stored in `configs/` directory, shareable and backupable
- **Custom parameters**: Support for extra llama-server parameters not covered by the GUI
- **Thread-safe**: Instance state read/write protected by lock to prevent race conditions

### 🚀 CI/CD Automated Builds
- **GitHub Actions**: Auto-builds Windows + Linux executables when version tags are pushed
- **Auto-release**: Build artifacts automatically uploaded to GitHub Releases
- **Manual trigger**: Supports `workflow_dispatch` for on-demand builds

### 📋 Other
- **System tray**: Minimize to tray for background operation
- **GGUF metadata**: Read GGUF file headers directly, display architecture, context, quantization (LRU-cached)
- **Cross-platform**: Windows / Linux / macOS (`os.startfile` / `xdg-open` / `open` auto-adaptation)

---

## Running from Source

```bash
git clone https://github.com/jerrydong1988/llama-cpp-GUI-zh.git
cd llama-cpp-GUI-zh
pip install ttkbootstrap pillow
python llama-server_gui_new.py
```

> System tray requires `pystray` (optional).

## Building the Executable

### Local Build

```bash
pip install pyinstaller ttkbootstrap pillow
python build_exe.py              # directory mode (faster startup)
python build_exe.py --onefile    # single-file mode (easier distribution)
```

### Via CI/CD

Push a version tag to trigger GitHub Actions:

```bash
git tag v1.9.0
git push --tags
```

Download the compiled executable from the [Releases](https://github.com/jerrydong1988/llama-cpp-GUI-zh/releases) page.

## Directory Structure

```
LLaMA-Server-GUI/
├── llama-server_gui_new.py   # Main program
├── build_exe.py              # Build script (supports --onefile)
├── .github/workflows/        # GitHub Actions CI/CD configuration
├── configs/                  # Named configs (JSON)
├── models/                   # Downloaded models
│   └── {namespace}/{repo}/
├── engines/                  # Engine directory (optional)
│   └── {version}/llama-server*
└── dist/                     # Build output
```

## System Requirements

- **Windows 10/11** / **Linux** / **macOS** (supported since v1.9.0)
- Python 3.7+ (when running from source)
- `llama-server` executable

## Differences from the Original Project

This repository is a deep customization of [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI):

| Feature | Original | This Fork |
|---------|----------|-----------|
| Model Download | ❌ | ✅ ModelScope (main + draft models) |
| Model Repository | ❌ | ✅ Multi-directory + metadata + load/delete |
| Engine Management | ❌ | ✅ Multi-version + multi-engine directory persistence |
| Named Configs | ❌ | ✅ Multi-instance management + quick-switch dropdown |
| Health Check | ❌ | ✅ Auto-ping + response time |
| GGUF Parsing | ❌ | ✅ Architecture/context/quantization display (LRU-cached) |
| Chinese UI | ❌ | ✅ Full localization |
| Parameter Coverage | Partial | ✅ Full MTP/speculative decoding support |
| Context Slider | Fixed (128K) | ✅ Auto-adapts to model's max context |
| Advanced Sampling | ❌ | ✅ Mirostat / XTC / Dynamic Temp / Typical-P / DRY |
| SSL Support | ❌ | ✅ SSL key/cert file selectors |
| Structured Output | ❌ | ✅ Grammar file + JSON schema |
| Reasoning Controls | ❌ | ✅ Reasoning budget + context shift |
| Cross-platform | ❌ | ✅ Windows/Linux/macOS compatibility |
| CI/CD Automated Builds | ❌ | ✅ GitHub Actions + Release |
| Thread Safety | ❌ | ✅ Instance state locking |

## License

MIT
