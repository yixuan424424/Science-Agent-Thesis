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

from src.agent import (  # noqa: E402
    CoTReActAgent,
    DAGAgent,
    NoToolsAgent,
    PlanAndSolveAgent,
    ReActAgent,
    ReflexionAgent,
)
from src.agent.messages import AgentResult  # noqa: E402
from src.eval import DEFAULT_CASES_PATH, RunRecord, load_cases, run_case, write_report  # noqa: E402
from src.prompts import MINIMAL_PROMPT, SYSTEM_PROMPT  # noqa: E402
from src.tool_selector import RATS  # noqa: E402
from src.tools import build_all_tools  # noqa: E402


# 所有支持的配置名:
# - b0/b1/ours 为原有（ours = v4 SYSTEM_PROMPT + ReAct）
# - b2         : CoT + 工具
# - b3         : Plan-and-Solve 两阶段（无 JSON 校验）
# - b4         : Reflexion（失败即反思）
# - ours_rats  : v4 Prompt + ReAct + RATS（只上工具选择）
# - ours_dag   : v4 Prompt + DAGAgent（只上结构化规划，不筛工具）
# - ours_full  : v4 Prompt + DAGAgent + RATS（主打配置）
CONFIG_NAMES = [
    "b0", "b1", "b2", "b3", "b4",
    "ours", "ours_rats", "ours_dag", "ours_full",
]


class RATSReActAgent:
    """每次 run(task) 前用 RATS 筛一遍工具，再委托给内置 ReActAgent。

    用于 ``ours_rats`` 配置：v4 Prompt 和 ReAct 主循环保持不变，唯一差异是
    工具集合变成"按任务精简后的子集"。
    """

    def __init__(
        self,
        tools: list,
        selector: RATS,
        system_prompt: str,
        max_iterations: int = 10,
    ) -> None:
        self._tools = tools
        self._selector = selector
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations

    def run(self, task: str) -> AgentResult:
        selected = self._selector.select(task) or self._tools
        inner = ReActAgent(
            tools=selected,
            system_prompt=self._system_prompt,
            max_iterations=self._max_iterations,
        )
        return inner.run(task)


def _build_rats(tools: list) -> RATS:
    """构造并预热一个 RATS 实例（所有工具向量一次性算好）。"""
    rats = RATS(tools=tools)
    rats.build()
    return rats


def build_agent(config: str, *, max_iterations: int = 10):
    """根据配置名构造对应的 agent；返回 (agent, tools_available)。"""
    if config == "b0":
        return NoToolsAgent(), False
    if config == "b1":
        return ReActAgent(
            tools=build_all_tools(),
            system_prompt=MINIMAL_PROMPT,
            max_iterations=max_iterations,
        ), True
    if config == "ours":
        return ReActAgent(
            tools=build_all_tools(),
            system_prompt=SYSTEM_PROMPT,
            max_iterations=max_iterations,
        ), True
    if config == "b2":
        return CoTReActAgent(
            tools=build_all_tools(),
            max_iterations=max_iterations,
        ), True
    if config == "b3":
        return PlanAndSolveAgent(
            tools=build_all_tools(),
            max_iterations=max_iterations,
        ), True
    if config == "b4":
        return ReflexionAgent(
            tools=build_all_tools(),
            max_iterations=max_iterations,
        ), True
    if config == "ours_rats":
        tools = build_all_tools()
        rats = _build_rats(tools)
        return RATSReActAgent(
            tools=tools,
            selector=rats,
            system_prompt=SYSTEM_PROMPT,
            max_iterations=max_iterations,
        ), True
    if config == "ours_dag":
        return DAGAgent(tools=build_all_tools(), selector=None), True
    if config == "ours_full":
        tools = build_all_tools()
        rats = _build_rats(tools)
        return DAGAgent(tools=tools, selector=rats), True
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
        agent, tools_available = build_agent(config, max_iterations=args.max_iterations)
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
