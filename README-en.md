# LLaMA Server Manager (English)

> [🇨🇳 中文](README.md)
>
> ⚠️ **v1.5.0 Breaking Change**: Only supports the latest llama.cpp (≥ commit b39a7bf). `--spec-type` value `mtp` replaced with `draft-mtp`, built-in Web UI removed. For old engines, use v1.4.0 or earlier.
>
> Fork of [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) with deep customization — graphical management for llama.cpp servers, gradually replacing NovaMax

A full-featured GUI application to manage the complete `llama-server` lifecycle: **Download model → Select engine → Configure parameters → Start & monitor**. No more complex command-line arguments.

---

## Tab Overview

| Tab | Function |
|-----|----------|
| 🏪 **Model Repository** | Download models (ModelScope), browse downloaded models, multi-directory scanning (LM Studio / NovaMax) |
| 🖥 **Engine** | Manage multiple llama.cpp engine versions, multi-engine directory persistence |
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
- **Metadata reading**: Show architecture, context length, quantization type on selection
- **One-click load**: Load model path / mmproj path into config instantly
- **Delete files**: Confirm then delete from disk, list auto-refreshes
- **Open directory**: Locate files in File Explorer

### 🖥 Engine Management
- **Multi-engine switching**: Browse installed llama.cpp engines, select default
- **Auto-discovery**: Automatically scan `engines/` directory, custom engine directories persisted across restarts
- **Backend detection**: Auto-identify ROCm / Vulkan backend types
- **Custom directories**: Add any directory containing `llama-server.exe`

### ⚡ Server Operation
- **One-click start/stop**: Easily manage server processes
- **Health check**: Auto-ping `/health` endpoint after startup, real-time response time display
- **Status monitoring**: Running / Disconnected indicators
- **Real-time logs**: Live server output monitoring
- **API access**: One-click open API URL (new llama.cpp has no built-in Web UI; use an external client)

### 🎛 Configuration Management
- **Named configs**: Save multiple named configs (e.g. `draft_qwen`, `draft_gemma`), quick-switch from dropdown
- **Auto-load**: Config switch restores all parameters + model repo directories
- **JSON persistence**: Configs stored in `configs/` directory, shareable and backupable
- **Custom parameters**: Support for extra llama-server parameters not covered by the GUI

### 📋 Other
- **System tray**: Minimize to tray for background operation
- **GGUF metadata**: Read GGUF file headers directly, display architecture, context, etc.
- **Context slider auto-adjust**: When selecting a model, automatically reads its max context length and adjusts the slider limit (500ms debounce)

---

## Running from Source

```bash
git clone https://github.com/jerrydong1988/llama-cpp-GUI-zh.git
cd llama-cpp-GUI-zh
pip install ttkbootstrap pillow pystray
python llama-server_gui_new.py
```

## Building the exe

```bash
pip install pyinstaller ttkbootstrap pillow pystray
python build_exe.py
```

The compiled exe will be at `dist/LLaMA-Server-GUI.exe`.

## Directory Structure

```
LLaMA-Server-GUI/
├── llama-server_gui_new.py   # Main program
├── build_exe.py              # Build script
├── configs/                  # Named configs (JSON)
├── models/                   # Downloaded models
│   └── {namespace}/{repo}/
├── engines/                  # Engine directory (optional)
│   └── {version}/llama-server.exe
└── dist/                     # Build output
```

## System Requirements

- Windows 10/11 (primary support)
- Python 3.7+ (when running from source)
- `llama-server` executable

## Differences from the Original Project

This repository is a deep customization of [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI):

| Feature | Original | This Fork |
|---------|----------|-----------|
| Model Download | ❌ | ✅ ModelScope (main + draft models) |
| Model Repository | ❌ | ✅ Multi-directory + metadata + load/delete |
| Engine Management | ❌ | ✅ Multi-version + multi-engine directory persistence |
| Named Configs | ❌ | ✅ Quick-switch dropdown |
| Health Check | ❌ | ✅ Auto-ping + response time |
| GGUF Parsing | ❌ | ✅ Architecture/context/quantization display |
| Chinese UI | ❌ | ✅ Full localization |
| Parameter Coverage | Partial | ✅ Full MTP/speculative decoding support |
| Context Slider | Fixed (128K) | ✅ Auto-adapts to model's max context |
| Advanced Sampling | ❌ | ✅ Mirostat / XTC / Dynamic Temp / Typical-P / DRY |
| SSL Support | ❌ | ✅ SSL key/cert file selectors |
| Structured Output | ❌ | ✅ Grammar file + JSON schema |
| Reasoning Controls | ❌ | ✅ Reasoning budget + context shift |

## License

MIT
