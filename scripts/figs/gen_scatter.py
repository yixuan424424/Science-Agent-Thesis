"""生成迭代次数与端到端耗时的散点图 fig_scatter.pdf（论文 Figure 7）。

数据来自 outputs/eval/20260518_120256/summary.md "Overall" 表格。
横轴: 平均工具调用次数；纵轴: 平均端到端耗时（秒）；点的大小代表成功率。
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import matplotlib.pyplot as plt

from _style import CONFIGS_ORDER, apply_style, out_path


# Source: outputs/eval/20260518_120256/summary.md "Overall" 表
# (config, success_rate, avg_tool_calls, avg_duration_sec)
DATA: dict[str, tuple[float, float, float]] = {
    "B0":         (44.9, 0.00, 10.08),
    "B1":         (83.1, 2.85,  4.14),
    "B2":         (82.0, 2.81,  4.09),
    "B3":         (80.9, 3.89,  5.52),
    "B4":         (83.1, 3.25,  5.79),
    "Ours":       (91.0, 2.94,  4.98),
    "Ours+RATS":  (83.1, 3.18,  6.78),
    "Ours+DAG":   (83.1, 6.34, 13.17),
    "Ours_full":  (85.4, 5.71, 13.29),
}

EMPHASIZE: set[str] = {"Ours", "Ours_full"}


def main() -> None:
    apply_style()

    fig, ax = plt.subplots(figsize=(6.6, 4.4))

    # 用成功率把点的大小放大成视觉权重；线性映射到面积
    base_size = 60
    for label in CONFIGS_ORDER:
        sr, tc, dur = DATA[label]
        size = base_size + (sr - 40) * 4  # 40% -> 60, 100% -> 300
        color = "#D17C2D" if label in EMPHASIZE else "#5B7AA0"
        edge = "#222"
        ax.scatter(tc, dur, s=size, color=color, edgecolor=edge, linewidth=0.8,
                   alpha=0.85, zorder=3)
        ax.annotate(
            label,
            (tc, dur),
            textcoords="offset points",
            xytext=(8, 6),
            fontsize=8.5,
            color="#222",
        )

    ax.set_xlabel("Average tool calls per task")
    ax.set_ylabel("Average end-to-end duration (s)")
    ax.set_xlim(-0.4, 7.5)
    ax.set_ylim(0, 16)
    ax.grid(True, linestyle=":", linewidth=0.5, color="#bbb", alpha=0.7)
    ax.set_title("Tool-call usage vs duration (point size ~ success rate)")

    fig.tight_layout()
    out = out_path("fig_scatter.pdf")
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
