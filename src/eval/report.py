"""评测报告生成。

输入：list[RunRecord]
输出：
- outputs/eval/<timestamp>/results.json：原始结果（含 trajectory_summary、check_report 明细）
- outputs/eval/<timestamp>/summary.md：人类可读的对比表
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean

from src.config import OUTPUT_DIR
from src.eval.cases import TestCase
from src.eval.runner import RunRecord


_EVAL_ROOT = OUTPUT_DIR / "eval"


def _ensure_output_dir(timestamp: str | None = None) -> Path:
    ts = timestamp or datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = _EVAL_ROOT / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _truncate(text: str, limit: int = 120) -> str:
    text = (text or "").replace("\n", " ").replace("|", "\\|")
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _format_overall_table(records_by_config: dict[str, list[RunRecord]]) -> str:
    lines = [
        "| Config | Cases | Success | Success rate | Avg iterations | Avg tool calls | Avg failed calls | Avg duration (s) |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for config, records in records_by_config.items():
        if not records:
            continue
        n = len(records)
        passed = sum(1 for r in records if r.success)
        rate = passed / n if n else 0.0
        avg_iter = mean(r.iterations for r in records) if records else 0
        avg_calls = mean(r.total_tool_calls for r in records) if records else 0
        avg_failed = mean(r.failed_tool_calls for r in records) if records else 0
        avg_dur = mean(r.duration_seconds for r in records) if records else 0
        lines.append(
            f"| {config} | {n} | {passed} | {rate:.1%} | "
            f"{avg_iter:.2f} | {avg_calls:.2f} | {avg_failed:.2f} | {avg_dur:.2f} |"
        )
    return "\n".join(lines)


def _format_pass_only_efficiency_table(
    records_by_config: dict[str, list[RunRecord]],
) -> str:
    """只统计 pass 用例的平均迭代数 / 工具调用数 / 耗时。

    fail 用例会被"早退"或"崩溃"拉低，失去可比性。pass-only 才能公平衡量
    "同样把题做对时谁更高效"，适合论文里衡量 prompt 优化的效率收益。
    """
    lines = [
        "| Config | Pass cases | Avg iterations (pass) | Avg tool calls (pass) | Avg duration (s, pass) |",
        "|---|---:|---:|---:|---:|",
    ]
    for config, records in records_by_config.items():
        passed = [r for r in records if r.success]
        if not passed:
            lines.append(f"| {config} | 0 | - | - | - |")
            continue
        avg_iter = mean(r.iterations for r in passed)
        avg_calls = mean(r.total_tool_calls for r in passed)
        avg_dur = mean(r.duration_seconds for r in passed)
        lines.append(
            f"| {config} | {len(passed)} | "
            f"{avg_iter:.2f} | {avg_calls:.2f} | {avg_dur:.2f} |"
        )
    return "\n".join(lines)


def _format_delta_vs_b1_table(
    records_by_config: dict[str, list[RunRecord]],
    baseline: str = "b1",
) -> str:
    """展示每个 config 相对基线（默认 b1）的关键指标 delta。

    成功率 delta 用"个数差"（+1 / -2）更直观；效率 delta 用相对百分比。
    效率指标只在 pass 交集（两个 config 都 pass 的用例集合）上比较，
    否则"本方多做对一题"和"那题顺带拖慢平均"会混淆。
    """
    if baseline not in records_by_config:
        return f"_No '{baseline}' baseline available; delta table skipped._"

    base_records = {r.case_id: r for r in records_by_config[baseline]}
    base_pass_ids = {cid for cid, r in base_records.items() if r.success}

    lines = [
        f"Comparison is relative to **{baseline}**. "
        f"Efficiency deltas are computed on cases that BOTH configs passed "
        f"(to avoid mixing 'solved more' with 'spent more time').\n",
        "| Config | Success delta | Shared-pass cases | Iter delta (pass) | Tool-call delta (pass) | Duration delta (pass) |",
        "|---|---:|---:|---:|---:|---:|",
    ]

    for config, records in records_by_config.items():
        if config == baseline:
            lines.append(f"| {config} (baseline) | 0 | - | - | - | - |")
            continue

        this_by_id = {r.case_id: r for r in records}
        this_pass = sum(1 for r in records if r.success)
        base_pass = sum(1 for r in base_records.values() if r.success)
        succ_delta = this_pass - base_pass
        succ_sign = "+" if succ_delta > 0 else ""

        shared_pass_ids = base_pass_ids & {cid for cid, r in this_by_id.items() if r.success}
        if not shared_pass_ids:
            lines.append(
                f"| {config} | {succ_sign}{succ_delta} | 0 | - | - | - |"
            )
            continue

        base_iter = mean(base_records[cid].iterations for cid in shared_pass_ids)
        this_iter = mean(this_by_id[cid].iterations for cid in shared_pass_ids)
        base_tc = mean(base_records[cid].total_tool_calls for cid in shared_pass_ids)
        this_tc = mean(this_by_id[cid].total_tool_calls for cid in shared_pass_ids)
        base_dur = mean(base_records[cid].duration_seconds for cid in shared_pass_ids)
        this_dur = mean(this_by_id[cid].duration_seconds for cid in shared_pass_ids)

        def _pct(now: float, base: float) -> str:
            """形如 '+12.3%' / '-5.1%' / 'n/a'（base=0 无法计算）。"""
            if base == 0:
                return "n/a"
            pct = (now - base) / base * 100
            sign = "+" if pct >= 0 else ""
            return f"{sign}{pct:.1f}%"

        lines.append(
            f"| {config} | {succ_sign}{succ_delta} | {len(shared_pass_ids)} | "
            f"{_pct(this_iter, base_iter)} | "
            f"{_pct(this_tc, base_tc)} | "
            f"{_pct(this_dur, base_dur)} |"
        )

    return "\n".join(lines)


def _format_category_table(
    records_by_config: dict[str, list[RunRecord]],
    cases: list[TestCase],
) -> str:
    cat_of: dict[str, str] = {c.id: c.category for c in cases}
    categories = sorted({c.category for c in cases})
    configs = list(records_by_config.keys())

    header = "| Category | " + " | ".join(configs) + " |"
    sep = "|---|" + "|".join(["---:"] * len(configs)) + "|"
    lines = [header, sep]
    for cat in categories:
        cells = [cat]
        for config in configs:
            relevant = [r for r in records_by_config[config] if cat_of.get(r.case_id) == cat]
            if relevant:
                passed = sum(1 for r in relevant if r.success)
                cells.append(f"{passed}/{len(relevant)} ({passed / len(relevant):.0%})")
            else:
                cells.append("-")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_case_detail_table(
    records_by_config: dict[str, list[RunRecord]],
    cases: list[TestCase],
) -> str:
    case_order = [c.id for c in cases]
    configs = list(records_by_config.keys())
    by_case: dict[str, dict[str, RunRecord]] = defaultdict(dict)
    for config, records in records_by_config.items():
        for r in records:
            by_case[r.case_id][config] = r

    header = "| Case | Category | " + " | ".join(configs) + " | Diagnostic |"
    sep = "|---|---|" + "|".join(["---"] * len(configs)) + "|---|"
    lines = [header, sep]

    cat_of: dict[str, str] = {c.id: c.category for c in cases}

    for cid in case_order:
        if cid not in by_case:
            continue
        per_config = by_case[cid]
        cells = [cid, cat_of.get(cid, "")]
        diag_parts: list[str] = []
        for config in configs:
            r = per_config.get(config)
            if r is None:
                cells.append("-")
                continue
            mark = "PASS" if r.success else "FAIL"
            cells.append(f"{mark} ({r.iterations}it/{r.total_tool_calls}tc)")
            if not r.success:
                diag_parts.append(f"{config}: {r.check_report.short_diagnostic()}")
        cells.append(_truncate("; ".join(diag_parts), 200) if diag_parts else "")
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def _format_failures_section(records_by_config: dict[str, list[RunRecord]]) -> str:
    sections: list[str] = []
    for config, records in records_by_config.items():
        failed = [r for r in records if not r.success]
        if not failed:
            continue
        sections.append(f"### {config} failures ({len(failed)})\n")
        for r in failed:
            diag = r.check_report.short_diagnostic()
            answer = _truncate(r.final_answer, 200)
            err = f" | error: {r.error}" if r.error else ""
            sections.append(f"- **{r.case_id}** — {diag}{err}\n  - final: {answer}")
        sections.append("")
    return "\n".join(sections)


def write_report(
    records: list[RunRecord],
    cases: list[TestCase],
    *,
    timestamp: str | None = None,
    extra_meta: dict | None = None,
) -> Path:
    """把所有 RunRecord 写入 results.json + summary.md，返回输出目录路径。"""
    out_dir = _ensure_output_dir(timestamp)

    records_by_config: dict[str, list[RunRecord]] = defaultdict(list)
    for r in records:
        records_by_config[r.config].append(r)
    records_by_config = dict(records_by_config)

    results_path = out_dir / "results.json"
    with results_path.open("w", encoding="utf-8") as f:
        json.dump(
            {
                "meta": {
                    "timestamp": timestamp or datetime.now().strftime("%Y%m%d_%H%M%S"),
                    "n_cases": len({r.case_id for r in records}),
                    "n_configs": len(records_by_config),
                    "n_runs": len(records),
                    **(extra_meta or {}),
                },
                "records": [r.to_dict() for r in records],
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    summary_path = out_dir / "summary.md"
    parts: list[str] = []
    parts.append(f"# Evaluation Summary ({timestamp or out_dir.name})\n")
    if extra_meta:
        parts.append("## Meta\n")
        for k, v in extra_meta.items():
            parts.append(f"- **{k}**: {v}")
        parts.append("")

    parts.append("## Overall\n")
    parts.append(_format_overall_table(records_by_config))
    parts.append("")

    parts.append("## Efficiency on passed cases\n")
    parts.append(_format_pass_only_efficiency_table(records_by_config))
    parts.append("")

    parts.append("## Delta vs baseline\n")
    parts.append(_format_delta_vs_b1_table(records_by_config, baseline="b1"))
    parts.append("")

    parts.append("## By category (success / total)\n")
    parts.append(_format_category_table(records_by_config, cases))
    parts.append("")

    parts.append("## By case\n")
    parts.append("Cells show `PASS/FAIL (iterations / tool_calls)`.\n")
    parts.append(_format_case_detail_table(records_by_config, cases))
    parts.append("")

    failures = _format_failures_section(records_by_config)
    if failures:
        parts.append("## Failures\n")
        parts.append(failures)

    summary_path.write_text("\n".join(parts), encoding="utf-8")
    return out_dir
