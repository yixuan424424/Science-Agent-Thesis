"""DAGAgent: 基于结构化 DAG 规划的 Agent 策略（论文 Algorithm 2 的入口）。

与 :class:`~src.agent.react_agent.ReActAgent` 的本质区别：

- ReActAgent：LLM 每轮边想边调，完整决策权交给模型，工具调用是在推理中逐步触发
- DAGAgent：一次性规划（Plan）→ 纯代码校验（Validate）→ 按拓扑序执行（Execute）
            → 汇总答复（Answer），LLM 仅出现在 Plan / 单步 args 修复 / Answer 三处

四阶段主循环:

1. Plan（LLM）：一次调用产出严格 JSON 计划
2. Validate（纯代码）：PlanValidator 五项检查；失败则把错误清单回灌给 LLM 重规划，
   上限 ``max_replans`` 次
3. Execute（纯代码 + 工具）：按 ``graphlib`` 拓扑序执行每个 step；占位符由 resolve_args
   解析；单步失败允许 ``max_step_fixes`` 次"仅 args 修复"
4. Answer（LLM）：把轨迹摘要丢回 LLM 产出最终答复

当上述任一阶段无法继续时，可选择回退到 :class:`ReActAgent`（``enable_fallback=True``），
以保证产线健壮性——这也方便做消融："DAGAgent 裸跑" vs "DAGAgent + ReAct 兜底"。

构造参数:

- ``tools``: 工具实例列表（会注册到内部 ToolRegistry，也供 fallback）
- ``selector``: 可选的 :class:`RATS`；提供则执行 Plan 前先筛工具
- ``llm``: LLMClient；不传则用默认实例
- ``max_replans``: 规划 + 校验的最大尝试次数（默认 3）
- ``max_step_fixes``: 单个 step 失败后 LLM 修复 args 的最大次数（默认 2）
- ``max_plan_steps``: 允许的最大步骤数（默认 8）
- ``enable_fallback``: 任一阶段不可恢复时是否回退到 ReActAgent（默认 True）
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from src.agent.dag_planner import (
    Plan,
    PlanStep,
    PlanValidator,
    parse_plan,
    resolve_args,
    topological_order,
)
from src.agent.messages import AgentResult, Step
from src.agent.react_agent import ReActAgent
from src.agent.tool_registry import ToolRegistry
from src.llm.client import LLMClient
from src.prompts.planner_prompts import (
    ANSWER_SYSTEM_PROMPT,
    PLANNER_SYSTEM_PROMPT,
    REPLAN_HINT_TEMPLATE,
)
from src.tool_selector.retriever import RATS
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


# 虚拟"工具名"：把 Planner 和 Answer 两次 LLM 调用也记录到 trajectory，
# 便于下游 checker / report 统一处理。不会进入 ToolRegistry 做真实调度。
PLANNER_STEP_TAG = "__planner__"
ANSWER_STEP_TAG = "__answer__"


# 各工具 ToolResult.data 中可用字段的白名单。Planner 可据此写出合法的
# ``${sX.field}`` 占位符，避免猜错字段名导致 resolve_args 失败、触发不必要的重规划。
# 格式: tool_name -> "field1 | field2 | ..."
TOOL_OUTPUT_FIELDS: dict[str, str] = {
    # 数值计算
    "matrix_operation": "result | shape | determinant | real | imag",
    "numerical_integration": "integral | absolute_error | expression | interval",
    "curve_fitting": "model | params | r_squared | formula",
    "equation_solver": "root | residual | expression | interval",
    # 统计
    "descriptive_statistics": "count | mean | median | std | variance | min | max | range | q1 | q3 | iqr",
    "hypothesis_test": "test_type | t_statistic | p_value | alpha | reject_null",
    "linear_regression": "slope | intercept | r_squared | p_value | std_err | formula",
    "correlation_analysis": "method | correlation | p_value | strength | direction",
    # 可视化
    "line_chart": "file_path | width_pixels | height_pixels",
    "scatter_chart": "file_path | width_pixels | height_pixels",
    "bar_chart": "file_path | width_pixels | height_pixels",
    "heatmap": "file_path | width_pixels | height_pixels",
}


class DAGAgent:
    """基于 DAGPlanner 的 Agent 策略实现。"""

    def __init__(
        self,
        tools: list[BaseTool],
        selector: RATS | None = None,
        llm: LLMClient | None = None,
        max_replans: int = 3,
        max_step_fixes: int = 2,
        max_plan_steps: int = 8,
        enable_fallback: bool = True,
        verbose: bool = False,
    ) -> None:
        if not tools:
            raise ValueError("DAGAgent requires at least one tool.")
        self.registry = ToolRegistry(tools)
        self.selector: RATS | None = selector
        self.llm: LLMClient = llm if llm is not None else LLMClient()
        self.max_replans = max_replans
        self.max_step_fixes = max_step_fixes
        self.max_plan_steps = max_plan_steps
        self.enable_fallback = enable_fallback
        self.verbose = verbose
        self._all_tools: list[BaseTool] = tools

    # ------------------------------------------------------------------ run

    def run(self, task: str) -> AgentResult:
        trajectory: list[Step] = []
        iter_ctr = _Counter()

        # ----- 阶段 0: 工具筛选 -----
        if self.selector is not None:
            selected_tools = self.selector.select(task)
        else:
            selected_tools = self._all_tools
        selected_names: set[str] = {t.name for t in selected_tools}
        tool_lookup: dict[str, BaseTool] = {t.name: t for t in selected_tools}
        validator = PlanValidator(
            allowed_tools=selected_names,
            max_steps=self.max_plan_steps,
        )

        if self.verbose:
            logger.info(
                "[dag] selected %d tools: %s", len(selected_names), sorted(selected_names)
            )

        # ----- 阶段 1 + 2: Plan + Validate（最多 max_replans + 1 次）-----
        plan: Plan | None = None
        prior_errors: list[str] = []
        for attempt in range(self.max_replans + 1):
            it = iter_ctr.bump()
            try:
                raw = self._call_planner(task, selected_tools, prior_errors)
            except Exception as e:
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=f"Planner LLM error: {e}",
                        tool_name=PLANNER_STEP_TAG,
                        tool_arguments=None,
                        observation={"success": False, "error": str(e)},
                    )
                )
                if self.enable_fallback:
                    return self._fallback(
                        task, trajectory, it, reason=f"planner error: {e}"
                    )
                return AgentResult(
                    final_answer=f"(DAGAgent stopped due to planner error: {e})",
                    trajectory=trajectory,
                    iterations_used=it,
                    stopped_reason="error",
                    error=str(e),
                )

            try:
                candidate_plan = parse_plan(raw)
            except Exception as e:
                prior_errors = [f"Plan JSON parse error: {e}"]
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=(raw if isinstance(raw, str) else "")[:200],
                        tool_name=PLANNER_STEP_TAG,
                        tool_arguments=None,
                        observation={"success": False, "error": str(e)},
                    )
                )
                continue

            validation = validator.validate(candidate_plan)
            trajectory.append(
                Step(
                    iteration=it,
                    thought=f"Planner proposed {len(candidate_plan.steps)} steps (attempt {attempt + 1}).",
                    tool_name=PLANNER_STEP_TAG,
                    tool_arguments={"steps": len(candidate_plan.steps)},
                    observation={
                        "success": validation.ok,
                        "data": candidate_plan.to_dict() if validation.ok else None,
                        "error": None if validation.ok else "; ".join(validation.errors),
                        "message": "plan validated" if validation.ok else "plan invalid",
                    },
                )
            )
            if validation.ok:
                plan = candidate_plan
                break
            prior_errors = validation.errors

        if plan is None:
            if self.enable_fallback:
                return self._fallback(
                    task,
                    trajectory,
                    iter_ctr.value,
                    reason=f"planning failed after {self.max_replans + 1} attempts",
                )
            return AgentResult(
                final_answer=(
                    f"(DAGAgent stopped: planning failed after "
                    f"{self.max_replans + 1} attempts)"
                ),
                trajectory=trajectory,
                iterations_used=iter_ctr.value,
                stopped_reason="max_iterations",
            )

        # ----- 阶段 3: 执行 -----
        observations: dict[str, dict[str, Any]] = {}
        try:
            exec_order = topological_order(plan)
        except Exception as e:
            # 极少数情况下 Validator 通过但排序失败，兜底 fallback
            if self.enable_fallback:
                return self._fallback(
                    task,
                    trajectory,
                    iter_ctr.value,
                    reason=f"topological_order failed: {e}",
                )
            return AgentResult(
                final_answer=f"(DAGAgent stopped: topo order error {e})",
                trajectory=trajectory,
                iterations_used=iter_ctr.value,
                stopped_reason="error",
                error=str(e),
            )

        for sid in exec_order:
            step = plan.step_by_id(sid)
            if step is None:
                continue

            it = iter_ctr.bump()
            # 解析 args_template 里的占位符
            resolved, unresolved = resolve_args(step.args_template, observations)
            if unresolved:
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=f"Step {sid} placeholder unresolved: {unresolved}",
                        tool_name=step.tool,
                        tool_arguments=step.args_template,
                        observation={
                            "success": False,
                            "error": "unresolved placeholders: " + "; ".join(unresolved),
                        },
                    )
                )
                if self.enable_fallback:
                    return self._fallback(
                        task,
                        trajectory,
                        it,
                        reason=f"step {sid} unresolved placeholders",
                    )
                return AgentResult(
                    final_answer=f"(DAGAgent stopped: unresolved placeholders in {sid})",
                    trajectory=trajectory,
                    iterations_used=it,
                    stopped_reason="error",
                )

            call_args: dict[str, Any] = resolved if isinstance(resolved, dict) else {}
            tool = tool_lookup.get(step.tool)
            if tool is None:
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=f"Tool {step.tool} not available (likely filtered out by RATS).",
                        tool_name=step.tool,
                        tool_arguments=call_args,
                        observation={
                            "success": False,
                            "error": f"tool not available: {step.tool}",
                        },
                    )
                )
                if self.enable_fallback:
                    return self._fallback(
                        task, trajectory, it, reason=f"missing tool {step.tool}"
                    )
                return AgentResult(
                    final_answer=f"(DAGAgent stopped: tool {step.tool} not available)",
                    trajectory=trajectory,
                    iterations_used=it,
                    stopped_reason="error",
                )

            # 尝试调用；失败则让 LLM 修复 args，最多 max_step_fixes 次
            result = None
            current_args = call_args
            fix_it = it
            for fix_attempt in range(self.max_step_fixes + 1):
                if self.verbose:
                    logger.info(
                        "[dag] exec step %s (attempt %d) tool=%s",
                        sid, fix_attempt + 1, step.tool,
                    )
                result = tool.run(**current_args)
                trajectory.append(
                    Step(
                        iteration=fix_it,
                        thought=step.goal,
                        tool_name=step.tool,
                        tool_arguments=current_args,
                        observation=result.to_dict(),
                    )
                )
                if result.success:
                    break
                if fix_attempt >= self.max_step_fixes:
                    break
                # 让 LLM 修 args
                try:
                    current_args = self._fix_args(task, step, current_args, result.to_dict())
                    fix_it = iter_ctr.bump()
                except Exception as e:
                    logger.warning("fix_args failed for step %s: %s", sid, e)
                    break

            if result is None or not result.success:
                if self.enable_fallback:
                    return self._fallback(
                        task,
                        trajectory,
                        iter_ctr.value,
                        reason=f"step {sid} ({step.tool}) failed after fixes",
                    )
                return AgentResult(
                    final_answer=f"(DAGAgent stopped: step {sid} failed)",
                    trajectory=trajectory,
                    iterations_used=iter_ctr.value,
                    stopped_reason="error",
                )
            observations[sid] = result.to_dict()

        # ----- 阶段 4: 最终答复 -----
        it = iter_ctr.bump()
        try:
            final_answer = self._call_answer(task, plan, observations)
        except Exception as e:
            return AgentResult(
                final_answer=(
                    f"(DAGAgent finalize error: {e}. "
                    f"Executed {len(observations)}/{len(plan.steps)} steps successfully.)"
                ),
                trajectory=trajectory,
                iterations_used=it,
                stopped_reason="error",
                error=str(e),
            )

        trajectory.append(
            Step(
                iteration=it,
                thought=final_answer,
                tool_name=None,
                tool_arguments=None,
                observation=None,
            )
        )
        return AgentResult(
            final_answer=final_answer,
            trajectory=trajectory,
            iterations_used=it,
            stopped_reason="final_answer",
        )

    # --------------------------------------------------------- LLM helpers

    def _call_planner(
        self,
        task: str,
        tools: list[BaseTool],
        prior_errors: list[str],
    ) -> str:
        """发起一次 Plan LLM 调用，返回 LLM 的 content 原文（期望是 JSON 字符串）。"""
        specs: list[str] = []
        for t in tools:
            schema = t.to_openai_schema()["function"]
            params = schema.get("parameters", {}).get("properties", {})
            params_desc: list[str] = []
            for pname, pinfo in params.items():
                pt = pinfo.get("type", "")
                params_desc.append(f"{pname}:{pt}")
            params_hint = ", ".join(params_desc) if params_desc else "(no params)"
            output_hint = TOOL_OUTPUT_FIELDS.get(schema["name"], "(unknown)")
            specs.append(
                f"- {schema['name']}: {schema.get('description', '').strip()}\n"
                f"    inputs : {params_hint}\n"
                f"    outputs: data.{{ {output_hint} }}"
            )
        tool_specs_text = "\n".join(specs)
        # 用字符串 replace 而非 .format，避免 JSON 示例里的花括号被当作占位符
        system_prompt = PLANNER_SYSTEM_PROMPT.replace("{tool_specs}", tool_specs_text)

        messages: list[dict[str, Any]] = [
            {"role": "system", "content": system_prompt},
        ]
        if prior_errors:
            hint = REPLAN_HINT_TEMPLATE.format(
                errors="\n".join(f"- {e}" for e in prior_errors),
                task=task,
            )
            messages.append({"role": "user", "content": hint})
        else:
            messages.append({"role": "user", "content": task})

        msg = self.llm.chat(messages=messages, tools=None, temperature=0.1)
        return (msg.content or "").strip()

    def _fix_args(
        self,
        task: str,
        step: PlanStep,
        args: dict[str, Any],
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        """让 LLM 对单步参数做一次修复。只修参数，不碰 DAG 结构。"""
        tool = self.registry.get(step.tool)
        schema_str = (
            json.dumps(tool.to_openai_schema(), ensure_ascii=False) if tool else "{}"
        )
        system = (
            "你是工具调用参数修复器。上一次调用失败，请仅针对该步骤重新输出参数 JSON 对象，"
            "不得输出任何解释文字、不得用 markdown 包裹。只输出一个 JSON 对象。"
        )
        user = (
            f"任务: {task}\n"
            f"当前步骤目标: {step.goal}\n"
            f"工具: {step.tool}\n"
            f"工具 schema: {schema_str}\n"
            f"上次参数: {json.dumps(args, ensure_ascii=False)}\n"
            f"失败信息: {observation.get('error')} | {observation.get('message')}\n"
            f"请只输出新的参数 JSON 对象。"
        )
        msg = self.llm.chat(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            tools=None,
            temperature=0.1,
        )
        raw = (msg.content or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```\s*$", "", raw)
        try:
            new_args = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"fix_args: invalid JSON: {e}")
        if not isinstance(new_args, dict):
            raise RuntimeError("fix_args: LLM did not return a JSON object.")
        return new_args

    def _call_answer(
        self,
        task: str,
        plan: Plan,
        observations: dict[str, dict[str, Any]],
    ) -> str:
        """把执行轨迹交给 Answer LLM，产出自然语言最终答复。"""
        summary_lines: list[str] = []
        for s in plan.steps:
            obs = observations.get(s.id, {})
            data_str = json.dumps(obs.get("data"), ensure_ascii=False)
            if len(data_str) > 800:
                data_str = data_str[:800] + "…(truncated)"
            summary_lines.append(
                f"{s.id} [{s.tool}] goal={s.goal}; "
                f"success={obs.get('success')}; "
                f"data={data_str}"
            )
        trajectory_text = "\n".join(summary_lines) or "(no steps)"

        user_content = (
            f"用户原任务:\n{task}\n\n"
            f"已执行的工具轨迹（按拓扑序）:\n{trajectory_text}\n\n"
            "请据此写出最终答复（遵守系统提示中的精度与图表说明规则）。"
        )
        msg = self.llm.chat(
            messages=[
                {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            tools=None,
            temperature=0.2,
        )
        return (msg.content or "").strip() or "(empty final answer)"

    # --------------------------------------------------------- fallback

    def _fallback(
        self,
        task: str,
        trajectory: list[Step],
        iter_used: int,
        reason: str,
    ) -> AgentResult:
        """规划/执行无法继续时回退到 ReActAgent。"""
        logger.warning("DAGAgent falling back to ReActAgent: %s", reason)
        react = ReActAgent(
            tools=self._all_tools,
            llm=self.llm,
            max_iterations=10,
            verbose=self.verbose,
        )
        fb_result = react.run(task)
        combined = list(trajectory) + [
            Step(
                iteration=iter_used + s.iteration,
                thought=s.thought,
                tool_name=s.tool_name,
                tool_arguments=s.tool_arguments,
                observation=s.observation,
            )
            for s in fb_result.trajectory
        ]
        return AgentResult(
            final_answer=fb_result.final_answer,
            trajectory=combined,
            iterations_used=iter_used + fb_result.iterations_used,
            stopped_reason=fb_result.stopped_reason,
            error=(
                f"dag_fallback: {reason}" if fb_result.stopped_reason == "error" else None
            ),
        )


class _Counter:
    """让内部方法共享一个递增的 iteration 计数。"""

    def __init__(self) -> None:
        self.value: int = 0

    def bump(self) -> int:
        self.value += 1
        return self.value


__all__: list[str] = ["DAGAgent"]
