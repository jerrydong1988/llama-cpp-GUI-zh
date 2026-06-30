# LLaMA 服务器管理器（中文版）

> [🇺🇸 English](README-en.md)
>
> ## 🚨 项目存档通知
>
> **此仓库不再持续维护。** 功能已移植并大幅增强至 **llama-server-manager**：
>
> [https://github.com/jerrydong1988/llama-server-manager](https://github.com/jerrydong1988/llama-server-manager)
>
> 如需继续使用本版本，可 **Fork 此仓库自行维护**。推荐直接使用新版 llama-server-manager（功能更完善、UI 升级、跨平台体验更好）。
>
> ---
>
> ⚠️ **v2.0.0 重要变更**：架构重构，提取 `gguf_reader.py` 和 `config_store.py` 独立模块；统一进程查杀与 UI 同步逻辑；主文件精简 200+ 行。编译产物 `--windowed` 模式，双击无黑框。
>
> 基于 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 深度二次开发 — 图形化管理 llama.cpp 服务器，简化llama.cpp的命令操作。感谢yossifibrahem开源了本项目，同时中文版改进工作主要贡献是Hermes Agent及背后的Deepseek v4 Flash模型，本人只提供了想法，具体实现由Hermes Agent及背后的Deepseek v4 Flash模型完成。

![CI/CD](https://github.com/jerrydong1988/llama-cpp-GUI-zh/actions/workflows/build.yml/badge.svg)

一个功能完整的图形界面程序，用于管理 `llama-server` 全生命周期：**下载模型 → 选择引擎 → 配置参数 → 启动监控**。告别复杂的命令行参数。

| 标签页 | 功能 |
|--------|------|
| 🏪 **模型仓库** | 下载模型（ModelScope）、浏览已下载模型、多目录扫描（支持 LM Studio/NovaMax） |
| 🖥 **引擎** | 管理多个 llama.cpp 引擎版本、多引擎目录持久化 |
| 📁 **模型** | 模型路径、LoRA、多模态投影器、对话模板、推理开关 |
| ⚙️ **生成参数** | 温度、Top-K/P、重复惩罚等采样参数 |
| 🚀 **性能** | 上下文大小、GPU 层数、批处理 |
| 🔬 **高级** | Flash Attention、推测解码（MTP/draft）、缓存类型、服务器可靠性 |
| 🌐 **服务器与API** | 网络配置、API 密钥、自定义参数 |
| 📊 **服务器输出** | 实时日志 | 运行状态 |

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
- **元信息读取**：选中模型后自动显示架构、上下文长度、量化类型（缓存优化，避免重复 I/O）
- **一键加载**：模型路径 / mmproj 路径一键填入配置
- **删除文件**：确认后从磁盘删除，列表自动刷新
- **打开目录**：在资源管理器中定位

### 🖥 引擎管理
- **多引擎切换**：浏览已安装的 llama.cpp 引擎，选择默认引擎
- **自动发现**：自动扫描 `engines/` 目录，支持自定义引擎目录持久化（保存后重启自动恢复）
- **后端识别**：自动识别 ROCm / Vulkan 后端类型
- **跨平台**：自动适配 Windows `llama-server.exe` 和 Linux `llama-server`

### ⚡ 服务器运行
- **一键启停**：轻松管理服务器进程
- **健康检查**：启动后自动 ping `/health` 端点，实时显示响应时间
- **状态监控**：运行中 / 连接中断自动标识
- **实时日志**：服务器输出实时监控
- **跨平台查杀**：Windows 用 tasklist/powershell，Linux 用 lsof/os.kill
- **API 访问**：一键打开 API 地址

### 🎛 配置管理
- **多实例管理**：创建、克隆、重命名、删除实例，每个实例独立保存参数
- **自动加载**：实例切换时自动恢复所有参数 + 模型仓库目录
- **JSON 持久化**：配置文件存于 `configs/` 目录，可分享、可备份
- **自定义参数**：支持 GUI 未覆盖的额外 llama-server 参数
- **线程安全**：实例状态读写加锁，防止竞态条件

### 🚀 CI/CD 自动编译
- **GitHub Actions**：推送版本标签时自动编译 Windows + Linux 双平台可执行文件
- **自动发布**：编译产物自动上传到 GitHub Releases
- **手动触发**：支持 `workflow_dispatch` 手动编译

### 📋 其他
- **系统托盘**：支持最小化到托盘后台运行
- **GGUF 元信息**：直接读取 GGUF 文件头部，展示架构、上下文等
- **跨平台兼容**：Windows / Linux / macOS（`os.startfile` / `xdg-open` / `open` 自动适配）

---

## 从源码运行

```bash
git clone https://github.com/jerrydong1988/llama-cpp-GUI-zh.git
cd llama-cpp-GUI-zh
pip install ttkbootstrap pillow
python llama-server_gui_new.py
```

> 系统托盘需要额外安装 `pystray`，非必须。

## 自行编译可执行文件

### 本地编译

```bash
pip install pyinstaller ttkbootstrap pillow
python build_exe.py              # 目录模式（启动快）
python build_exe.py --onefile    # 单文件模式（便于分发）
```

### 通过 CI/CD 自动编译

推送版本标签即可触发 GitHub Actions 自动编译：

```bash
git tag v2.0.0
git push --tags
```

编译完成后在 [Releases](https://github.com/jerrydong1988/llama-cpp-GUI-zh/releases) 页面下载即可。

## 目录结构

```
LLaMA-Server-GUI/
├── llama-server_gui_new.py   # 主程序
├── gguf_reader.py            # GGUF 二进制解析模块
├── config_store.py           # 配置原子存储模块
├── build_exe.py              # 构建脚本（支持 --onefile）
├── .github/workflows/        # GitHub Actions 自动编译配置
├── configs/                  # 命名配置（JSON）
├── models/                   # 下载的模型文件
│   └── {namespace}/{repo}/
├── engines/                  # 引擎目录（可选）
│   └── {version}/llama-server*
└── dist/                     # 编译输出
```

## 系统要求

- **Windows 10/11** / **Linux** / **macOS**（v1.9.0 起支持跨平台）
- Python 3.7+（从源码运行时）
- `llama-server` 可执行文件

## 与原始项目的区别

本仓库在 [yossifibrahem/llama-cpp-GUI](https://github.com/yossifibrahem/llama-cpp-GUI) 基础上做了大量二次开发：

| 功能 | 原始项目 | 本仓库 |
|------|----------|--------|
| 模型下载 | ❌ | ✅ ModelScope 下载（主模型 + 草稿模型） |
| 模型仓库 | ❌ | ✅ 多目录扫描 + 元信息 + 加载/删除 |
| 引擎管理 | ❌ | ✅ 多版本切换 + 多引擎目录持久化 |
| 命名配置 | ❌ | ✅ 多实例管理 + 下拉框快速切换 |
| 健康检查 | ❌ | ✅ 自动 ping + 响应时间 |
| GGUF 解析 | ❌ | ✅ 架构/上下文/量化展示（LRU 缓存优化） |
| 中文界面 | ❌ | ✅ 完整汉化 |
| 参数覆盖 | 部分 | ✅ MTP/推测解码等全部参数 |
| 上下文滑块 | 固定 128K | ✅ 自动适配模型最大上下文 |
| 高级采样 | ❌ | ✅ Mirostat / XTC / 动态温度 / Typical-P / DRY |
| SSL 支持 | ❌ | ✅ SSL 密钥/证书选择器 |
| 结构化输出 | ❌ | ✅ 语法文件 + JSON Schema |
| 推理控制 | ❌ | ✅ 推理预算 + 上下文偏移 |
| 跨平台 | ❌ | ✅ Windows/Linux/macOS 兼容 |
| CI/CD 自动编译 | ❌ | ✅ GitHub Actions + Release |
| 线程安全 | ❌ | ✅ 实例状态读写加锁 |
| 模块化 | ❌ | ✅ GGUF 解析 / 配置存储独立模块（v2.0.0） |
| 代码质量 | ❌ | ✅ 统一进程查杀 / UI 同步 / 消除 God Object |

## 许可证

MIT
