"""Agent 执行轨迹相关的数据类。

每一轮 LLM 调用（可能伴随若干 tool_calls）会记录成若干个 Step。
整个任务结束后打包成 AgentResult 返回给调用方。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Step:
    """ReAct 轨迹中的一步。

    - 若本步是"最终答案"，tool_name / tool_arguments / observation 均为 None
    - 若本步是"工具调用"，thought 为本轮模型的中文思考文本（可能为空），
      observation 为工具执行结果的 dict（即 ToolResult.to_dict()）
    """

    iteration: int
    thought: str
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None
    observation: dict[str, Any] | None = None

    def summary(self) -> str:
        """返回一行简短的人类可读描述（英文，供 demo 打印）。"""
        if self.tool_name is None:
            head = self.thought.strip().splitlines()[0] if self.thought else ""
            if len(head) > 80:
                head = head[:77] + "..."
            return f"[iter {self.iteration}] final answer: {head}"

        obs = self.observation or {}
        if obs.get("success"):
            tail = "ok"
        else:
            tail = f"error: {obs.get('error', 'unknown')}"
        return f"[iter {self.iteration}] call {self.tool_name} -> {tail}"


@dataclass
class AgentResult:
    """Agent 任务完成后的最终返回。

    Attributes:
        final_answer: 模型给出的最终自然语言回答
        trajectory: 所有执行步骤的时间顺序列表
        iterations_used: 实际使用了几轮 LLM 调用
        stopped_reason: "final_answer" / "max_iterations" / "error"
        error: 当 stopped_reason == "error" 时的错误信息
    """

    final_answer: str
    trajectory: list[Step] = field(default_factory=list)
    iterations_used: int = 0
    stopped_reason: str = "final_answer"
    error: str | None = None
