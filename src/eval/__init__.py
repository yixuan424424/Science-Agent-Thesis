"""Evaluation harness：测试用例 / 检查器 / 运行器 / 报告生成。"""

from .cases import (
    DEFAULT_CASES_PATH,
    ExpectedFile,
    ExpectedNumeric,
    TestCase,
    load_cases,
)
from .checker import CheckReport, check
from .runner import RunRecord, run_case
from .report import write_report

__all__ = [
    "DEFAULT_CASES_PATH",
    "ExpectedFile",
    "ExpectedNumeric",
    "TestCase",
    "load_cases",
    "CheckReport",
    "check",
    "RunRecord",
    "run_case",
    "write_report",
]
