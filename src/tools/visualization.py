"""数据可视化类工具集，基于 Matplotlib。

设计要点：
- 使用 Agg 后端，确保在无显示环境下也能正常生成图片
- 所有图片保存到 OUTPUT_DIR/ 下，文件名带时间戳避免覆盖
- ToolResult.data 返回 file_path、figure_size 等信息
- 中文字体回退方案：优先尝试系统中文字体，找不到时退化为英文标签
"""

from datetime import datetime
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from ..config import OUTPUT_DIR
from .base import BaseTool, ToolParameter, ToolResult


_CN_FONT_CANDIDATES = [
    "Microsoft YaHei", "SimHei", "PingFang SC", "Noto Sans CJK SC",
    "Source Han Sans SC", "Heiti SC", "Arial Unicode MS",
]


def _setup_chinese_font() -> None:
    """尽量配置中文字体，找不到也不报错。"""
    from matplotlib import font_manager
    available = {f.name for f in font_manager.fontManager.ttflist}
    for font in _CN_FONT_CANDIDATES:
        if font in available:
            plt.rcParams["font.sans-serif"] = [font]
            plt.rcParams["axes.unicode_minus"] = False
            return


_setup_chinese_font()


def _new_output_path(prefix: str) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    return Path(OUTPUT_DIR) / f"{prefix}_{timestamp}.png"


class _ChartToolBase(BaseTool):
    """可视化工具的公共基类，封装保存图片的样板代码。"""

    def _save_figure(self, fig, prefix: str) -> dict:
        path = _new_output_path(prefix)
        fig.savefig(path, dpi=120, bbox_inches="tight")
        plt.close(fig)
        size = fig.get_size_inches() * fig.dpi
        return {
            "file_path": str(path),
            "width_pixels": int(size[0]),
            "height_pixels": int(size[1]),
        }


class LineChartTool(_ChartToolBase):
    """折线图工具，支持单条或多条曲线。"""

    @property
    def name(self) -> str:
        return "line_chart"

    @property
    def description(self) -> str:
        return (
            "绘制折线图。x 是横轴数据列表，y 是纵轴数据。"
            "若 y 是一维列表，绘制单条曲线；若 y 是二维列表（每行一条曲线），绘制多条曲线。"
            "可选参数: title, xlabel, ylabel, series_labels（多曲线时的图例标签）。"
            "图片自动保存到 outputs/ 目录，返回文件路径。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="x", type="array", description="横轴数据", items_type="number"),
            ToolParameter(name="y", type="array", description="纵轴数据，一维列表或二维列表"),
            ToolParameter(name="title", type="string", description="图标题",
                          required=False, default=""),
            ToolParameter(name="xlabel", type="string", description="x 轴标签",
                          required=False, default="x"),
            ToolParameter(name="ylabel", type="string", description="y 轴标签",
                          required=False, default="y"),
            ToolParameter(name="series_labels", type="array",
                          description="多曲线时各条线的图例标签列表",
                          items_type="string", required=False, default=None),
        ]

    def execute(self, **kwargs) -> ToolResult:
        x = np.array(kwargs["x"], dtype=float)
        y_raw = kwargs["y"]
        y = np.array(y_raw, dtype=float)

        fig, ax = plt.subplots(figsize=(8, 5))

        if y.ndim == 1:
            ax.plot(x, y, marker="o")
        else:
            labels = kwargs.get("series_labels") or [f"series {i+1}" for i in range(y.shape[0])]
            for i, row in enumerate(y):
                label = labels[i] if i < len(labels) else f"series {i+1}"
                ax.plot(x, row, marker="o", label=label)
            ax.legend()

        ax.set_title(kwargs.get("title") or "")
        ax.set_xlabel(kwargs.get("xlabel") or "x")
        ax.set_ylabel(kwargs.get("ylabel") or "y")
        ax.grid(True, alpha=0.3)

        info = self._save_figure(fig, "line_chart")
        return ToolResult(success=True, data=info,
                          message=f"折线图已保存到 {info['file_path']}")


class ScatterChartTool(_ChartToolBase):
    """散点图工具，可选叠加线性拟合线。"""

    @property
    def name(self) -> str:
        return "scatter_chart"

    @property
    def description(self) -> str:
        return (
            "绘制散点图。给定 x 和 y 两个等长数据列表，绘制散点。"
            "可选参数 fit_line=true 时叠加一条线性拟合线。"
            "图片自动保存到 outputs/ 目录。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="x", type="array", description="横轴数据", items_type="number"),
            ToolParameter(name="y", type="array", description="纵轴数据", items_type="number"),
            ToolParameter(name="title", type="string", description="图标题",
                          required=False, default=""),
            ToolParameter(name="xlabel", type="string", description="x 轴标签",
                          required=False, default="x"),
            ToolParameter(name="ylabel", type="string", description="y 轴标签",
                          required=False, default="y"),
            ToolParameter(name="fit_line", type="boolean",
                          description="是否叠加线性拟合线，默认 false",
                          required=False, default=False),
        ]

    def execute(self, **kwargs) -> ToolResult:
        x = np.array(kwargs["x"], dtype=float)
        y = np.array(kwargs["y"], dtype=float)

        if len(x) != len(y):
            return ToolResult(success=False, error="x 和 y 长度不一致",
                              message=f"x 长度 {len(x)}, y 长度 {len(y)}")

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.scatter(x, y, alpha=0.7, edgecolors="k", linewidths=0.5)

        if kwargs.get("fit_line"):
            slope, intercept = np.polyfit(x, y, 1)
            xs = np.linspace(x.min(), x.max(), 100)
            ax.plot(xs, slope * xs + intercept, color="red",
                    label=f"y = {slope:.3f}x + {intercept:.3f}")
            ax.legend()

        ax.set_title(kwargs.get("title") or "")
        ax.set_xlabel(kwargs.get("xlabel") or "x")
        ax.set_ylabel(kwargs.get("ylabel") or "y")
        ax.grid(True, alpha=0.3)

        info = self._save_figure(fig, "scatter_chart")
        return ToolResult(success=True, data=info,
                          message=f"散点图已保存到 {info['file_path']}")


