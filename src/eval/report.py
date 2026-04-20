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
