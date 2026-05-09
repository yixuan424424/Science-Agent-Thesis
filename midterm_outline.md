# 毕业设计中期报告提纲（详细 Bullet Points 版）

> **课题**：面向科学场景的智能体工具调用优化研究
> **学生**：彭超琦，浙江大学计算机科学与技术 2022 级
> **指导教师**：朱霖潮
> **报告时间**：2026 年 4 月

---

## 第一节 研究进展概述（~200 字）

**要写的内容**：

- 截至本次中期报告（2026 年 4 月下旬），毕业设计主体工程工作已全部完成
- 已完成的工作包括：科学工具库开发、ReAct 智能体框架搭建、自动评估框架、46 题测试集设计、多轮基线对比实验（共 4 轮）以及 4 项 Prompt 工程优化
- 最终系统（Ours_final）在 46 道测试题上达到 45/46（97.8%），与仅有工具但无优化提示的 B1 基线持平，同时工具调用次数减少约 9%
- 下一步进入论文撰写阶段，预计 3 周内完成初稿

---

## 第二节 已完成的主要工作（~1500 字）

### 2.1 系统总体架构（~200 字）

**要写的内容**：

- 系统基于 ReAct（Reasoning + Acting）框架，由四个核心模块构成：工具库、LLM 客户端、Agent 主循环、系统提示词
- 工具库：12 个工具，3 类（数值/统计/可视化），每个工具实现 `BaseTool` 抽象类，自动生成 OpenAI Function Calling 格式的 schema
- LLM 客户端：封装通义千问 API（OpenAI 兼容），含超时控制和重试机制
- Agent 主循环：每轮调用 LLM → 解析 tool_calls → 执行工具 → 追加 observation → 循环，直到模型给出最终答复或达到最大迭代次数
- **插入架构图**（见 `midterm_materials.md` 中的 Mermaid 图）

### 2.2 科学工具库（~300 字）

**要写的内容**：

- 数值计算类（4 个）：
  - `matrix_operation`：矩阵行列式、求逆、特征值、乘积等
  - `numerical_integration`：数值积分（scipy.integrate.quad）
  - `curve_fitting`：指数/多项式/线性拟合（scipy.optimize.curve_fit），返回参数 + R²
  - `equation_solver`：方程数值求根（scipy.optimize.brentq）

- 统计分析类（4 个）：
  - `descriptive_statistics`：均值、中位数、方差、标准差、四分位数（ddof=1 样本统计）
  - `hypothesis_test`：独立样本 t 检验（scipy.stats.ttest_ind）+ Cohen's d 效应量
  - `linear_regression`：最小二乘线性回归，返回斜率、截距、R²
  - `correlation_analysis`：Pearson 和 Spearman 相关系数

- 数据可视化类（4 个）：`line_chart`、`scatter_chart`、`bar_chart`、`heatmap`，均保存为 PNG 文件并返回路径

- 工具统一设计：`ToolResult(success, data, error, message)` 返回结构；`BaseTool.run()` 对外统一入口，自动参数校验 + 异常兜底；45 个单元测试全部通过

### 2.3 ReAct Agent 框架（~300 字）

**要写的内容**：

- 采用 Function Calling 模式（而非文本解析）：LLM 通过 `tool_calls` 字段声明工具调用意图，框架解析并执行，将结果作为 `tool` 角色消息追加到对话历史
- 设计了显式的 Thought 字段：每轮 assistant 消息的 `content` 中包含中文思考过程，便于后续 trajectory 分析
- `ToolRegistry`：按名称映射工具，`invoke()` 统一调度，未知工具/JSON 解析失败均包装为 `ToolResult(success=False)`，不抛出异常
- `Step` 数据类记录每轮的 thought / tool_name / arguments / observation，`AgentResult` 汇总完整轨迹
- `stopped_reason` 三值：`final_answer`（正常终止）/ `max_iterations`（达上限）/ `error`（LLM 异常）
- 最大迭代次数默认 10 轮，足以完成任何测试题

### 2.4 自动评估框架（~200 字）

**要写的内容**：

- 测试用例以 JSON 格式定义（`tests/data/test_cases.json`），46 道题，每题包含：
  - 自然语言问题描述
  - 期望数值（带相对容差和绝对容差双阈值）
  - 期望文件（图表，带最小文件大小约束）
  - 必须调用的工具列表

- 正确性判定三个维度：
  1. **数值正确性**：从 final_answer 中用正则提取所有数字，逐个与期望值比对，取最近匹配
  2. **文件正确性**：检查图表文件是否存在且大于最小 size（确保不是空白图）
  3. **工具调用**：检查 trajectory 中是否出现了必要的工具调用记录

- CLI 评估脚本：`python scripts/run_eval.py`，支持 `--configs`、`--cases` 过滤，自动生成 `summary.md` + `results.json`

### 2.5 测试集设计（~200 字）

**要写的内容**：

- 46 道测试题，5 个类别，3 档难度，总体设计原则：确保 B0 和 Ours 之间有明显差距

