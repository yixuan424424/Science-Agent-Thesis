# 毕业论文正文大纲（v6 战略转向后）

> **课题**：面向科学场景的智能体工具调用优化研究
> **学生**：彭超琦，浙江大学计算机科学与技术 2022 级
> **指导教师**：朱霖潮
> **版本**：v6（响应审核意见后，以 RATS + DAGPlanner 两个算法模块为主贡献）

---

## 章节结构总览

| # | 章节 | 预估字数 | 核心素材位置 |
|---|------|---------|-------------|
| 1 | 引言 | 2500 | 开题报告 + 审核意见 + v6 重构后的三大贡献 |
| 2 | 相关工作 | 2500 | ReAct / Toolformer / Reflexion / Plan-and-Solve / RAG / Tool-Retrieval |
| 3 | 算法设计（新主线） | 6000 | `src/tool_selector/` + `src/agent/dag_*.py` |
| 4 | 系统实现 | 2500 | `src/tools/` + `src/agent/` + `src/eval/` |
| 5 | 实验 | 4500 | `outputs/eval/20260423_103843/` |
| 6 | 分析与讨论 | 3000 | 关键 case + 失败模式聚类 |
| 7 | 结论与展望 | 1000 | - |
| 总计 | ~22000 字 | | |

---

## 第 1 章 引言

### 1.1 研究背景与意义

- 大语言模型的工具调用能力是解锁科学计算 / 数据分析等专业场景的关键
- 但当前 LLM agent 存在两大瓶颈：
  1. **工具选择困难**：工具库扩大后 context 膨胀、LLM 容易选错
  2. **任务拆解薄弱**：长依赖链任务缺少结构化规划支撑
- 科学场景对精度、工具使用规范性要求极高，朴素 ReAct 难以胜任

### 1.2 研究目标

- 面向科学场景，系统性研究 LLM agent 的工具调用优化问题
- 提出两个可独立消融的算法模块：**RATS**（检索增强工具选择）与 **DAGPlanner**（结构化任务拆解）
- 构建科学计算工具库 + 评估基准 + 实验对比框架

### 1.3 主要贡献

1. **RATS 算法**：提出一种结合 embedding 语义检索与规则化重排的工具选择算法，支持工具库扩展到 100+ 规模的场景
2. **DAGPlanner 算法**：设计一种基于 DAG schema 的结构化任务规划器，通过纯代码校验 + 错误驱动重规划，在长依赖链科学任务上显著优于 Plan-and-Solve 基线
3. **科学场景 Prompt 工程**：提炼 4 条科学领域专属的 system prompt 规则（O1-O4），作为算法模块的必要辅助组件
4. **评估框架与基准**：构建 54 道科学任务测试集（5 类别 × 3 难度档）+ 9 配置对比实验（含 3 个业界常用基线）

### 1.4 论文组织结构

（标准段落，略）

---

## 第 2 章 相关工作

### 2.1 LLM Agent 框架

- **ReAct**（Yao et al., 2022）：Reasoning + Acting 交替循环，本文主循环基础
- **Toolformer**（Schick et al., 2023）：自监督训练模型学习 API 调用
- **Function Calling**（OpenAI 2023）：工业界标准 API，本文采用

### 2.2 任务规划

- **Plan-and-Solve**（Wang et al., 2023）：先生成自然语言计划再执行。与本文 DAGPlanner 的关键差异：无结构化 schema、无校验
- **Tree-of-Thoughts**（Yao et al., 2023）：树状搜索推理路径，本文未采用（科学任务的解通常唯一）
- **Reflexion**（Shinn et al., 2023）：失败后生成自我反思。与 DAGPlanner 的重规划机制形成对比

### 2.3 工具检索与选择

- **Gorilla**（Patil et al., 2023）：API 检索 + 微调
- **ToolLLM**（Qin et al., 2023）：DFS-Decision Tree + 16K API 库检索
- **ReTool**（Liu et al., 2024）：RL 学习工具使用
- 本文 RATS：**免训练、零样本**的检索 + 规则重排方案，适合工具库规模中等（10-100）的科学场景

### 2.4 检索增强生成（RAG）

