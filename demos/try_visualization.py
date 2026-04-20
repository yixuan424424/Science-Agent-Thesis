"""可视化工具 demo 脚本：直接运行可生成 4 张示例图到 outputs/ 目录。

用法:
    python -m demos.try_visualization
"""

import math

from src.tools.visualization import (
    LineChartTool, ScatterChartTool, BarChartTool, HeatmapTool,
)


def demo_line_chart():
    print("\n[1/4] 折线图示例：sin(x) 与 cos(x)")
    x = [i * math.pi / 20 for i in range(41)]
    sin_y = [math.sin(v) for v in x]
    cos_y = [math.cos(v) for v in x]
    result = LineChartTool().run(
        x=x, y=[sin_y, cos_y],
        title="Sine and Cosine",
        xlabel="x (radians)", ylabel="value",
        series_labels=["sin(x)", "cos(x)"],
    )
    print(f"  -> {result.message}")


def demo_scatter_chart():
    print("\n[2/4] 散点图示例：带拟合线")
    x = list(range(20))
    y = [2 * v + 1 + (v % 3 - 1) * 1.5 for v in x]
    result = ScatterChartTool().run(
        x=x, y=y, title="Scatter with linear fit",
        xlabel="x", ylabel="y", fit_line=True,
    )
    print(f"  -> {result.message}")


def demo_bar_chart():
    print("\n[3/4] 柱状图示例：四组实验结果")
    result = BarChartTool().run(
        categories=["Group A", "Group B", "Group C", "Group D"],
        values=[23.4, 17.8, 31.2, 26.5],
        title="Experiment results", ylabel="score",
    )
    print(f"  -> {result.message}")


def demo_heatmap():
    print("\n[4/4] 热力图示例：相关性矩阵")
    matrix = [
        [1.00, 0.85, 0.42, -0.10],
        [0.85, 1.00, 0.51, -0.05],
        [0.42, 0.51, 1.00, 0.30],
        [-0.10, -0.05, 0.30, 1.00],
    ]
    labels = ["temp", "humidity", "pressure", "wind"]
    result = HeatmapTool().run(
        matrix=matrix, row_labels=labels, col_labels=labels,
        title="Variable correlation matrix", cmap="coolwarm",
    )
    print(f"  -> {result.message}")


if __name__ == "__main__":
    demo_line_chart()
    demo_scatter_chart()
    demo_bar_chart()
    demo_heatmap()
    print("\n全部 demo 完成，请到 outputs/ 目录查看生成的图片。")