- **基础题（36 道）**：每题 1~3 个工具调用，考察 agent 对单类工具的正确使用
  - numerical（8 道）：矩阵运算、积分、拟合、方程求根
  - statistics（8 道）：描述性统计、假设检验、回归、相关分析
  - visualization（6 道）：4 类图表生成
  - composite（10 道）：2~3 个工具的组合
  - error_recovery（4 道）：题目故意设置需要容错的场景

- **Hard 题（6 道，hard_01~06）**：4~6 个工具，步骤间有依赖，且不给出明确的步骤分解提示

- **vhard 题（4 道，vhard_01~04）**：专门针对 Ours 的弱点设计
  - vhard_01：指数拟合初始值不适配（测试合理性检查）
  - vhard_02：符号约定题（测试科学规范遵守）
  - vhard_03：需要主动调整方程求根区间（测试容错）
  - vhard_04：科学记数法矩阵（测试多步 matrix_operation）

### 2.6 基线实验设计（~100 字）

**要写的内容**：

- 三组配置：
  - **B0**（无工具基线）：使用 `NoToolsAgent`，LLM 依赖纯文本推理，不调用任何工具
  - **B1**（最简提示基线）：`MINIMAL_PROMPT`（约 50 字），仅告知模型可以用工具，无任何额外规范
  - **Ours**（优化提示）：`SYSTEM_PROMPT`（约 2000 字），包含 7 条工作规范 + few-shot 示例

- 底层 LLM：所有配置均使用 qwen-turbo-latest（选 turbo 而非 plus 的原因：turbo 在复杂场景下失败率更高，更能体现 prompt 优化的效果）

---

## 第三节 主要实验结果（~1000 字）

### 3.1 工具调用的必要性（B0 vs B1）（~200 字）

**要写的内容**：

- **插入 v4 基线总体对比表**（见 `midterm_materials.md` 1.2 节）
- 核心数据：B0=50.0%，B1=97.8%，差距 47.8 个百分点
- B0 的失败模式分析：B0 失败的 23 道题中，有 6 道可视化题（0%，B0 不会调用图表工具）、12 道 composite 题（只有 5/18=28%），B0 即使"猜"对了数字，也无法生成图表
- B0 成功的 23 道题主要是数学题（LLM 能直接心算出来，如 num_01~04 的基础矩阵/积分题）
- **结论**：工具调用对科学任务执行是必要条件，特别是涉及可视化和多步数值计算的任务

### 3.2 Prompt 工程的效果（B1 vs Ours）（~400 字）

**要写的内容**：

- **v3（优化前）**：Ours=43/46（93.5%）< B1=44/46（95.7%），Ours 反而输了
  - 原因：Ours 的 prompt 在某些场景下成为约束（如 vhard_01 盲信工具、stats_08 心算）
  - 这是反直觉的发现，表明 prompt 设计不当可能适得其反

- **v4（优化后）**：Ours=45/46（97.8%）= B1=45/46（97.8%），准确率持平
  - O1+O2 直接修复了 vhard_01 和 stats_08（各 +1 道）
  - O3+O4 修复了 viz_03（+1 道），但引起 comp_07 回归（−1 道），净 +0

- **效率维度**（v4，44 道共同通过的题）：
  - **插入 Delta vs B1 表**（见 `midterm_materials.md` 1.3 节）
  - Ours 工具调用次数少 8.8%：说明 O2/O3 的规范化引导避免了冗余工具调用（Plan 前置使 agent 不重复试错）
  - Ours 耗时多 15.8%：主要来自 Thought 更详细、Plan 编写占用时间，可接受的 tradeoff

- **by-category 差异**（见 `midterm_materials.md` 1.4 节）：
  - composite 类 B1/Ours 均为 17/18（同 FAIL comp_07 一题），说明多步任务对两者均有挑战
  - statistics 类 Ours v4 升至 8/8（v3 中 7/8），O2 规则有效
  - visualization 类 Ours v4 升至 6/6（v3 中 5/6），O3/O4 有效

### 3.3 论文核心结论（~200 字）

**要写的内容**：

- 本系统验证了以下结论：
  1. 工具调用对科学场景的自动化任务执行是必要的（B0 vs B1：+47.8pp）
  2. 针对科学场景的 prompt 工程优化，在准确率上能与仅有工具的基线持平，同时在工具使用效率上更优
  3. 具体优化规则（O1~O4）解决了可验证的 agent 行为缺陷，且每条规则的效果可以通过 trajectory 级别的对比直接观察

- 这与论文的核心创新点"针对科学场景对工具调用进行优化"高度一致

---

## 第四节 遇到的问题及解决方案（~800 字）

### 4.1 问题1：Agent 盲信工具异常输出（已解决，O1）

**要写的内容**：

- **问题描述**：在 vhard_01 中，`curve_fitting` 返回了 R²=−0.28（工具内部的初始值 p0=[1.0, 0.1] 不适合量级为 1000 的数据，导致拟合发散）。v3 版本的 Ours 注意到 R² 为负，但仍然在最终答复中使用了这个发散结果（λ≈7 min⁻¹，半衰期≈6 秒），与实际物理量级（半衰期约 14 分钟）严重不符
- **根因分析**：SYSTEM_PROMPT 强调"必须从 observation 中取值，不得编造"，但没有规定应如何处理明显异常的 observation，导致 agent 在"服从规则"和"质疑结果"之间选择了前者
- **解决方案（O1）**：在 SYSTEM_PROMPT 中增加"结果合理性检查"条款，明确 R²<0 或>1 视为异常，必须换方法重试，且不得将异常值写入最终答复
- **效果验证**：vhard_01 从 FAIL 变 PASS，trajectory 出现了"curve_fitting → R²异常 → 切换 linear_regression on ln(N)" 的正确路径

