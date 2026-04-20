"""科学工具库统一入口。

通过 ALL_TOOLS 列表暴露所有工具，便于 Agent 框架批量注册。
"""

from .base import BaseTool, ToolParameter, ToolResult

from .numerical import (
    MatrixOperationTool,
    NumericalIntegrationTool,
    CurveFittingTool,
    EquationSolverTool,
)
from .statistics import (
    DescriptiveStatsTool,
    HypothesisTestTool,
    RegressionTool,
    CorrelationTool,
)
from .visualization import (
    LineChartTool,
    ScatterChartTool,
    BarChartTool,
    HeatmapTool,
)


ALL_TOOL_CLASSES: list[type[BaseTool]] = [
    MatrixOperationTool,
    NumericalIntegrationTool,
    CurveFittingTool,
    EquationSolverTool,
    DescriptiveStatsTool,
    HypothesisTestTool,
    RegressionTool,
    CorrelationTool,
    LineChartTool,
    ScatterChartTool,
    BarChartTool,
    HeatmapTool,
]


def build_all_tools() -> list[BaseTool]:
    """实例化所有工具，返回工具实例列表。"""
    return [cls() for cls in ALL_TOOL_CLASSES]


__all__ = [
    "BaseTool", "ToolParameter", "ToolResult",
    "MatrixOperationTool", "NumericalIntegrationTool", "CurveFittingTool", "EquationSolverTool",
    "DescriptiveStatsTool", "HypothesisTestTool", "RegressionTool", "CorrelationTool",
    "LineChartTool", "ScatterChartTool", "BarChartTool", "HeatmapTool",
    "ALL_TOOL_CLASSES", "build_all_tools",
]
