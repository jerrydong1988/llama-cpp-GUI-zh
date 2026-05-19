## 变更

### ✨ 新增：自定义模型下载目录
- ModelScope 下载区域顶部新增「下载目录」行 + 「📂 更改」按钮
- 可自定义模型下载的保存位置，不再局限于 exe 同级目录
- 更改下载目录时自动注册到模型仓库扫描列表（自动去重，不会导致重复目录树）
- 支持配置持久化，下次启动自动恢复

### 🎯 修复：ModelScope 浏览文件不完整
- API 请求添加 `Recursive=true` 参数，递归列出子目录中所有量化版本
- 现在 `Q8_0/`、`UD-Q4_K_M/` 等子目录中的模型文件完整显示
- 下载保存时保留子目录结构

### 🔗 联动修复：草稿模型下载路径同步
- 草稿模型下载也使用自定义下载目录，与主模型下载保持路径一致

### 🧹 代码质量提升
- 添加 `__version__` 统一版本管理
- 集中 import 语句，消除方法内重复 import
- 提取 `_monitor_loop` 消除健康检查中的重复代码
- `_SPECIAL_PARAMS` 类属性替代 generate_command 中的硬编码跳过列表

## Changes

### ✨ New: Custom model download directory
- Added download directory picker with "📂 Change" button above ModelScope download area
- Download models to any location, not just alongside the executable
- Auto-registers as a repo root when changed (smart dedup prevents duplicate trees)
- Preference saved in config, restored on restart

### 🎯 Fixed: Incomplete ModelScope file listing
- Added `Recursive=true` to API query, now lists all quantization variants in subdirectories
- Files in `Q8_0/`, `UD-Q4_K_M/` etc. are fully displayed
- Download preserves subdirectory structure

### 🔗 Fixed: Draft model download path sync
- Draft model downloads now respect the custom download directory, consistent with main model downloads

### 🧹 Code quality improvements
- Centralized `__version__` variable
- Consolidated imports, removed inline imports
- Extracted `_monitor_loop` to eliminate duplicate health check code
- `_SPECIAL_PARAMS` class attribute replaces hardcoded skip list
