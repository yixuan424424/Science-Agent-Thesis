"""checker.py 的回归单测。

重点覆盖：
1. abs_tolerance 生效（严化后小误差应判 FAIL）
2. 相对/绝对双阈值的取 max 行为
3. B0 tools_available=False 时的 vacuous pass 防御
4. required_tools 组内 OR / 组间 AND / 空列表无要求
"""

from __future__ import annotations

from src.agent.messages import AgentResult, Step
from src.eval.cases import ExpectedFile, ExpectedNumeric, TestCase
from src.eval.checker import _is_match, check


def _mk_result(final: str, steps: list[Step] | None = None) -> AgentResult:
    return AgentResult(
        final_answer=final,
        trajectory=steps or [],
        iterations_used=1,
        stopped_reason="final_answer",
    )


def test_is_match_default_abs_tolerance_tolerates_small_error():
    """默认 abs_tolerance=0.01 时，5.0 ± 0.009 应命中。"""
    exp = ExpectedNumeric(name="x", value=5.0, tolerance=1e-9, abs_tolerance=0.01)
    assert _is_match(exp, 5.009) is True
    assert _is_match(exp, 4.991) is True


def test_is_match_tight_abs_tolerance_rejects_small_error():
    """严化 abs_tolerance=1e-6 时，5.0 ± 0.009 应被判 miss。"""
    exp = ExpectedNumeric(name="x", value=5.0, tolerance=1e-9, abs_tolerance=1e-6)
    assert _is_match(exp, 5.009) is False
    assert _is_match(exp, 5.0000005) is True


def test_is_match_uses_max_of_two_thresholds():
    """value=100, tolerance=0.02 时，相对阈值 2.0 应压过 abs_tolerance 0.01。"""
    exp = ExpectedNumeric(name="x", value=100.0, tolerance=0.02, abs_tolerance=1e-6)
    assert _is_match(exp, 101.5) is True
    assert _is_match(exp, 103.0) is False


def test_check_numeric_strict_catches_rounded_value():
    """LLM 把 0.333333 截成 0.3 时，严化 tolerance 能判 FAIL。"""
    case = TestCase(
        id="t",
        category="numerical",
        difficulty="easy",
        task="",
        expected_numeric=[
            ExpectedNumeric(
                name="integral", value=0.3333333, tolerance=0.001, abs_tolerance=1e-4
            )
        ],
    )
    result = _mk_result("The integral is about 0.3.")
    report = check(case, result, tools_available=False)
    assert report.numeric_pass is False
    assert report.overall is False


def test_check_tools_available_false_rejects_file_expectation():
    """B0 配置下，有 expected_files 的题目直接判 FAIL，不允许 vacuous pass。"""
    case = TestCase(
        id="t",
        category="visualization",
        difficulty="easy",
        task="",
        expected_numeric=[],
        expected_files=[ExpectedFile(tool_name="line_chart", min_size_bytes=1024)],
    )
    result = _mk_result("Here is the code: plt.plot(...)")
    report = check(case, result, tools_available=False)
    assert report.overall is False


def test_check_tool_calls_or_within_group():
    """required_tools = [[a, b], [c]]，调用 a 和 c 即可通过。"""
    case = TestCase(
        id="t",
        category="numerical",
        difficulty="easy",
        task="",
        expected_numeric=[ExpectedNumeric(name="x", value=1.0)],
        required_tools=[["linear_regression", "curve_fitting"], ["scatter_chart"]],
    )
    traj = [
        Step(
            iteration=1,
            thought="",
            tool_name="linear_regression",
            tool_arguments={},
            observation={"success": True, "data": {}},
        ),
        Step(
            iteration=2,
            thought="",
            tool_name="scatter_chart",
            tool_arguments={},
            observation={"success": True, "data": {"file_path": "/tmp/x.png"}},
        ),
    ]
    result = AgentResult(
        final_answer="slope = 1.0",
        trajectory=traj,
        iterations_used=2,
        stopped_reason="final_answer",
    )
    report = check(case, result, tools_available=True)
    assert report.tool_call_pass is True


def test_check_tool_calls_empty_means_no_requirement():
    """required_tools=[] 时直接视为 tool_call_pass=True。"""
    case = TestCase(
        id="t",
        category="numerical",
        difficulty="easy",
        task="",
        expected_numeric=[ExpectedNumeric(name="x", value=1.0)],
        required_tools=[],
    )
    result = _mk_result("x = 1.0")
    report = check(case, result, tools_available=True)
    assert report.tool_call_pass is True


def test_check_tool_calls_missing_group_fails():
    """required 的某组工具一个都没调用，tool_call_pass 应 False。"""
    case = TestCase(
        id="t",
        category="numerical",
        difficulty="easy",
        task="",
        expected_numeric=[ExpectedNumeric(name="x", value=1.0)],
        required_tools=[["linear_regression"], ["scatter_chart"]],
    )
    traj = [
        Step(
            iteration=1,
            thought="",
            tool_name="linear_regression",
            tool_arguments={},
            observation={"success": True, "data": {}},
        ),
    ]
    result = AgentResult(
        final_answer="slope = 1.0",
        trajectory=traj,
        iterations_used=1,
        stopped_reason="final_answer",
    )
    report = check(case, result, tools_available=True)
    assert report.tool_call_pass is False
    missed = [d.display() for d in report.tool_details if not d.matched]
    assert "scatter_chart" in missed
