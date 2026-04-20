"""基线 Agent 实现。

目前只有 B0：完全不提供工具，单次调用 LLM 让其自然语言回答。
B1 直接复用 ReActAgent + MINIMAL_PROMPT，不需要单独的类。
"""

from __future__ import annotations

from src.agent.messages import AgentResult, Step
from src.llm.client import LLMClient


class NoToolsAgent:
    """B0 基线：纯 LLM 单次调用，不提供任何工具。

    设计要点：
    - 不带 system prompt（让模型靠自身常识回答），与 B1/Ours 形成清晰对照
    - 最多一次 LLM 调用即返回
    - 返回的 AgentResult 结构与 ReActAgent 完全一致，下游 checker / report 无需差异化处理
    - 由于完全没有工具，所有需要生成图表的任务在 file_pass 上必然失败，这是预期行为
    """

    def __init__(self, llm: LLMClient | None = None) -> None:
        self.llm = llm if llm is not None else LLMClient()

    def run(self, task: str) -> AgentResult:
        try:
            msg = self.llm.chat(
                messages=[{"role": "user", "content": task}],
                tools=None,
            )
        except Exception as e:
            return AgentResult(
                final_answer=f"(B0 LLM error: {e})",
                trajectory=[],
                iterations_used=0,
                stopped_reason="error",
                error=str(e),
            )

        content = (msg.content or "").strip()
        return AgentResult(
            final_answer=content or "(empty response)",
            trajectory=[
                Step(
                    iteration=1,
                    thought=content,
                    tool_name=None,
                    tool_arguments=None,
                    observation=None,
                )
            ],
            iterations_used=1,
            stopped_reason="final_answer",
        )