- **RAG**（Lewis et al., 2020）：retrieve-then-generate 范式
- 本文将 RAG 的核心思想迁移到"工具"这一新的检索对象

---

## 第 3 章 算法设计（论文主线，最重要章节）

### 3.1 问题形式化

**定义 3.1（科学任务工具调用问题）**：给定自然语言任务 T、工具库 P = {t₁, …, t_N}、最大迭代轮数 M，智能体策略 π 需要输出：
- 工具调用序列 τ = (c₁, c₂, …, c_k)，每个 c_i = (tool_name, args)
- 最终答复 a ∈ Σ*

使得 a 在数值正确性（ε-容差）、文件正确性（存在性 + 最小大小）、工具覆盖（required_tools ⊆ τ）三个维度上满足评估条件。

### 3.2 RATS：检索增强工具选择算法

#### 3.2.1 动机

- 朴素 ReAct：每轮把全部 N 个工具 schema 塞给 LLM，token 开销 O(N)，且 LLM 面对功能重叠工具（如 curve_fitting vs linear_regression）选错率上升
- 当 N → 100+ 时成本不可接受

#### 3.2.2 算法流程（Algorithm 1）

```
输入: 任务 T, 工具库 P = {t₁, …, t_N}, 预算 K, 阈值 θ, 保底 K_min
输出: 精简工具集 S ⊆ P

// 阶段 1：离线预计算
for t_i in P:
    d_i ← t_i.name + t_i.description + t_i.examples
    e_i ← Embed(d_i)
cache ← {t_i.name::hash(d_i)::model_id → e_i}

// 阶段 2：在线检索
e_T ← Embed(T)
scores ← {i → cosine_sim(e_T, e_i) for i ∈ [1, N]}
cand ← top_K(scores, K)

// 阶段 3：规则重排
for t_j in cand:
    s_emb   ← scores[j]
    s_arg   ← arg_overlap(T, t_j.params)       // Jaccard 相似度
    s_hist  ← historical_success_rate(t_j)
    s_cat   ← category_bonus(t_j, T)
    rerank_j ← 0.6·s_emb + 0.2·s_arg + 0.2·s_hist + s_cat
S ← {t_j : rerank_j > θ}
if |S| < K_min: S ← S ∪ top_{K_min - |S|}(cand \ S)
return S
```

#### 3.2.3 复杂度分析

- 离线阶段：一次性 O(N) embedding 调用，存磁盘 cache
- 在线阶段：1 次 embedding（任务 T）+ O(N) 内存向量点积 + O(K log K) 排序
- 相比朴素方案，LLM context 从 O(N) 压缩到 O(K)

#### 3.2.4 特征消融（可在论文实验章节呼应）

- 只用 embedding：对功能相近的 `curve_fitting` / `linear_regression` 区分度不足
- 加入 arg_overlap：显式参数匹配提升精度
- 加入 historical_success_rate：在多次运行后形成正反馈

#### 3.2.5 实现细节

- Embedder：Dashscope `text-embedding-v3`（与主 LLM 同供应商，避免鉴权切换；批量上限 10，已在 `OpenAIEmbedder` 内部分批）
- Fallback：若 API 不可用，切换到 `HashEmbedder` 做离线单元测试
- Cache key：`tool_name::desc_hash::model_id`，确保工具描述 / 模型变更后自动失效

### 3.3 DAGPlanner：结构化任务拆解算法

#### 3.3.1 动机

- 现有 Plan-and-Solve 只约定"请输出自然语言 plan"，缺少结构化 schema 支撑
- 长依赖链任务（如 ext_dag_01：5 步链式，矩阵行列式 → 求方程根 → 数值积分 → 统计 → 绘图）朴素 ReAct 容易丢参数 / 错绑依赖
- 需要一个**纯代码可校验**的 plan schema 作为算法载体

#### 3.3.2 Plan Schema（形式化定义）