class BarChartTool(_ChartToolBase):
    """柱状图工具。"""

    @property
    def name(self) -> str:
        return "bar_chart"

    @property
    def description(self) -> str:
        return (
            "绘制柱状图。categories 是分类标签列表，values 是对应的数值列表。"
            "两者长度必须一致。图片自动保存到 outputs/ 目录。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="categories", type="array",
                          description="分类标签列表，如 ['A', 'B', 'C']",
                          items_type="string"),
            ToolParameter(name="values", type="array",
                          description="对应的数值列表，与 categories 等长",
                          items_type="number"),
            ToolParameter(name="title", type="string", description="图标题",
                          required=False, default=""),
            ToolParameter(name="xlabel", type="string", description="x 轴标签",
                          required=False, default=""),
            ToolParameter(name="ylabel", type="string", description="y 轴标签",
                          required=False, default="value"),
        ]

    def execute(self, **kwargs) -> ToolResult:
        categories = list(kwargs["categories"])
        values = np.array(kwargs["values"], dtype=float)

        if len(categories) != len(values):
            return ToolResult(success=False, error="categories 和 values 长度不一致",
                              message=f"categories 长度 {len(categories)}, values 长度 {len(values)}")

        fig, ax = plt.subplots(figsize=(8, 5))
        ax.bar(categories, values, color="steelblue", edgecolor="black", alpha=0.8)
        ax.set_title(kwargs.get("title") or "")
        ax.set_xlabel(kwargs.get("xlabel") or "")
        ax.set_ylabel(kwargs.get("ylabel") or "value")
        ax.grid(True, alpha=0.3, axis="y")

        info = self._save_figure(fig, "bar_chart")
        return ToolResult(success=True, data=info,
                          message=f"柱状图已保存到 {info['file_path']}")


class HeatmapTool(_ChartToolBase):
    """热力图工具，绘制二维数据矩阵。"""

    @property
    def name(self) -> str:
        return "heatmap"

    @property
    def description(self) -> str:
        return (
            "绘制热力图，可视化二维数值矩阵。"
            "matrix 是二维数值列表（如相关性矩阵）。"
            "可选参数 row_labels / col_labels 指定行列标签。"
            "图片自动保存到 outputs/ 目录。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="matrix", type="array",
                          description="二维数值矩阵，如 [[1, 0.8], [0.8, 1]]"),
            ToolParameter(name="row_labels", type="array",
                          description="行标签列表，长度需与矩阵行数一致",
                          items_type="string", required=False, default=None),
            ToolParameter(name="col_labels", type="array",
                          description="列标签列表，长度需与矩阵列数一致",
                          items_type="string", required=False, default=None),
            ToolParameter(name="title", type="string", description="图标题",
                          required=False, default=""),
            ToolParameter(name="annotate", type="boolean",
                          description="是否在每个单元格上标注数值，默认 true",
                          required=False, default=True),
            ToolParameter(name="cmap", type="string",
                          description="颜色映射，常用: viridis / coolwarm / RdBu_r / YlOrRd",
                          required=False, default="viridis"),
        ]

    def execute(self, **kwargs) -> ToolResult:
        matrix = np.array(kwargs["matrix"], dtype=float)
        if matrix.ndim != 2:
            return ToolResult(success=False, error="matrix 必须是二维",
                              message=f"实际维度 {matrix.ndim}")

        rows, cols = matrix.shape
        row_labels = kwargs.get("row_labels") or [str(i) for i in range(rows)]
        col_labels = kwargs.get("col_labels") or [str(i) for i in range(cols)]

        if len(row_labels) != rows or len(col_labels) != cols:
            return ToolResult(
                success=False, error="标签长度与矩阵形状不匹配",
                message=f"matrix 形状 {matrix.shape}, row_labels {len(row_labels)}, col_labels {len(col_labels)}",
            )

        fig, ax = plt.subplots(figsize=(max(6, cols * 0.6), max(5, rows * 0.6)))
        im = ax.imshow(matrix, cmap=kwargs.get("cmap", "viridis"), aspect="auto")
        fig.colorbar(im, ax=ax)

        ax.set_xticks(range(cols))
        ax.set_yticks(range(rows))
        ax.set_xticklabels(col_labels, rotation=45, ha="right")
        ax.set_yticklabels(row_labels)

        if kwargs.get("annotate", True):
            mean_val = matrix.mean()
            for i in range(rows):
                for j in range(cols):
                    color = "white" if matrix[i, j] < mean_val else "black"
                    ax.text(j, i, f"{matrix[i, j]:.2f}", ha="center", va="center",
                            color=color, fontsize=9)

        ax.set_title(kwargs.get("title") or "")
        info = self._save_figure(fig, "heatmap")
        return ToolResult(success=True, data=info,
                          message=f"热力图已保存到 {info['file_path']}")
