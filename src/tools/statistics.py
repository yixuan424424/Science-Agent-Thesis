"""统计分析类工具集。"""

import numpy as np
from .base import BaseTool, ToolParameter, ToolResult


class DescriptiveStatsTool(BaseTool):
    """对数据集进行描述性统计分析，返回均值、中位数、标准差等指标。"""

    @property
    def name(self) -> str:
        return "descriptive_statistics"

    @property
    def description(self) -> str:
        return (
            "对一组数值数据进行描述性统计分析。"
            "返回均值、中位数、标准差、最小值、最大值、四分位数等统计指标。"
            "适用于快速了解数据的集中趋势和离散程度。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="data",
                type="array",
                description="待分析的数值数据列表，如 [1.2, 3.4, 5.6, 7.8]",
                items_type="number",
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        data = np.array(kwargs["data"], dtype=float)

        if len(data) == 0:
            return ToolResult(success=False, error="数据为空", message="输入数据不能为空列表")

        stats = {
            "count": len(data),
            "mean": float(np.mean(data)),
            "median": float(np.median(data)),
            "std": float(np.std(data, ddof=1)) if len(data) > 1 else 0.0,
            "variance": float(np.var(data, ddof=1)) if len(data) > 1 else 0.0,
            "min": float(np.min(data)),
            "max": float(np.max(data)),
            "range": float(np.max(data) - np.min(data)),
            "q1": float(np.percentile(data, 25)),
            "q3": float(np.percentile(data, 75)),
        }
        stats["iqr"] = stats["q3"] - stats["q1"]

        message = (
            f"数据共 {stats['count']} 个值，"
            f"均值 {stats['mean']:.4f}，中位数 {stats['median']:.4f}，"
            f"标准差 {stats['std']:.4f}，范围 [{stats['min']:.4f}, {stats['max']:.4f}]"
        )

        return ToolResult(success=True, data=stats, message=message)
