"""生成 9 配置主实验柱图 fig_main_bar.pdf（论文 Figure 4）。

数据来自 outputs/eval/20260423_103843/summary.md "Overall" 表格。
柱图按 CONFIGS_ORDER 的顺序展示成功率，并对 Ours / Ours_full 用强调色标注。
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import matplotlib.pyplot as plt

from _style import CONFIGS_ORDER, apply_style, out_path


# Source: outputs/eval/20260423_103843/summary.md "Overall" 表
SUCCESS_RATE: dict[str, float] = {
    "B0": 48.1,
    "B1": 90.7,
    "B2": 79.6,
    "B3": 92.6,
    "B4": 94.4,
    "Ours": 100.0,
    "Ours+RATS": 90.7,
    "Ours+DAG": 94.4,
    "Ours_full": 100.0,
}

# 哪些配置加重强调（橙色）
EMPHASIZE: set[str] = {"Ours", "Ours_full"}


def main() -> None:
    apply_style()

    labels = CONFIGS_ORDER
    values = [SUCCESS_RATE[k] for k in labels]
    colors = ["#D17C2D" if k in EMPHASIZE else "#5B7AA0" for k in labels]

    fig, ax = plt.subplots(figsize=(7.4, 3.6))
    bars = ax.bar(labels, values, color=colors, edgecolor="#222", linewidth=0.6)

    # 数值标签
    for b, v in zip(bars, values):
        ax.text(
            b.get_x() + b.get_width() / 2,
            v + 0.8,
            f"{v:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    ax.set_ylabel("Success rate (%)")
    ax.set_ylim(0, 108)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xlabel("Configuration")
    ax.tick_params(axis="x", rotation=15)
    ax.axhline(100, color="#bbb", linewidth=0.6, linestyle=":")
    ax.set_title("Success rate over 54 scientific tasks (9 configurations)")

    fig.tight_layout()
    out = out_path("fig_main_bar.pdf")
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
