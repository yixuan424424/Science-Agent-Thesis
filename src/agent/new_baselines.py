"""业界常用的 3 个基线 Agent 策略（对照 DAGAgent 使用）。

- :class:`CoTReActAgent` — B2: Chain-of-Thought + 工具。
  与 B1 的唯一差异：MINIMAL_PROMPT 后追加"think step by step"提示。

- :class:`PlanAndSolveAgent` — B3: Plan-and-Solve (Wang et al., 2023) 两阶段变体。
  Stage 1 让 LLM 写自然语言计划；Stage 2 在"计划作为上下文"前提下走 ReAct。
  关键对比点：**没有 JSON 结构化校验**、不做占位符解析、不做错误驱动重规划。
  跑完全量后，Ours_DAG 与 B3 的差异即可量化"算法级校验"的价值。

- :class:`ReflexionAgent` — B4: Reflexion (Shinn et al., 2023) 的单-trial 变体。
  在一次 run 内，每当某轮有任一工具调用失败时，下一轮 LLM 调用前追加一条由 LLM
  产出的"反思"消息（user 角色），让模型在下一步修正思路。
  与 DAGAgent 错误恢复的对比：反思 vs 结构化 args 修复 + 重规划。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.messages import AgentResult, Step
from src.agent.react_agent import ReActAgent
from src.agent.tool_registry import ToolRegistry
from src.llm.client import LLMClient
from src.prompts.system_prompts import MINIMAL_PROMPT
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


# ==========================================================================
# B2 — Chain-of-Thought
# ==========================================================================

COT_SUFFIX = """

【思维链】在调用任何工具之前，先用简短一段文字"分步思考"：
- 先把任务拆成若干子目标
- 每个子目标对应哪个工具、需要什么参数
- 预期的中间结果是什么
然后再执行。"""

COT_SYSTEM_PROMPT = MINIMAL_PROMPT + COT_SUFFIX


class CoTReActAgent(ReActAgent):
    """B2 基线：ReAct + Chain-of-Thought 系统提示。"""

    def __init__(
        self,
        tools: list[BaseTool],
        llm: LLMClient | None = None,
        max_iterations: int = 10,
        verbose: bool = False,
    ) -> None:
        super().__init__(
            tools=tools,
            llm=llm,
            max_iterations=max_iterations,
            system_prompt=COT_SYSTEM_PROMPT,
            verbose=verbose,
        )


# ==========================================================================
# B3 — Plan-and-Solve
# ==========================================================================

PLAN_AND_SOLVE_PLANNER_PROMPT = """你是一个任务规划器。给定用户任务，用自然语言写出\
一份简短的分步计划（1~5 步），每步说明：
- 这一步要做什么
- 可能用到哪个工具
只写计划本身（不超过 200 字），不要 JSON、不要代码块包裹、不要直接解题。
"""

PLAN_AND_SOLVE_EXEC_PROMPT_TEMPLATE = """你是一名面向科学场景的智能助理，可以调用工具\
完成任务。下面是你之前制定的自然语言计划（仅供参考，可随时根据实际情况调整）。

【参考计划】
{plan}

按计划执行任务，必要时调用工具，最后给出最终答复。
"""


class PlanAndSolveAgent:
    """B3 基线：Plan-and-Solve 两阶段 Agent。"""

    def __init__(
        self,
        tools: list[BaseTool],
        llm: LLMClient | None = None,
        max_iterations: int = 10,
        verbose: bool = False,
    ) -> None:
        if not tools:
            raise ValueError("PlanAndSolveAgent requires at least one tool.")
        self._tools = tools
        self.llm: LLMClient = llm if llm is not None else LLMClient()
        self.max_iterations = max_iterations
        self.verbose = verbose

    def run(self, task: str) -> AgentResult:
        # Stage 1: 自然语言计划
        try:
            plan_msg = self.llm.chat(
                messages=[
                    {"role": "system", "content": PLAN_AND_SOLVE_PLANNER_PROMPT},
                    {"role": "user", "content": task},
                ],
                tools=None,
                temperature=0.2,
            )
        except Exception as e:
            return AgentResult(
                final_answer=f"(Plan-and-Solve planner error: {e})",
                trajectory=[],
                iterations_used=0,
                stopped_reason="error",
                error=str(e),
            )
        plan_text = (plan_msg.content or "").strip() or "(empty plan)"
        if self.verbose:
            logger.info("[P&S] plan: %s", plan_text[:120])

        # Stage 2: 在"计划作为 system context"下跑 ReAct
        exec_prompt = PLAN_AND_SOLVE_EXEC_PROMPT_TEMPLATE.format(plan=plan_text)
        inner = ReActAgent(
            tools=self._tools,
            llm=self.llm,
            max_iterations=self.max_iterations,
            system_prompt=exec_prompt,
            verbose=self.verbose,
        )
        inner_result = inner.run(task)

        plan_step = Step(
            iteration=0,
            thought=f"PLAN: {plan_text}",
            tool_name="__plan__",
            tool_arguments=None,
            observation={
                "success": True,
                "data": {"plan": plan_text},
                "message": "plan produced",
            },
        )
        combined = [plan_step] + list(inner_result.trajectory)
        return AgentResult(
            final_answer=inner_result.final_answer,
            trajectory=combined,
            iterations_used=inner_result.iterations_used + 1,
            stopped_reason=inner_result.stopped_reason,
            error=inner_result.error,
        )


# ==========================================================================
# B4 — Reflexion (single-trial variant)
# ==========================================================================

REFLEXION_SYSTEM_PROMPT = """你是一名面向科学场景的智能助理，可以调用工具完成任务。

