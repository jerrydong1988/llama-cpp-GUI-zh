# LLaMA 服务器管理器（中文版）

> [🇺🇸 English](README-en.md)

> 基于 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 深度二次开发 — 图形化管理 llama.cpp 服务器，简化llama.cpp的命令操作。感谢yossifibrahem开源了本项目，同时中文版改进工作主要贡献是Hermes Agent及背后的Deepseek v4 Flash模型，本人只提供了想法，具体实现由Hermes Agent及背后的Deepseek v4 Flash模型完成。

一个功能完整的图形界面程序，用于管理 `llama-server` 全生命周期：**下载模型 → 选择引擎 → 配置参数 → 启动监控**。告别复杂的命令行参数。


| 标签页 | 功能 |
|--------|------|
| 🏪 **模型仓库** | 下载模型（ModelScope）、浏览已下载模型、多目录扫描（支持 LM Studio/NovaMax） |
| 🖥 **引擎** | 管理多个 llama.cpp 引擎版本、切换默认引擎（自动发现 NovaMax 引擎） |
| 📁 **模型** | 模型路径、LoRA、多模态投影器、对话模板、推理开关 |
| ⚙️ **生成参数** | 温度、Top-K/P、重复惩罚等采样参数 |
| 🚀 **性能** | 上下文大小、GPU 层数、批处理 |
| 🔬 **高级** | Flash Attention、推测解码（MTP/draft）、缓存类型、服务器可靠性 |
| 🌐 **服务器与API** | 网络配置、API 密钥、自定义参数 |
| 📊 **服务器输出** | 实时日志 | 运行状态 |

---

## 界面一览
<img width="1654" height="1388" alt="image" src="https://github.com/user-attachments/assets/b87fc72b-bfb2-4fe5-b1e4-b77119b19f50" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/a0aca3ce-51dd-4055-800a-e99ea5ad5c75" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/8ed40804-4eac-47ff-bb38-240c52a96a2f" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/6fd930ec-66f4-4f8f-87b2-c9e67b2ceeb5" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/feebd556-7512-402e-aa11-fc47218e8b6f" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/d1043a8e-0952-4547-91b7-58e8e08164bc" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/7ba38a20-6a03-43b6-9d62-bbc9f18e4830" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/9b0f38c5-8a9a-415e-863b-2e7b17dc8aaf" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/730b3b1e-edc9-436a-87bf-1095d68d2b8e" />
<img width="1679" height="1390" alt="image" src="https://github.com/user-attachments/assets/70f4d199-bfeb-46fe-b255-0044f401dd71" />




---



## 功能特性

### ⬇ ModelScope 模型下载
- **国内优先**：从 ModelScope（魔搭社区）下载模型，速度快、稳定，无需 API Key
- **勾选框选择**：直观勾选要下载的量化版本
- **自动关联 mmproj**：自动预勾选 BF16 版多模态投影器
- **草稿模型下载**：支持推测解码的草稿模型下载
- **目录结构**：下载到 `models/{命名空间}/{仓库}/`，多模型不混淆
- **取消支持**：下载期间随时取消，自动清理临时文件

### 🏪 模型仓库管理
- **多目录扫描**：默认 `models/` 目录 + 任意自定义目录（LM Studio、NovaMax 等）
- **树形结构**：按仓库名称 / 目录结构分组展示
- **元信息读取**：选中模型后自动显示架构、上下文长度、量化类型
- **一键加载**：模型路径 / mmproj 路径一键填入配置
- **删除文件**：确认后从磁盘删除，列表自动刷新
- **打开目录**：在资源管理器中定位

### 🖥 引擎管理
- **多引擎切换**：浏览已安装的 llama.cpp 引擎，选择默认引擎
- **自动发现**：自动扫描 `engines/` 目录和 NovaMax 引擎目录
- **后端识别**：自动识别 ROCm / Vulkan 后端类型
- **添加自定义目录**：手动添加包含 `llama-server.exe` 的目录

### ⚡ 服务器运行
- **一键启停**：轻松管理服务器进程
- **健康检查**：启动后自动 ping `/health` 端点，实时显示响应时间
- **状态监控**：运行中 / 连接中断自动标识
- **实时日志**：服务器输出实时监控
- **浏览器集成**：一键打开 Web UI

### 🎛 配置管理
- **命名配置**：保存多个命名配置（如 `mtp_qwen`、`draft_gemma`），下拉框快速切换
- **自动加载**：配置切换时自动恢复所有参数 + 模型仓库目录
- **JSON 持久化**：配置文件存于 `configs/` 目录，可分享、可备份
- **自定义参数**：支持 GUI 未覆盖的额外 llama-server 参数

### 📋 其他
- **系统托盘**：支持最小化到托盘后台运行
- **GGUF 元信息**：直接读取 GGUF 文件头部，展示架构、上下文等

---

## 从源码运行

```bash
git clone https://github.com/jerrydong1988/llama-cpp-GUI-zh.git
cd llama-cpp-GUI-zh
pip install ttkbootstrap pillow pystray
python llama-server_gui_new.py
```

## 自行编译 exe

```bash
pip install pyinstaller ttkbootstrap pillow pystray
python build_exe.py
```

编译后的 exe 位于 `dist/LLaMA-Server-GUI.exe`。

## 目录结构

```
LLaMA-Server-GUI/
├── llama-server_gui_new.py   # 主程序
├── build_exe.py              # 构建脚本
├── configs/                  # 命名配置（JSON）
├── models/                   # 下载的模型文件
│   └── {namespace}/{repo}/
├── engines/                  # 引擎目录（可选）
│   └── {version}/llama-server.exe
└── dist/                     # 编译输出
```

## 系统要求

- Windows 10/11（主要支持）
- Python 3.7+（从源码运行时）
- `llama-server` 可执行文件

## 与原始项目的区别

本仓库在 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 基础上做了大量二次开发：

| 功能 | 原始项目 | 本仓库 |
|------|----------|--------|
| 模型下载 | ❌ | ✅ ModelScope 下载（主模型 + 草稿模型） |
| 模型仓库 | ❌ | ✅ 多目录扫描 + 元信息 + 加载/删除 |
| 引擎管理 | ❌ | ✅ 多版本切换 + NovaMax 自动发现 |
| 命名配置 | ❌ | ✅ 下拉框快速切换 |
| 健康检查 | ❌ | ✅ 自动 ping + 响应时间 |
| GGUF 解析 | ❌ | ✅ 架构/上下文/量化展示 |
| 中文界面 | ❌ | ✅ 完整汉化 |
| 参数覆盖 | 部分 | ✅ MTP/推测解码等全部参数 |

## 许可证

MIT