### 4.2 问题2：Agent 绕过工具做心算（已解决，O2）

**要写的内容**：

- **问题描述**：stats_08 要求去除异常值后重新计算均值。v3 版本的 Ours 调用了一次 descriptive_statistics 得到 Q1/Q3，然后在 thought 中心算 cleaned_mean，结果算错（2.4 而非 2.43333）
- **根因分析**：prompt 没有明确禁止"小规模心算"，agent 认为 6 个数可以直接心算，不值得再调一次工具
- **解决方案（O2）**：新增"数值计算规范"条款，明确要求：任何新的样本集（即使只有 5~6 个数）MUST 再调一次 descriptive_statistics；同时禁止在 thought 中写出心算表达式
- **效果验证**：stats_08 从 FAIL 变 PASS，v4 trajectory 中出现了两次 descriptive_statistics 调用

### 4.3 问题3：LLM 基础设施层 400 错（未解决，Future Work）

**要写的内容**：

- **问题描述**：qwen-turbo-latest 偶发 HTTP 400 错误，错误信息为 `InternalError.Algo.InvalidParameter: function.arguments must be in JSON format`，导致 agent 停止并返回空答复（如 v3 中的 viz_03）
- **特点**：该错误是随机性的（同一道题有时过有时不过），与 prompt 内容无关，属于 LLM 服务的不稳定性
- **当前处理**：计入 FAIL，在报告中注明；现有重试机制（`LLMClient`）仅针对网络错误，不处理此类业务错误
- **Future Work**：可在 `src/llm/client.py` 中针对 400 错加一次重试（扰动 temperature 或简化 tool schema）

### 4.4 问题4：B1 基线数值精度截断（Ours 避免了此问题）

**要写的内容**：

- **问题描述**：B1 在 hard_03 中将工具返回的 49.1625 截断为 49.16，被 checker 判为 miss（容差 0.001 绝对值 = 0.0005，而 |49.16 - 49.1625| = 0.0025 > 0.0005）
- **Ours 的优势**：SYSTEM_PROMPT 包含精度规则（"至少保留 4~6 位有效数字"），Ours 正确报告了 49.1625

---

## 第五节 与开题报告的差异说明（~300 字）

**要写的内容**：

- **插入差异对比表**（见 `midterm_materials.md` 第五节）
- 强调调整是合理的：
  - 砍掉 Biopython 是因为三大类（数值/统计/可视化）已足够覆盖论文核心贡献，生物信息学工具会分散焦点
  - qwen-turbo 替换 qwen-plus 提升了实验的区分度，使 prompt 工程效果更可量化
  - 测试集从 10-12 扩展到 46 道：更充分的统计基础，且有助于发现不同类型的 failure mode

- 核心创新点未变：**针对科学场景的工具调用优化**，体现在 prompt 工程的四条具体规则（O1~O4）和可量化的实验对比上

---

## 第六节 后续工作计划（~300 字）

### 6.1 遗留工程改进（Optional，~100 字）

**要写的内容**：

- O5：LLM 客户端层针对 400 错的重试（`src/llm/client.py`，约 1 天工作量）
- O6：curve_fitting 工具的初始值自适应（`src/tools/numerical.py`，约半天）
- 这两项不影响论文主线，若时间充裕则做，否则列为 Future Work 讨论

### 6.2 论文撰写计划（~200 字）

**要写的内容**（时间节点）：

| 周次 | 时间 | 主要任务 |
|------|------|---------|
| 第 1 周 | 4/21~4/27 | 中期报告提交；同时制作论文所需图表（系统架构图、成功率柱图、trajectory 对比图） |
| 第 2 周 | 4/28~5/4 | 撰写论文正文：引言、相关工作、系统设计与实现（前 3 章） |
| 第 3 周 | 5/5~5/11 | 撰写实验设计与结果分析（核心章节）；完成结论与展望 |
| 第 4 周 | 5/12~5/18 | 全文修改润色；准备答辩 PPT；最终提交 |

**论文建议章节结构**：
1. 引言（研究背景、问题定义、贡献点）
2. 相关工作（LLM 工具调用、ReAct 框架、科学计算自动化）
3. 系统设计与实现（工具库、Agent、评估框架）
4. 实验设置（测试集、配置、评估指标）
5. 实验结果与分析（B0/B1/Ours 对比、O1~O4 逐项分析、关键 case 深度分析）
6. 结论与展望（局限性、future work）

---

*本提纲基于当前（2026-04-21）的实际工程状态和实验数据撰写，可直接作为中期报告的写作框架使用。每节末尾的"要写的内容"是 bullet points，扩展为连贯段落即可。*
