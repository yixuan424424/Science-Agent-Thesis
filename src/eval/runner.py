"""单条用例执行器。

负责：
- 调用 agent.run(task) 拿到 AgentResult，全程做异常兜底
- 调用 checker.check() 得到正确性报告
- 采集指标（耗时、轮数、工具调用次数等），打包为 RunRecord
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Protocol

from src.agent.messages import AgentResult, Step
from src.eval.cases import TestCase
from src.eval.checker import CheckReport, check


class _AgentLike(Protocol):
    """任何提供 .run(task) -> AgentResult 的对象都可以当 agent 用。"""

    def run(self, task: str) -> AgentResult: ...


@dataclass
class RunRecord:
    """单条用例 × 单个配置的运行记录。"""

    case_id: str
    config: str  # "b0" / "b1" / "ours"
    success: bool
    iterations: int
    total_tool_calls: int
    failed_tool_calls: int
    duration_seconds: float
    stopped_reason: str
    final_answer: str
    check_report: CheckReport
    error: str | None = None
    trajectory_summary: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "config": self.config,
            "success": self.success,
            "iterations": self.iterations,
            "total_tool_calls": self.total_tool_calls,
            "failed_tool_calls": self.failed_tool_calls,
            "duration_seconds": round(self.duration_seconds, 3),
            "stopped_reason": self.stopped_reason,
            "final_answer": self.final_answer,
            "check_report": self.check_report.to_dict(),
            "error": self.error,
            "trajectory_summary": self.trajectory_summary,
        }


def _summarize_trajectory(trajectory: list[Step]) -> list[str]:
    return [s.summary() for s in trajectory]


def _count_tool_calls(trajectory: list[Step]) -> tuple[int, int]:
    total = 0
    failed = 0
    for step in trajectory:
        if step.tool_name is None:
            continue
        total += 1
        obs = step.observation or {}
        if not obs.get("success"):
            failed += 1
    return total, failed


def run_case(
    case: TestCase,
    agent: _AgentLike,
    config_name: str,
    *,
    tools_available: bool = True,
) -> RunRecord:
    """跑一条用例，返回 RunRecord。

    Args:
        case: 测试用例
        agent: 任何提供 run(task) 的 agent 实例（ReActAgent / NoToolsAgent）
        config_name: 配置名称（"b0" / "b1" / "ours"），仅用于报告
        tools_available: 透传给 checker，决定 overall 的判定方式
    """
    t0 = time.perf_counter()
    error: str | None = None
    try:
        result = agent.run(case.task)
    except Exception as e:
        result = AgentResult(
            final_answer=f"(agent crashed: {e})",
            trajectory=[],
            iterations_used=0,
            stopped_reason="error",
            error=str(e),
        )
        error = f"{type(e).__name__}: {e}"
    duration = time.perf_counter() - t0

    if result.error and not error:
        error = result.error

    report = check(case, result, tools_available=tools_available)
    total_calls, failed_calls = _count_tool_calls(result.trajectory)

    return RunRecord(
        case_id=case.id,
        config=config_name,
        success=report.overall,
        iterations=result.iterations_used,
        total_tool_calls=total_calls,
        failed_tool_calls=failed_calls,
        duration_seconds=duration,
        stopped_reason=result.stopped_reason,
        final_answer=result.final_answer,
        check_report=report,
        error=error,
        trajectory_summary=_summarize_trajectory(result.trajectory),
    )
