"""测试用例的数据类与 JSON 加载器。

测试用例定义在 [tests/data/test_cases.json](tests/data/test_cases.json)，
评测脚本通过 `load_cases()` 读入并转为 `TestCase` 对象列表。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from src.config import PROJECT_ROOT


DEFAULT_CASES_PATH: Path = PROJECT_ROOT / "tests" / "data" / "test_cases.json"


@dataclass
class ExpectedNumeric:
    """单个数值期望。

    name 仅用于报告里指代某个具体指标（如 "mean"）。
    匹配判定见 checker：使用 max(0.01 绝对误差, value*tolerance) 双阈值。
    """

    name: str
    value: float
    tolerance: float = 0.02  # 默认 2% 相对误差


@dataclass
class ExpectedFile:
    """单个图表文件期望。

    tool_name：负责生成此文件的工具名（如 "bar_chart"）；
    checker 会扫描轨迹中该工具的 observation.data.file_path 并检查文件实际存在。
    """

    tool_name: str
    min_size_bytes: int = 1024


@dataclass
class TestCase:
    """单条测试用例。

    required_tools 采用"组列表"结构：外层 AND、内层 OR。
    - 例如 [["curve_fitting", "linear_regression"], ["scatter_chart"]] 表示
      "curve_fitting 或 linear_regression 必须被调用一次，且 scatter_chart 必须被调用一次"。
    - 空列表 [] 表示不强制任何工具，checker 此时的 tool_call_pass 直接视为 True。
    - JSON 中可以写成老格式 ["a", "b"]，加载时会自动归一化为 [["a"], ["b"]]（即 AND 语义）。
    """

    id: str
    category: str  # numerical / statistics / visualization / composite / error_recovery
    difficulty: str  # easy / medium / hard
    task: str
    expected_numeric: list[ExpectedNumeric] = field(default_factory=list)
    expected_files: list[ExpectedFile] = field(default_factory=list)
    required_tools: list[list[str]] = field(default_factory=list)


def load_cases(
    path: str | Path = DEFAULT_CASES_PATH,
    case_ids: list[str] | None = None,
) -> list[TestCase]:
    """加载测试用例。

    Args:
        path: JSON 文件路径，默认指向 tests/data/test_cases.json
        case_ids: 若提供，仅返回 id 在该列表中的用例，并保持文件中的原始顺序

    Returns:
        TestCase 列表
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"Test cases file not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if not isinstance(raw, dict) or "cases" not in raw:
        raise ValueError(
            f"Invalid test cases file structure in {path}: expected top-level 'cases' key."
        )

    cases: list[TestCase] = []
    for entry in raw["cases"]:
        case = _parse_case(entry)
        if case_ids is None or case.id in case_ids:
            cases.append(case)

    if case_ids is not None:
        unknown = set(case_ids) - {c.id for c in cases}
        if unknown:
            raise ValueError(f"Unknown case ids: {sorted(unknown)}")

    return cases


def _parse_case(entry: dict) -> TestCase:
    expected_numeric = [
        ExpectedNumeric(
            name=item["name"],
            value=float(item["value"]),
            tolerance=float(item.get("tolerance", 0.02)),
        )
        for item in entry.get("expected_numeric", [])
    ]
    expected_files = [
        ExpectedFile(
            tool_name=item["tool_name"],
            min_size_bytes=int(item.get("min_size_bytes", 1024)),
        )
        for item in entry.get("expected_files", [])
    ]
    return TestCase(
        id=entry["id"],
        category=entry["category"],
        difficulty=entry["difficulty"],
        task=entry["task"],
        expected_numeric=expected_numeric,
        expected_files=expected_files,
        required_tools=_normalize_required_tools(entry.get("required_tools", [])),
    )


def _normalize_required_tools(raw: list) -> list[list[str]]:
    """把 JSON 里的 required_tools 统一归一化为 list[list[str]]。

    允许两种写法：
    - 老格式：["tool_a", "tool_b"]，解释为 [["tool_a"], ["tool_b"]]（AND 语义）
    - 新格式：[["tool_a", "tool_b"], ["tool_c"]]，第一组 OR、组之间 AND
    - 空列表 []：保持为 []，表示不强制任何工具

    允许两种写法混用，便于老测试用例与新测试用例共存。
    """
    groups: list[list[str]] = []
    for item in raw:
        if isinstance(item, str):
            groups.append([item])
        elif isinstance(item, list):
            cleaned = [str(t) for t in item if t]
            if not cleaned:
                raise ValueError(f"Empty group in required_tools: {item!r}")
            groups.append(cleaned)
        else:
            raise ValueError(f"Invalid required_tools entry (expect str or list): {item!r}")
    return groups