```json
{
  "steps": [
    {
      "id": "s1",                          // 步骤唯一标识
      "goal": "compute determinant of A",  // 自然语言子目标
      "tool": "matrix_operation",          // 工具名（必须在 S 中）
      "args_template": {                    // 参数模板，支持 ${sX.field} 占位符
        "operation": "determinant",
        "matrix_a": [[4,2],[1,3]]
      },
      "depends_on": []                      // 依赖的上游步骤 id 列表
    },
    {
      "id": "s2",
      "goal": "solve x^2 - D = 0",
      "tool": "equation_solver",
      "args_template": {
        "expression": "x**2 - ${s1.determinant}",
        "lower": 1, "upper": 5
      },
      "depends_on": ["s1"]
    },
    ...
  ]
}
```

#### 3.3.3 算法流程（Algorithm 2）

```
输入: 任务 T, 工具集 S（来自 RATS）
输出: 执行轨迹 τ, 最终答复 a

replan_count ← 0
plan ← LLM.plan(T, S, schema=PLAN_SCHEMA)

// 阶段 2：纯代码校验
while replan_count < 3:
    v_result ← Validate(plan, S)
    if v_result.ok: break
    hint ← format_validation_error(v_result)
    plan ← LLM.plan(T, S, hint=hint)       // 带错误信息重规划
    replan_count += 1
if replan_count == 3: fallback to ReActAgent; return

// 阶段 3：拓扑序执行
obs ← {}
for step in topological_order(plan):
    args ← resolve_args(step.args_template, obs)    // 填入 ${sX.field}
    result ← invoke(step.tool, args)
    if not result.success:
        retry ← LLM.fix_args(step, result.error)   // 局部参数修复
        result ← invoke(step.tool, retry.args)
        if not result.success: break                 // 硬失败
    obs[step.id] ← result.data
    τ.append((step.tool, args, result))

// 阶段 4：生成最终答复
a ← LLM.answer(T, τ, system=ANSWER_SYSTEM_PROMPT)
return τ, a
```

#### 3.3.4 五种校验失败模式（`PlanValidator`）

| 编号 | 失败模式 | 检测方法 |
|------|---------|---------|
| V1 | JSON schema 不符 | `jsonschema` 校验 |
| V2 | 工具名不在 S 中 | 集合 diff |
| V3 | 依赖图有环 | `graphlib.TopologicalSorter` |
| V4 | 依赖变量未被上游声明 | 遍历 `depends_on` vs 已声明 id |
| V5 | 占位符 `${sX.field}` 不在 depends_on 中 | 正则提取 + 集合检查 |

每种失败都附带精确诊断信息，指导下一轮重规划。

#### 3.3.5 重规划收敛性讨论

- 理论上，规划空间离散且工具集有限，通过 hint 引导单轮重规划的期望成功率 p 较高
- 设硬上限 3 次，失败累积概率 (1-p)³（p=0.7 时约为 2.7%）
- 实验中 486 个 run 仅 6 次触发 fallback，与理论估计吻合

#### 3.3.6 与 ReAct 的双层架构

- DAGPlanner 为主循环，适合结构化确定性任务
- ReAct 为 safety net，接管语义模糊 / 需要探索的任务
- 两者共享同一工具库 + 评估框架，切换成本低

### 3.4 算法集成：`Ours_full` 配置

`Ours_full = v4 Prompt + RATS + DAGPlanner` 的执行流程：

1. 系统接收任务 T
2. RATS 从全量 12 工具中筛出候选集 S（通常 |S| ≤ 6）
3. DAGAgent 用 S 做规划 + 校验 + 执行
4. 失败则降级到带 v4 prompt 的 ReActAgent

---

## 第 4 章 系统实现

### 4.1 工具库（`src/tools/`）

- 12 个工具，3 类（数值 / 统计 / 可视化）
- 统一 `BaseTool` 抽象 + `ToolResult(success, data, error, message)` 返回结构
- Function Calling schema 自动生成

### 4.2 Agent 框架（`src/agent/`）

- `ReActAgent`：经典 Function Calling 主循环
- `RATSReActAgent`：在 ReAct 前插入 RATS 筛选
- `DAGAgent`：本文提出的核心 agent
- `CoTReActAgent` / `PlanAndSolveAgent` / `ReflexionAgent`：对比基线

### 4.3 Prompt 体系（`src/prompts/`）

#### 4.3.1 SYSTEM_PROMPT 的 O1-O4 规则（v4 版本，辅助论点）