【失败反思规则】若上一轮任一工具调用失败或返回异常数据，下一轮你会收到一条
"【Reflection】" 开头的用户消息，对失败做简短诊断。收到反思后**必须**根据反思调整\
本轮思路，不要简单重复上一轮操作。

完成任务后，以最终自然语言答复收尾。
"""

_REFLECTION_SYSTEM = (
    "请对以下工具调用失败写一句中文反思（不超过 50 字）："
    "包含（1）失败原因，（2）下一步应该怎样调整。只输出反思句本身。"
)


class ReflexionAgent:
    """B4 基线：ReAct + 基于反思的错误恢复（single trial）。"""

    def __init__(
        self,
        tools: list[BaseTool],
        llm: LLMClient | None = None,
        max_iterations: int = 10,
        verbose: bool = False,
    ) -> None:
        if not tools:
            raise ValueError("ReflexionAgent requires at least one tool.")
        self.registry = ToolRegistry(tools)
        self.llm: LLMClient = llm if llm is not None else LLMClient()
        self.max_iterations = max_iterations
        self.verbose = verbose

    def run(self, task: str) -> AgentResult:
        schemas = self.registry.get_schemas()
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": REFLEXION_SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]
        trajectory: list[Step] = []
        last_failure: dict[str, Any] | None = None

        for it in range(1, self.max_iterations + 1):
            # 若上一轮失败，先追加反思
            if last_failure is not None:
                reflection_text = self._generate_reflection(last_failure)
                messages.append(
                    {"role": "user", "content": f"【Reflection】{reflection_text}"}
                )
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=f"REFLECTION: {reflection_text}",
                        tool_name="__reflection__",
                        tool_arguments=None,
                        observation={
                            "success": True,
                            "data": {"reflection": reflection_text},
                            "message": "reflection appended",
                        },
                    )
                )
                last_failure = None

            try:
                msg = self.llm.chat(messages=messages, tools=schemas)
            except Exception as e:
                return AgentResult(
                    final_answer=f"(Reflexion stopped due to LLM error: {e})",
                    trajectory=trajectory,
                    iterations_used=it - 1,
                    stopped_reason="error",
                    error=str(e),
                )

            assistant = msg.model_dump(exclude_none=True)
            messages.append(assistant)
            thought = (msg.content or "").strip()
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=thought,
                        tool_name=None,
                        tool_arguments=None,
                        observation=None,
                    )
                )
                return AgentResult(
                    final_answer=thought or "(empty response)",
                    trajectory=trajectory,
                    iterations_used=it,
                    stopped_reason="final_answer",
                )

            for call in tool_calls:
                tool_name = call.function.name
                raw_args = call.function.arguments or "{}"
                try:
                    parsed_args = (
                        json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                    )
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}

                result = self.registry.invoke(tool_name, raw_args)
                observation = result.to_dict()

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call.id,
                        "content": json.dumps(observation, ensure_ascii=False),
                    }
                )
                trajectory.append(
                    Step(
                        iteration=it,
                        thought=thought,
                        tool_name=tool_name,
                        tool_arguments=parsed_args if isinstance(parsed_args, dict) else None,
                        observation=observation,
                    )
                )
                if not observation.get("success"):
                    last_failure = {
                        "tool": tool_name,
                        "arguments": parsed_args,
                        "error": observation.get("error"),
                        "message": observation.get("message"),
                    }

        return AgentResult(
            final_answer="(Reflexion stopped because max_iterations was reached)",
            trajectory=trajectory,
            iterations_used=self.max_iterations,
            stopped_reason="max_iterations",
        )

    def _generate_reflection(self, failure: dict[str, Any]) -> str:
        """对失败信息做一次轻量 LLM 反思调用，返回一句诊断。"""
        try:
            msg = self.llm.chat(
                messages=[
                    {"role": "system", "content": _REFLECTION_SYSTEM},
                    {"role": "user", "content": json.dumps(failure, ensure_ascii=False)},
                ],
                tools=None,
                temperature=0.2,
            )
            text = (msg.content or "").strip()
            return text or "(empty reflection)"
        except Exception as e:
            return f"(reflection generation failed: {e})"


__all__: list[str] = [
    "CoTReActAgent",
    "PlanAndSolveAgent",
    "ReflexionAgent",
    "COT_SYSTEM_PROMPT",
]
