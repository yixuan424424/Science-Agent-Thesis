"""评测主入口。

用法（在项目根目录、激活 venv 之后）：

    # 跑全量（3 configs x 12 cases = 36 次 LLM 串行调用，约 5-10 分钟）
    python scripts/run_eval.py

    # 仅跑某些配置
    python scripts/run_eval.py --configs b1 ours

    # 仅跑某些用例
    python scripts/run_eval.py --cases stats_01 comp_01

    # 只打印将要跑的内容，不真发请求（用例自检 / 排错用）
    python scripts/run_eval.py --dry-run
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

# 让脚本直接 python scripts/run_eval.py 也能 import src.*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Windows PowerShell 下默认 GBK，提前把 stdout 切成 UTF-8 防止 print 中文崩溃
for _name in ("stdout", "stderr"):
    _stream = getattr(sys, _name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

from src.agent import NoToolsAgent, ReActAgent  # noqa: E402
from src.eval import DEFAULT_CASES_PATH, RunRecord, load_cases, run_case, write_report  # noqa: E402
from src.prompts import MINIMAL_PROMPT, SYSTEM_PROMPT  # noqa: E402
from src.tools import build_all_tools  # noqa: E402


CONFIG_NAMES = ["b0", "b1", "ours"]


def build_agent(config: str):
    """根据配置名构造对应的 agent；返回 (agent, tools_available)。"""
    if config == "b0":
        return NoToolsAgent(), False
    if config == "b1":
        return ReActAgent(tools=build_all_tools(), system_prompt=MINIMAL_PROMPT), True
    if config == "ours":
        return ReActAgent(tools=build_all_tools(), system_prompt=SYSTEM_PROMPT), True
    raise ValueError(f"Unknown config: {config}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run evaluation across configurations.")
    parser.add_argument(
        "--configs",
        nargs="+",
        default=CONFIG_NAMES,
        choices=CONFIG_NAMES,
        help="Which configurations to evaluate (default: all).",
    )
    parser.add_argument(
        "--cases",
        nargs="+",
        default=None,
        help="Optional list of case ids to run (default: all in test_cases.json).",
    )
    parser.add_argument(
        "--cases-file",
        type=Path,
        default=DEFAULT_CASES_PATH,
        help=f"Path to test cases JSON (default: {DEFAULT_CASES_PATH}).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the planned runs without calling the LLM.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=10,
        help="Max ReAct iterations for B1/Ours (default: 10).",
    )
    return parser.parse_args()


def _print_plan(cases, configs) -> None:
    print(f"Planned runs: {len(cases)} cases x {len(configs)} configs = {len(cases) * len(configs)}")
    print(f"Cases: {[c.id for c in cases]}")
    print(f"Configs: {configs}")
    print()
    for case in cases:
        print(f"- [{case.id}] ({case.category}/{case.difficulty}) {case.task}")
        for ev in case.expected_numeric:
            print(f"    expect numeric: {ev.name} = {ev.value} (tol {ev.tolerance})")
        for ef in case.expected_files:
            print(f"    expect file from tool: {ef.tool_name} (>= {ef.min_size_bytes} bytes)")
        if case.required_tools:
            print(f"    required tools: {case.required_tools}")


def main() -> None:
    args = parse_args()
    cases = load_cases(path=args.cases_file, case_ids=args.cases)
    configs: list[str] = args.configs

    if args.dry_run:
        _print_plan(cases, configs)
        return

    _print_plan(cases, configs)
    print()
    print("Starting evaluation...")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    records: list[RunRecord] = []

    total = len(cases) * len(configs)
    counter = 0
    for config in configs:
        agent, tools_available = build_agent(config)
        for case in cases:
            counter += 1
            print(f"[{counter}/{total}] config={config} case={case.id} ... ", end="", flush=True)
            record = run_case(case, agent, config_name=config, tools_available=tools_available)
            mark = "PASS" if record.success else "FAIL"
            err = f" (error: {record.error})" if record.error else ""
            print(
                f"{mark} | {record.iterations}it / "
                f"{record.total_tool_calls}tc / "
                f"{record.duration_seconds:.1f}s{err}"
            )
            records.append(record)

    out_dir = write_report(records, cases, timestamp=timestamp,
                           extra_meta={"configs": configs, "cli_args": vars(args).__str__()})
    print()
    print(f"Done. Report written to: {out_dir}")
    print(f"  - {out_dir / 'summary.md'}")
    print(f"  - {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