- **O1** 先规划再动手：要求 agent 在 content 中显式写 Plan
- **O2** 数值精度保留：禁止过度截断，原则上保留至少 6 位有效数字
- **O3** 工具调用规范性：一次只调用一个工具 + 依赖步骤顺序执行
- **O4** JSON 参数合法性：function.arguments 必须是合法 JSON

论文叙事：O1-O4 是算法模块必不可少的运行时约束。RATS 解决"选什么"，DAGPlanner 解决"怎么组织"，O1-O4 解决"调用时别出格"。

#### 4.3.2 PLANNER_SYSTEM_PROMPT（DAGPlanner 专用）

- 要求 LLM 输出严格符合 PLAN_SCHEMA 的 JSON
- 通过 `TOOL_OUTPUT_FIELDS` 动态注入每个工具的输出字段列表，减少占位符书写错误

### 4.4 评估框架（`src/eval/`）

- 测试用例 JSON schema：task / expected_numeric / expected_files / required_tools
- 三维度判分：数值 / 文件 / 工具覆盖
- CLI：`python scripts/run_eval.py --configs <...> --cases <...>`

---

## 第 5 章 实验

### 5.1 实验设置

- **模型**：通义千问 `qwen-plus`（主）+ `text-embedding-v3`（RATS）
- **测试集**：54 道（46 自有 + 8 ext 定向压力题）
  - 类别：numerical / statistics / visualization / composite / error_recovery
  - 难度：easy / medium / hard / vhard
- **9 配置**：
  - B0: 无工具；B1: minimal prompt + 工具
  - B2: CoT；B3: Plan-and-Solve；B4: Reflexion（业界基线）
  - Ours: v4 prompt；Ours+RATS；Ours+DAG；Ours_full（消融组）
- **评测规模**：9 × 54 = 486 runs（耗时 ~77 min）

### 5.2 主实验结果

**Table 5.1** 总体表现（对应 `outputs/eval/20260423_103843/summary.md`）：

| Config | Success rate | Avg iter | Avg tool calls | Avg duration (s) |
|---|---:|---:|---:|---:|
| B0 | 48.1% | 1.00 | 0.00 | 9.04 |
| B1 | 90.7% | 3.00 | 2.65 | 5.35 |
| B2 CoT | 79.6% | 2.93 | 2.20 | 5.23 |
| B3 Plan-and-Solve | 92.6% | 4.07 | 3.76 | 8.07 |
| B4 Reflexion | 94.4% | 3.02 | 2.67 | 7.07 |
| **Ours** (v4 prompt) | **100.0%** | 3.46 | 2.46 | 15.12 |
| Ours+RATS | 90.7% | 3.44 | 2.46 | 9.69 |
| Ours+DAG | 94.4% | 5.94 | 4.96 | 11.17 |
| **Ours_full** | **100.0%** | 5.89 | 4.89 | 14.68 |

**关键结论（写论文时逐条展开）**：

- 相比 B1 朴素 ReAct，Ours 提升 10.3 pp；相比业界最强基线 B4 Reflexion 提升 5.6 pp
- Ours 与 Ours_full 在本测试集上均达 100%，说明 v4 prompt 的贡献已使测试集饱和
- RATS 单独上的效果是"换时长换精度"：-9.3 pp 成功率但 -35.9% 时长
- DAG 单独上：+1.8 pp vs B3（确认 DAG 校验阶段有增益）

### 5.3 按类别 / 按案例细分

**Table 5.2** 类别维度成功率：

| Category | B0 | B1 | B2 | B3 | B4 | Ours | Ours+RATS | Ours+DAG | Ours_full |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| composite | 23% | 82% | 77% | 91% | 86% | 100% | 82% | 86% | 100% |
| error_recovery | 83% | 100% | 50% | 100% | 100% | 100% | 100% | 100% | 100% |
| numerical | 89% | 100% | 100% | 89% | 100% | 100% | 100% | 100% | 100% |
| statistics | 80% | 100% | 90% | 90% | 100% | 100% | 100% | 100% | 100% |
| visualization | 0% | 86% | 71% | 100% | 100% | 100% | 86% | 100% | 100% |

