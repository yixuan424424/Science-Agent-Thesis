"""生成类别 x 配置成功率热力图 fig_heatmap.pdf（论文 Figure 5）。

数据来自 outputs/eval/20260423_103843/summary.md "By category" 表格。
"""

from __future__ import annotations

import sys
from pathlib import Path

THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(THIS_DIR))

import matplotlib.pyplot as plt
import numpy as np

from _style import CATEGORIES_ORDER, CONFIGS_ORDER, apply_style, out_path


# Source: outputs/eval/20260423_103843/summary.md "By category" 表
# 单位: percentage (0-100)
RATE_BY_CAT: dict[str, dict[str, float]] = {
    # row = category, col = config
    "numerical":      {"B0": 89, "B1": 100, "B2": 100, "B3":  89, "B4": 100, "Ours": 100, "Ours+RATS": 100, "Ours+DAG": 100, "Ours_full": 100},
    "statistics":     {"B0": 80, "B1": 100, "B2":  90, "B3":  90, "B4": 100, "Ours": 100, "Ours+RATS": 100, "Ours+DAG": 100, "Ours_full": 100},
    "visualization":  {"B0":  0, "B1":  86, "B2":  71, "B3": 100, "B4": 100, "Ours": 100, "Ours+RATS":  86, "Ours+DAG": 100, "Ours_full": 100},
    "composite":      {"B0": 23, "B1":  82, "B2":  77, "B3":  91, "B4":  86, "Ours": 100, "Ours+RATS":  82, "Ours+DAG":  86, "Ours_full": 100},
    "error_recovery": {"B0": 83, "B1": 100, "B2":  50, "B3": 100, "B4": 100, "Ours": 100, "Ours+RATS": 100, "Ours+DAG": 100, "Ours_full": 100},
}


def main() -> None:
    apply_style()

    rows = CATEGORIES_ORDER
    cols = CONFIGS_ORDER
    matrix = np.array([[RATE_BY_CAT[r][c] for c in cols] for r in rows], dtype=float)

    fig, ax = plt.subplots(figsize=(8.0, 3.5))
    im = ax.imshow(matrix, cmap="YlGnBu", vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(len(cols)))
    ax.set_xticklabels(cols, rotation=15, ha="right")
    ax.set_yticks(range(len(rows)))
    ax.set_yticklabels(rows)

    for i in range(len(rows)):
        for j in range(len(cols)):
            v = matrix[i, j]
            color = "white" if v >= 60 else "#333"
            ax.text(j, i, f"{int(round(v))}", ha="center", va="center",
                    color=color, fontsize=8.5)

    cbar = fig.colorbar(im, ax=ax, fraction=0.030, pad=0.02)
    cbar.set_label("Success rate (%)")
    ax.set_title("Per-category success rate (rows: 5 categories, cols: 9 configs)")

    fig.tight_layout()
    out = out_path("fig_heatmap.pdf")
    fig.savefig(out)
    print(f"saved {out}")


if __name__ == "__main__":
    main()
