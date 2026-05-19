# llama-cpp-GUI 与最新 llama.cpp 功能差异分析

## 一、GUI 当前支持的状态

### 已经支持的参数（25个字符串参数 + 8个布尔参数）

| 分类 | 已支持的参数 |
|------|-------------|
| 模型 | `-m` 模型路径, `--lora`, `--mmproj`, `--chat-template`, `--jinja`, `-a` 别名 |
| 生成 | `-n` 令牌数, `--temp`, `--top-k`, `--top-p`, `--repeat-penalty`, `--ignore-eos` |
| 性能 | `-c` 上下文大小, `-ngl` GPU层数, `-t` 线程, `-b` 批大小, `-ub` 物理批大小 |
| 高级 | `-fa` Flash Attention, `--mlock`, `--no-mmap`, `--numa`, `--cache-type-k/v`, `--n-cpu-moe` |
| 推测解码 | `-md` 草稿模型, `-ngld`, `--draft` |
| 服务器 | `--host`, `--port`, `--api-key`, `-np` 并行, `-cb` 持续批处理, `-v` 日志 |
| 推理 | `--reasoning-format`, `--embedding`, `--no-webui` |

## 二、官方 llama.cpp 新增但 GUI 未覆盖的功能

### 🔴 高优先级（建议添加，常用且有显著价值）

| 参数 | 说明 | 理由 |
|------|------|------|
| `--seed SEED` | 随机种子 | 调试重现关键参数，几乎所有 GUI 都有 |
| `--min-p N` | min-p 采样 | 现在主流采样方式，比 top-p 更自然，默认 0.05 |
| `--presence-penalty N` | 存在惩罚 | OpenAI 兼容参数，减少话题重复 |
| `--frequency-penalty N` | 频率惩罚 | 同上，降低高频词重复 |
| `--grammar-file FNAME` | 语法文件 | 结构化输出关键功能 |
| `--hf-repo user/model:quant` | HF 自动下载 | 无需手动找模型文件，填入HF仓库名即下载 |
| `--tb, --threads-batch N` | 批处理线程 | 可单独控制提示处理时的CPU线程数 |
| `--device dev1,dev2,...` | 指定GPU设备 | 多GPU/混合设备场景必备 |
| `--reranking` | 重排序端点 | 最新 RAG 重要功能 |
| `--pooling {none,mean,cls,last,rank}` | 嵌入池化 | 嵌入模型必须配置 |
| `--sleep-idle-seconds N` | 空闲休眠 | 省显存/内存的实用功能 |
| `--timeout N` | HTTP超时 | 长任务防断连 |

### 🟡 中优先级（进阶用户有用）

| 参数 | 说明 |
|------|------|
| `--repeat-last-n N` | 重复惩罚窗口大小 |
| `--typical-p N` | 局部典型采样 |
| `--dynatemp-range N` + `--dynatemp-exp N` | 动态温度 |
| `--mirostat N` + `--mirostat-lr/ent` | Mirostat 采样（3个参数） |
| `--xtc-probability N` + `--xtc-threshold N` | XTC 采样 |
| `--dry-*`（5个参数） | DRY 采样（multiplier/base/allowed_length/penalty_last_n/sequence_breaker） |
| `--json-schema SCHEMA` | JSON Schema 约束 |
| `--grammar GRAMMAR` | 内联 BNF 语法 |
| `--slot-save-path PATH` | 插槽KV缓存持久化（多用户场景） |
| `--cache-prompt` / `--no-cache-prompt` | 提示缓存开关 |
| `--context-shift` | 无限生成时的上下文偏移 |
| `--reasoning [on/off/auto]` | 推理/思考开关 |
| `--reasoning-budget N` | 推理令牌预算 |
| `--ssl-key-file` + `--ssl-cert-file` | HTTPS 支持 |
| `--control-vector FNAME` | 控制向量 |

### 🟢 低优先级（小众或高级参数）

- `--split-mode`, `--tensor-split`, `--main-gpu`（多GPU，Strix Halo单GPU用不到）
- `--lora-scaled`, `--lora-init-without-apply`（LoRA进阶）
- `--rope-scaling`, `--rope-*`, `--yarn-*`（长上下文调优）
- `--cpu-mask`, `--cpu-range`, `--prio`（CPU亲和性）
- `--mmproj-url`, `--mmproj-offload`, `--image-min/max-tokens`（多模态进阶）
- `--models-dir`, `--models-preset`, `--models-max`（路由器模式，多个模型）
- `--tools`, `--ui-mcp-proxy`（实验性功能）
- `-kvo/--kv-offload`, `--repack`, `--direct-io`（底层优化）
- `--fit`, `--fit-target`, `--fit-ctx`（自动显存适配）
- `--pooling`（已列入高优先级）
- 日志配置相关（`--log-verbosity`, `--log-file`等）

## 三、建议的改进方案

### 第一波（核心完善）

1. **采样参数面板重构** — 当前只有4个采样参数（temp/top-k/top-p/repeat-penalty），建议扩展为完整采样面板：
   - 新增：`--seed`, `--min-p`, `--presence-penalty`, `--frequency-penalty`
   - 把`--repeat-last-n`也加上
   - 布局调整：改成两列或滚动区域

2. **模型加载增强** — 增加HuggingFace仓库自动下载支持：
   - 新增 `--hf-repo` 输入框 + `--hf-file` 可选指定文件名
   - 填入 `ggml-org/gemma-3-1b-it-GGUF:Q4_K_M` 即可自动下载

3. **嵌入与重排序专区** — 嵌入模型用户越来越多：
   - `--embedding` 已支持
   - 新增 `--pooling` 下拉框
   - 新增 `--reranking` 复选框

4. **服务器性能与可靠性**：
   - 新增 `--threads-batch` 输入框
   - 新增 `--timeout` 输入框
   - 新增 `--sleep-idle-seconds` 输入框
   - 新增 `--cache-prompt` 复选框

### 第二波（进阶功能）

5. **采样参数完整化** — 第二波补全剩余采样器：
   - `--dynatemp-range/--dynatemp-exp`
   - `--mirostat/--mirostat-lr/--mirostat-ent`
   - `--xtc-probability/--xtc-threshold`
   - `--typical-p`
   - `--dry-*`（5个参数打包成一组可折叠区域）
   - 这些建议收在一个"高级采样"可折叠框中

6. **结构化输出支持**：
   - `--grammar-file` 文件选择器（.gbnf 文件）
   - `--json-schema` 文本框

7. **SSL/HTTPS**：
   - `--ssl-key-file` + `--ssl-cert-file` 文件选择器

8. **推理控制**：
   - `--reasoning [on/off/auto]` 下拉框
   - `--reasoning-budget` 输入框
   - `--context-shift` 复选框

### 第三波（"自定义参数"已经兜底）

所有未覆盖的参数都可以通过"自定义参数管理"面板手动添加，所以即使不增加UI控件，用户也能使用任何参数。这降低了加新功能的紧迫性。

## 四、可选的界面重构建议

当前GUI使用 ttkbootstrap（tkinter），布局以 Labelframe 分组。如果要大幅扩展参数，建议：

**方案A：保持现有框架，增加参数密度**
- 采样参数改用两列网格布局
- 新增功能放在现有选项卡中（如"高级"选项卡空间充裕）
- 优点：改动最小，现有用户习惯不破坏

**方案B：增加新选项卡**
- 新建"采样"选项卡，把采样参数从"生成参数"中独立出来
- 优点：布局清晰，参数再多也不拥挤
- 缺点：结构变化较大