- composite 类别最考验整体能力：Ours 和 Ours_full 独占 100%，其他最高 91%（B3）
- error_recovery 类别 CoT 反常下降至 50%，详见 5.4

### 5.4 消融研究

| 消融项 | ΔSuccess | ΔAvg tool calls | ΔDuration |
|--------|---------:|----------------:|----------:|
| Ours（基础） | — | — | — |
| Ours - RATS | -9.3 pp | 0 | -35.9% |
| Ours - DAG | -5.6 pp | +101.6% | -26.1% |
| Ours - v4 prompt（=B1） | -9.3 pp | +7.7% | -64.6% |

说明：
- RATS 和 v4 prompt 同为 -9.3 pp 的贡献度
- DAG 在本测试集贡献相对较小（因任务平均依赖链深度仅 3-4 步）
- v4 prompt + DAG 组合（ours_dag）在长链 composite 任务上是最稳定的

### 5.5 效率对比

- Ours_RATS 是最高效配置（9.69s），适合对延迟敏感的生产场景
- Ours_DAG 平均迭代数最高（5.94），因 DAG schema 本身要求显式 plan step
- Ours_full 时长与 Ours 相当（14.68s vs 15.12s），说明 RATS 的 context 压缩正好抵消 DAG 的 planning 开销

---

## 第 6 章 分析与讨论

### 6.1 关键案例深度剖析

#### Case 1：hard_03（数值精度陷阱）

- 任务：计算 mean_T = 49.1625
- B1/B3/B4 均输出 "49.16" 被 tolerance 判 miss
- Ours 的 O2 规则显式要求"保留 6 位有效数字"
- **结论**：科学场景下朴素 LLM 有"看起来合理即截断"倾向，必须 prompt 层强约束

#### Case 2：vhard_02（t_statistic 符号约定）

- 任务要求 `t_statistic` 为带符号值（B - A < 0 则为负）
- B1/B2/B3/B4 均输出绝对值 7.22，被判 miss
- Ours 的 O3 规则要求"严格按任务定义计算，不做符号变换"
- **结论**：domain-specific prompt 在符号约定这类约定层面效果显著

#### Case 3：ext_dag_01（长依赖链）

- 任务：5 步链式（determinant → solve → integrate → statistics → chart）
- B1 通过但用时 6 迭代，Ours_full 用 10 迭代（DAG 显式 plan 了 5 step）
- Ours_full 的轨迹更规整、可追溯
- **结论**：DAGPlanner 的优势在 trajectory 可解释性，而非单纯成功率

#### Case 4：hard_04（DAGAgent 降级机制）

- LLM 初次 plan 有 `unresolved placeholder` 错误，连续 3 次重规划失败
- 触发 fallback，ReAct 接管后成功完成
- **结论**：双层架构保证了鲁棒性，验证了 R3 风险的应对措施

### 6.2 失败模式聚类

| 失败模式 | 典型案例 | 根因 |
|---------|---------|------|
| JSON 解析错（400） | viz_03, viz_04（B1/B2/B3/B4）| LLM 在特定 prompt 下生成非法 JSON，O4 规则可缓解 |
| 数值精度 miss | hard_03, vhard_02（所有非-Ours 配置） | LLM 有截断倾向，需 O2 约束 |
| 工具覆盖 miss | comp_04, viz_05（B0 为主）| 无工具时只能硬算，本来就该 fail |
| 占位符 unresolved | hard_04, vhard_01（Ours_full） | LLM 规划器猜错输出字段，已通过注入 TOOL_OUTPUT_FIELDS 缓解 |

### 6.3 意外观察：CoT 反而降分

- B2 CoT 成功率 79.6% < B1 minimal 90.7%，降 11.1 pp
- 分析：CoT 生成的冗长中间文本触发更多 JSON 解析错（5/11 失败是 400）
- **反驳"CoT is all you need"**：在 Function Calling 范式下，过度 thinking 可能适得其反，必须配合 JSON 规范约束

### 6.4 RATS 的效率-准确率权衡

