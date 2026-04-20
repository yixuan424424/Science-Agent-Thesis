"""ReAct Agent 主循环。

流程：
1. 构造初始 messages = [system_prompt, user_task]
2. 循环最多 max_iterations 次：
   a. 调用 LLM，拿到一条 assistant message（可能含 content 文本 + tool_calls）
   b. 若无 tool_calls：视为最终答案，结束
   c. 若有 tool_calls：逐个执行工具，把结果作为 tool message 塞回 messages，
      并把每次调用都记录成一个 Step
3. 超过最大轮数时按 max_iterations 原因退出
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.agent.messages import AgentResult, Step
from src.agent.tool_registry import ToolRegistry
from src.llm.client import LLMClient
from src.prompts.system_prompts import SYSTEM_PROMPT
from src.tools.base import BaseTool


logger = logging.getLogger(__name__)


class ReActAgent:
    """基于 OpenAI Function Calling 的 ReAct Agent。"""

    def __init__(
        self,
        tools: list[BaseTool],
        llm: LLMClient | None = None,
        max_iterations: int = 10,
        system_prompt: str = SYSTEM_PROMPT,
        verbose: bool = False,
    ) -> None:
        self.registry = ToolRegistry(tools)
        self.llm = llm if llm is not None else LLMClient()
        self.max_iterations = max_iterations
        self.system_prompt = system_prompt
        self.verbose = verbose

    def run(self, task: str) -> AgentResult:
        """执行一个用户任务，返回包含最终答案与完整轨迹的 AgentResult。"""
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": task},
        ]
        trajectory: list[Step] = []
        schemas = self.registry.get_schemas()

        for iteration in range(1, self.max_iterations + 1):
            if self.verbose:
                logger.info("[iter %d] calling LLM", iteration)

            try:
                msg = self.llm.chat(messages=messages, tools=schemas)
            except Exception as e:
                return AgentResult(
                    final_answer=f"(agent stopped due to LLM error: {e})",
                    trajectory=trajectory,
                    iterations_used=iteration - 1,
                    stopped_reason="error",
                    error=str(e),
                )

            # 把 assistant 消息原样塞回 messages，保留 tool_calls 结构
            assistant_msg = msg.model_dump(exclude_none=True)
            # openai sdk 返回的 dict 里 content 可能是 None（被 exclude_none 过滤），
            # 但后续我们可能需要读，这里不需要再补。
            messages.append(assistant_msg)

            thought = (msg.content or "").strip()
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                # 没有工具调用 => 视为最终答案
                final_answer = thought or "(empty response)"
                trajectory.append(
                    Step(
                        iteration=iteration,
                        thought=thought,
                        tool_name=None,
                        tool_arguments=None,
                        observation=None,
                    )
                )
                if self.verbose:
                    logger.info("[iter %d] final answer produced", iteration)
                return AgentResult(
                    final_answer=final_answer,
                    trajectory=trajectory,
                    iterations_used=iteration,
                    stopped_reason="final_answer",
                )

            # 有工具调用：按顺序执行，每个调用都要回一个 tool message
            for call in tool_calls:
                tool_name = call.function.name
                raw_args = call.function.arguments or "{}"

                try:
                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                except json.JSONDecodeError:
                    parsed_args = {"_raw": raw_args}

                if self.verbose:
                    logger.info("[iter %d] invoking tool %s", iteration, tool_name)

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
                        iteration=iteration,
                        thought=thought,
                        tool_name=tool_name,
                        tool_arguments=parsed_args if isinstance(parsed_args, dict) else None,
                        observation=observation,
                    )
                )

        # 超过最大轮数
        return AgentResult(
            final_answer="(agent stopped because max_iterations was reached)",
            trajectory=trajectory,
            iterations_used=self.max_iterations,
            stopped_reason="max_iterations",
        )
