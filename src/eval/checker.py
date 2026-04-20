"""测试用例正确性判定。

对一次 Agent 执行结果（AgentResult）按预先定义的期望（TestCase）做三项检查：

1. numeric_pass：从 final_answer 抽取所有数字，对每个 ExpectedNumeric 都能匹配
2. file_pass：trajectory 里对应工具确实生成了文件，且文件存在 + 尺寸达标
3. tool_call_pass：required_tools 里的每个工具都被成功调用至少一次

overall：
- 当配置带工具时（B1/Ours），三项皆过才算 pass
- 当配置不带工具时（B0），仅看 numeric_pass（因为不可能生成文件、无 tool 调用）
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from src.agent.messages import AgentResult, Step
from src.eval.cases import ExpectedFile, ExpectedNumeric, TestCase


# 匹配普通浮点 / 整数 / 科学计数法。例如：
#   3, 3.14, -2.5, 1e-3, 1.2E+10, +0.5
# 不处理 LaTeX 风格的 "1.2 \times 10^{-5}"，会被拆成 1.2/10/5 三个数字。
_NUMBER_RE = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


@dataclass
class NumericMatchDetail:
    expected: ExpectedNumeric
    matched: bool
    matched_value: float | None = None  # 命中的实际数字（首个）


@dataclass
class FileMatchDetail:
    expected: ExpectedFile
    matched: bool
    file_path: str | None = None
    actual_size: int | None = None
    reason: str | None = None  # 失败原因（无产物 / 文件不存在 / 太小）


@dataclass
class ToolMatchDetail:
    tool_name: str
    matched: bool  # 是否被成功调用过


@dataclass
class CheckReport:
    """单条用例的检查报告。"""

    case_id: str
    numeric_pass: bool
    file_pass: bool
    tool_call_pass: bool
    overall: bool

    numeric_details: list[NumericMatchDetail] = field(default_factory=list)
    file_details: list[FileMatchDetail] = field(default_factory=list)
    tool_details: list[ToolMatchDetail] = field(default_factory=list)

    def short_diagnostic(self) -> str:
        """一行简短诊断（英文，便于在 markdown 表格里显示）。"""
        if self.overall:
            return "pass"
        reasons = []
        if not self.numeric_pass:
            missed = [d.expected.name for d in self.numeric_details if not d.matched]
            if missed:
                reasons.append(f"numeric miss: {','.join(missed)}")
        if not self.file_pass:
            missed = [d.expected.tool_name for d in self.file_details if not d.matched]
            if missed:
                reasons.append(f"file miss: {','.join(missed)}")
        if not self.tool_call_pass:
            missed = [d.tool_name for d in self.tool_details if not d.matched]
            if missed:
                reasons.append(f"tool miss: {','.join(missed)}")
        return "; ".join(reasons) if reasons else "fail"

    def to_dict(self) -> dict[str, Any]:
        return {
            "case_id": self.case_id,
            "numeric_pass": self.numeric_pass,
            "file_pass": self.file_pass,
            "tool_call_pass": self.tool_call_pass,
            "overall": self.overall,
            "numeric_details": [
                {
                    "name": d.expected.name,
                    "expected_value": d.expected.value,
                    "tolerance": d.expected.tolerance,
                    "matched": d.matched,
                    "matched_value": d.matched_value,
                }
                for d in self.numeric_details
            ],
            "file_details": [
                {
                    "tool_name": d.expected.tool_name,
                    "min_size_bytes": d.expected.min_size_bytes,
                    "matched": d.matched,
                    "file_path": d.file_path,
                    "actual_size": d.actual_size,
                    "reason": d.reason,
                }
                for d in self.file_details
            ],
            "tool_details": [
                {"tool_name": d.tool_name, "matched": d.matched} for d in self.tool_details
            ],
        }


def extract_numbers(text: str) -> list[float]:
    """从任意文本中抽取所有数字，返回 float 列表。"""
    if not text:
        return []
    out: list[float] = []
    for m in _NUMBER_RE.finditer(text):
        token = m.group(0)
        try:
            out.append(float(token))
        except ValueError:
            continue
    return out


def _is_match(expected: ExpectedNumeric, value: float) -> bool:
    """判定提取的数值是否与期望匹配。

    使用 max(0.01 绝对误差, |expected| * tolerance) 双阈值，
    避免接近 0 时相对误差过苛、绝对值很大时绝对误差过松。
    """
    threshold = max(0.01, abs(expected.value) * expected.tolerance)
    return abs(value - expected.value) <= threshold


def _check_numeric(
    expected_list: list[ExpectedNumeric], final_answer: str
) -> tuple[bool, list[NumericMatchDetail]]:
    numbers = extract_numbers(final_answer)
    details: list[NumericMatchDetail] = []
    all_matched = True
    for expected in expected_list:
        hit_value: float | None = None
        for v in numbers:
            if _is_match(expected, v):
                hit_value = v
                break
        details.append(
            NumericMatchDetail(expected=expected, matched=hit_value is not None, matched_value=hit_value)
        )
        if hit_value is None:
            all_matched = False
    return all_matched, details


def _iter_file_paths_from_step(step: Step) -> list[str]:
    """从一个轨迹步骤中提取可能的图表文件路径。"""
    obs = step.observation or {}
    if not obs.get("success"):
        return []
    data = obs.get("data") or {}
    paths: list[str] = []
    if isinstance(data, dict):
        fp = data.get("file_path")
        if isinstance(fp, str):
            paths.append(fp)
    return paths


def _check_files(
    expected_list: list[ExpectedFile], trajectory: list[Step]
) -> tuple[bool, list[FileMatchDetail]]:
    details: list[FileMatchDetail] = []
    all_matched = True
    for expected in expected_list:
        candidate_steps = [s for s in trajectory if s.tool_name == expected.tool_name]
        match_path: str | None = None
        size: int | None = None
        reason: str | None = None

        if not candidate_steps:
            reason = f"tool {expected.tool_name} was not called"
        else:
            for step in candidate_steps:
                for path_str in _iter_file_paths_from_step(step):
                    p = Path(path_str)
                    if not p.is_file():
                        reason = f"file not found: {path_str}"
                        continue
                    actual_size = p.stat().st_size
                    if actual_size < expected.min_size_bytes:
                        reason = (
                            f"file too small: {path_str} ({actual_size} < {expected.min_size_bytes})"
                        )
                        size = actual_size
                        continue
                    match_path = path_str
                    size = actual_size
                    reason = None
                    break
                if match_path:
                    break
            if match_path is None and reason is None:
                reason = f"tool {expected.tool_name} did not return a file_path"

        matched = match_path is not None
        details.append(
            FileMatchDetail(
                expected=expected,
                matched=matched,
                file_path=match_path,
                actual_size=size,
                reason=reason,
            )
        )
        if not matched:
            all_matched = False
    return all_matched, details


def _check_tool_calls(
    required_tools: list[str], trajectory: list[Step]
) -> tuple[bool, list[ToolMatchDetail]]:
    details: list[ToolMatchDetail] = []
    all_matched = True
    for tool_name in required_tools:
        ok = any(
            s.tool_name == tool_name and (s.observation or {}).get("success")
            for s in trajectory
        )
        details.append(ToolMatchDetail(tool_name=tool_name, matched=ok))
        if not ok:
            all_matched = False
    return all_matched, details


def check(
    case: TestCase,
    result: AgentResult,
    *,
    tools_available: bool = True,
) -> CheckReport:
    """对一条用例的执行结果做正确性判定。

    Args:
        case: 测试用例（含期望）
        result: Agent 执行结果
        tools_available: 当前 Agent 是否有工具能力。
            False 表示 B0 基线，此时 file_pass / tool_call_pass 不计入 overall，
            只看 numeric_pass，避免对 B0 不公平。

    Returns:
        CheckReport，含三项布尔结论与每项的详细对比结果
    """
    numeric_pass, numeric_details = _check_numeric(case.expected_numeric, result.final_answer)
    file_pass, file_details = _check_files(case.expected_files, result.trajectory)
    tool_call_pass, tool_details = _check_tool_calls(case.required_tools, result.trajectory)

    if tools_available:
        overall = numeric_pass and file_pass and tool_call_pass
    else:
        # B0 没有工具能力：
        # - 若用例要求生成文件，B0 必然失败（无法写文件）
        # - 若用例没有任何数值期望（纯可视化），也判失败，避免 vacuously pass
        # - 否则只看 numeric_pass
        if case.expected_files or not case.expected_numeric:
            overall = False
        else:
            overall = numeric_pass

    return CheckReport(
        case_id=case.id,
        numeric_pass=numeric_pass,
        file_pass=file_pass,
        tool_call_pass=tool_call_pass,
        overall=overall,
        numeric_details=numeric_details,
        file_details=file_details,
        tool_details=tool_details,
    )