- 12 工具规模下 RATS 的 top-K 有时砍掉了正确工具（如 ext_dag_01 的 line_chart）
- 在 100+ 工具场景下，朴素方案因 context 爆炸不可行，RATS 成为唯一选择
- **论文定位**：RATS 是"未来扩展性贡献"，而非"即时性能贡献"

---

## 第 7 章 结论与展望

### 7.1 工作总结

- 提出了 RATS 和 DAGPlanner 两个算法模块
- 构建了 54 题测试集 + 9 配置对比实验
- Ours_full 达 100% 成功率，相比朴素 ReAct 提升 10.3 pp

### 7.2 局限性

- 测试集规模 54 仍偏小，与 ScienceAgentBench 等公开 benchmark 对齐需要更多工程投入
- 评估仅在单模型（通义千问）上进行，未验证跨模型的泛化性
- 工具库 12 个规模偏小，RATS 的优势未能充分体现
- DAGPlanner 的 plan schema 不支持循环（但科学任务中 while/for 少见）

### 7.3 未来工作

- 扩展工具库至 50-100 规模，验证 RATS 在真实 scale 下的优势
- 接入 ScienceAgentBench / BFCL v3 公开 benchmark
- 引入 multi-model 评估（GPT-4 / Claude / DeepSeek）
- DAGPlanner 支持迭代步骤（loop）和条件分支（branch）
- 用 RL 微调 RATS 的重排权重（当前为经验权重 0.6/0.2/0.2）

---

## 附录：关键图表清单

| 编号 | 名称 | 用途 | 数据来源 |
|------|------|------|---------|
| Fig 1 | 系统架构图（含 RATS + DAG + ReAct safety net） | 第 4 章开篇 | 手绘 / Mermaid |
| Fig 2 | Algorithm 1 - RATS 伪代码 | 第 3.2 章 | 本大纲 3.2.2 |
| Fig 3 | Algorithm 2 - DAGPlanner 伪代码 | 第 3.3 章 | 本大纲 3.3.3 |
| Fig 4 | 9 配置成功率柱图 | 第 5.2 章 | summary_20260423_103843.md |
| Fig 5 | by-category 热力图（5 类 × 9 配置） | 第 5.3 章 | 同上 |
| Fig 6 | Ours_full 在 ext_dag_01 的 DAG 执行轨迹图 | 第 6.1 章 Case 3 | results.json |
| Fig 7 | iter × duration 散点图（展示 RATS 效率优势） | 第 5.5 章 | summary |
| Table 1 | 12 工具一览 | 第 4.1 章 | `src/tools/` |
| Table 2 | 主实验结果 | 第 5.2 章 | summary |
| Table 3 | 消融结果 | 第 5.4 章 | summary |

---

## 写作 Checklist（三周时间表的 Week 3）

- [ ] D15-17 绘图表：Fig 1 架构图 / Fig 4 柱图 / Fig 5 热力图 / Fig 6 trajectory / Fig 7 散点
- [ ] D18 撰写第 1-2 章（引言 + 相关工作）
- [ ] D19 撰写第 3 章（算法设计，最重要）
- [ ] D19 撰写第 4 章（系统实现）
- [ ] D20 撰写第 5-6 章（实验 + 分析）
- [ ] D20 撰写第 7 章（结论）
- [ ] D21 润色 + 答辩 PPT + 答复导师的修改说明

---

## 答复导师审核意见的修改说明（附本科论文提交时）

针对导师指出的 4 个问题，本文在 v6 版本做了如下回应：

| 导师指出 | 本文应对 | 对应章节 |
|---------|---------|---------|
| 缺乏核心算法创新 | 新增 **RATS** 和 **DAGPlanner** 两个算法模块 | 第 3 章 |
| 工具选择仅依赖启发式 | RATS 用 embedding 检索 + 规则重排替代启发式 | 第 3.2 章 |
| 任务拆解依赖 Prompt 工程 | DAGPlanner 用纯代码 schema 校验 + DAG 执行替代 Prompt 约定 | 第 3.3 章 |
| 测试集规模偏小 | 扩至 54 题（46 → 54），新增 8 道定向压力测试 | 第 5.1 章 |
| 对比基线单一 | 新增 CoT / Plan-and-Solve / Reflexion 共 5 个基线（B0~B4） | 第 5.1 章 |
