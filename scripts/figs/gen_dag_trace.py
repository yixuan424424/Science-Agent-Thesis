"""生成 ext_dag_01 任务的 DAGPlanner 执行轨迹图 fig_dag_trace.pdf（论文 Figure 6）。

任务: 5 步链式（matrix_operation -> equation_solver -> numerical_integration ->
descriptive_statistics -> line_chart）。

本脚本不依赖运行时数据，仅手工绘制 Plan 中的 5 个步骤与依赖箭头。
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


# (id, x, y, tool, goal_short)
NODES: list[tuple[str, float, float, str, str]] = [
    ("s1", 0.6, 2.5, "matrix_operation",        "det(A)"),
    ("s2", 2.6, 2.5, "equation_solver",         "solve x^2 - D = 0"),
    ("s3", 4.6, 2.5, "numerical_integration",   "∫ f(x) dx"),
    ("s4", 6.6, 2.5, "descriptive_statistics",  "stats(samples)"),
    ("s5", 8.6, 2.5, "line_chart",              "plot trace"),
]

# (from, to, label)
EDGES: list[tuple[str, str, str]] = [
    ("s1", "s2", "${s1.determinant}"),
    ("s2", "s3", "${s2.root}"),
    ("s3", "s4", "${s3.integral}"),
    ("s4", "s5", "${s4.mean}, ${s4.std}"),
]


def main() -> None:
    apply_style()

    fig, ax = plt.subplots(figsize=(9.0, 3.4))
    ax.set_xlim(0, 10)
    ax.set_ylim(0, 5)
    ax.axis("off")

    # 节点
    for sid, x, y, tool, goal in NODES:
        rect = mpatches.FancyBboxPatch(
            (x - 0.7, y - 0.55),
            1.4,
            1.1,
            boxstyle="round,pad=0.05,rounding_size=0.10",
            linewidth=1.1,
            edgecolor="#222",
            facecolor="#F2F2F2",
        )
        ax.add_patch(rect)
        ax.text(x, y + 0.30, sid, ha="center", va="center",
                fontsize=10, weight="bold", color="#222")
        ax.text(x, y - 0.05, tool, ha="center", va="center",
                fontsize=8, color="#222", family="monospace")
        ax.text(x, y - 0.32, goal, ha="center", va="center",
                fontsize=8, color="#555")

    # 边（依赖箭头 + 占位符标签）
    pos: dict[str, tuple[float, float]] = {sid: (x, y) for sid, x, y, *_ in NODES}
    for src, dst, label in EDGES:
        x0, y0 = pos[src]
        x1, y1 = pos[dst]
        ax.add_patch(
            FancyArrowPatch(
                (x0 + 0.7, y0),
                (x1 - 0.7, y1),
                arrowstyle="->",
                mutation_scale=14,
                linewidth=1.3,
                color="#1565C0",
            )
        )
        ax.text(
            (x0 + x1) / 2,
            y0 + 0.78,
            label,
            ha="center",
            va="center",
            fontsize=8,
            color="#1565C0",
            family="monospace",
        )

    # 顶部：阶段标注
    ax.text(0.6, 4.35, "Plan + Validate", ha="center", fontsize=10,
            color="#444", weight="bold")
    ax.text(5.6, 4.35, "Topological Execution",
            ha="center", fontsize=10, color="#444", weight="bold")
    ax.add_patch(
        mpatches.FancyBboxPatch(
            (-0.05, 4.0), 1.3, 0.6,
            boxstyle="round,pad=0.04,rounding_size=0.10",
            linewidth=0.8, edgecolor="#888", facecolor="#FFFAEB",
        )
    )
    ax.add_patch(
        mpatches.FancyBboxPatch(
            (1.4, 4.0), 8.4, 0.6,
            boxstyle="round,pad=0.04,rounding_size=0.10",
            linewidth=0.8, edgecolor="#888", facecolor="#EFF6FF",
        )
    )

    # 底部：Answer 阶段
    ax.text(5.0, 0.65, "Answer LLM (compose final reply with O1-O4 rules)",
            ha="center", fontsize=10, color="#444", weight="bold")
    ax.add_patch(
        mpatches.FancyBboxPatch(
            (1.4, 0.30), 7.2, 0.7,
            boxstyle="round,pad=0.04,rounding_size=0.10",
            linewidth=0.8, edgecolor="#888", facecolor="#F2EAF7",
        )
    )
    # 把所有节点连到底部 answer
    for sid, x, y, *_ in NODES:
        ax.add_patch(
            FancyArrowPatch(
                (x, y - 0.55),
                (x, 1.05),
                arrowstyle="->",
                mutation_scale=10,
                linewidth=0.8,
                linestyle="dashed",
                color="#7E57C2",
            )
        )

    fig.tight_layout()
    out = out_path("fig_dag_trace.pdf")
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
