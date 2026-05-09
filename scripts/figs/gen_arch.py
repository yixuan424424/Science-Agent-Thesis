"""生成系统架构图 fig_arch.pdf（论文 Figure 1）。

本脚本不依赖任何运行时数据，仅使用 matplotlib 绘制方框 + 箭头，
展示 Ours_full 配置的整体执行流程：
    Task -> RATS (filter) -> DAGPlanner (plan + validate + execute) -> Answer
              \\                                                        /
               '----- fallback ReActAgent (safety net) -----------------'
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch

from _style import apply_style, out_path


def main() -> None:
    apply_style()

    fig, ax = plt.subplots(figsize=(8.0, 4.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    # 顶层组件方框 (x, y, w, h, label)
    boxes: list[tuple[float, float, float, float, str]] = [
        (0.2, 3.5, 1.4, 0.9, "Task T"),
        (1.9, 3.5, 1.6, 0.9, "RATS\n(retrieve + rerank)"),
        (3.8, 3.5, 2.0, 0.9, "DAGPlanner\nPlan + Validate"),
        (6.1, 3.5, 1.8, 0.9, "Topo Execute\n(tool calls)"),
        (8.2, 3.5, 1.6, 0.9, "Answer LLM"),
        # 安全网
        (3.8, 1.6, 4.1, 0.9, "ReActAgent (fallback safety net)"),
        # 底层基础设施
        (0.2, 0.2, 9.6, 0.9, "Tool Library: 12 Scientific Tools (Numerical / Statistics / Visualization)"),
    ]

    for x, y, w, h, label in boxes:
        rect = mpatches.FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0.05,rounding_size=0.10",
            linewidth=1.2,
            edgecolor="#333333",
            facecolor="#F2F2F2",
        )
        ax.add_patch(rect)
        ax.text(
            x + w / 2,
            y + h / 2,
            label,
            ha="center",
            va="center",
            fontsize=10,
            color="#222222",
        )

    # 主链路箭头
    main_chain = [
        (1.6, 3.95, 1.9, 3.95),   # Task -> RATS
        (3.5, 3.95, 3.8, 3.95),   # RATS -> DAGPlanner
        (5.8, 3.95, 6.1, 3.95),   # DAGPlanner -> Execute
        (7.9, 3.95, 8.2, 3.95),   # Execute -> Answer
    ]
    for x0, y0, x1, y1 in main_chain:
        ax.add_patch(
            FancyArrowPatch(
                (x0, y0),
                (x1, y1),
                arrowstyle="->",
                mutation_scale=14,
                linewidth=1.4,
                color="#222222",
            )
        )

    # validate fail -> fallback (curved)
    ax.add_patch(
        FancyArrowPatch(
            (4.8, 3.5),
            (5.85, 2.5),
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.2,
            color="#A33",
            linestyle="dashed",
            connectionstyle="arc3,rad=0.25",
        )
    )
    ax.text(
        5.0, 3.05,
        "fail x3\nfallback",
        ha="left", va="center",
        fontsize=8.5, color="#A33",
    )

    # validate fail self-loop (replan)
    ax.add_patch(
        FancyArrowPatch(
            (4.4, 4.4),
            (5.0, 4.4),
            arrowstyle="->",
            mutation_scale=10,
            linewidth=1.0,
            color="#1565C0",
            connectionstyle="arc3,rad=-0.55",
        )
    )
    ax.text(
        4.7, 4.78,
        "replan w/ hint",
        ha="center", va="center",
        fontsize=8.5, color="#1565C0",
    )

    # fallback path arrows back to answer
    ax.add_patch(
        FancyArrowPatch(
            (7.9, 2.05),
            (8.95, 3.5),
            arrowstyle="->",
            mutation_scale=12,
            linewidth=1.2,
            color="#A33",
            linestyle="dashed",
            connectionstyle="arc3,rad=-0.25",
        )
    )

    # tool library connection (vertical dotted lines from execute & fallback to library)
    for x0 in (7.0, 5.85):
        ax.add_patch(
            FancyArrowPatch(
                (x0, 1.6),
                (x0, 1.1),
                arrowstyle="-",
                mutation_scale=8,
                linewidth=0.9,
                linestyle=":",
                color="#444",
            )
        )

    # Title-ish caption inside figure (not the LaTeX caption)
    ax.text(
        5.0,
        4.95,
        "Ours_full = Prompt v4 + RATS + DAGPlanner (with ReAct safety net)",
        ha="center",
        va="top",
        fontsize=10,
        color="#000",
        weight="bold",
    )

    fig.tight_layout()
    out = out_path("fig_arch.pdf")
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
