"""Shared Matplotlib style for thesis figures.

所有图表脚本都先 ``from _style import apply_style; apply_style()``，
确保字号、字体、配色与导出格式（PDF）的一致性。
"""

from __future__ import annotations

import warnings
from pathlib import Path

import matplotlib

# 论文图表用 PDF 导出，再由 LaTeX includegraphics 引入
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402  (must come after backend select)

# 工程根目录: scripts/figs/_style.py -> scripts/figs/ -> scripts/ -> project root
PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]
FIG_OUT_DIR: Path = PROJECT_ROOT / "final_report" / "figure"
RESULTS_PATH: Path = (
    PROJECT_ROOT / "outputs" / "eval" / "20260423_103843" / "results.json"
)
SUMMARY_PATH: Path = (
    PROJECT_ROOT / "outputs" / "eval" / "20260423_103843" / "summary.md"
)


# 9 配置的展示顺序与简短英文标签（避免 LaTeX 端再做映射）
CONFIGS_ORDER: list[str] = [
    "B0",
    "B1",
    "B2",
    "B3",
    "B4",
    "Ours",
    "Ours+RATS",
    "Ours+DAG",
    "Ours_full",
]

# 9 配置在 results.json / summary.md 中可能出现的别名映射
CONFIG_ALIAS: dict[str, str] = {
    "b0_no_tool": "B0",
    "b1_minimal": "B1",
    "b2_cot": "B2",
    "b3_plan_solve": "B3",
    "b4_reflexion": "B4",
    "ours_v4": "Ours",
    "ours_rats": "Ours+RATS",
    "ours_dag": "Ours+DAG",
    "ours_full": "Ours_full",
}

# 5 类任务的展示顺序
CATEGORIES_ORDER: list[str] = [
    "numerical",
    "statistics",
    "visualization",
    "composite",
    "error_recovery",
]


def apply_style() -> None:
    """统一所有图表的 rcParams。"""
    plt.rcParams.update(
        {
            "font.family": ["DejaVu Sans"],
            "font.size": 10,
            "axes.titlesize": 11,
            "axes.labelsize": 10,
            "xtick.labelsize": 9,
            "ytick.labelsize": 9,
            "legend.fontsize": 9,
            "figure.titlesize": 12,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "savefig.bbox": "tight",
            "savefig.dpi": 200,
            "pdf.fonttype": 42,
            "ps.fonttype": 42,
        }
    )
    # 禁用 NotoSansCJK 等中文字体的 missing glyph 警告（轴标签全部使用英文/数字）
    warnings.filterwarnings(
        "ignore",
        message="Glyph .* missing from current font",
    )


def out_path(name: str) -> Path:
    """返回 figure/<name> 的绝对路径，并确保父目录存在。"""
    FIG_OUT_DIR.mkdir(parents=True, exist_ok=True)
    return FIG_OUT_DIR / name


__all__ = [
    "apply_style",
    "out_path",
    "PROJECT_ROOT",
    "FIG_OUT_DIR",
    "RESULTS_PATH",
    "SUMMARY_PATH",
    "CONFIGS_ORDER",
    "CONFIG_ALIAS",
    "CATEGORIES_ORDER",
]
