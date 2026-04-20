"""统计分析类工具集。"""

import numpy as np
from scipy import stats

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

        result = {
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
        result["iqr"] = result["q3"] - result["q1"]

        message = (
            f"数据共 {result['count']} 个值，"
            f"均值 {result['mean']:.4f}，中位数 {result['median']:.4f}，"
            f"标准差 {result['std']:.4f}，范围 [{result['min']:.4f}, {result['max']:.4f}]"
        )

        return ToolResult(success=True, data=result, message=message)


class HypothesisTestTool(BaseTool):
    """t 检验工具，支持单样本、双样本（独立）、配对三种类型。"""

    @property
    def name(self) -> str:
        return "hypothesis_test"

    @property
    def description(self) -> str:
        return (
            "执行 t 检验。支持三种类型: "
            "one_sample (单样本 t 检验，比较 sample_a 的均值与 mu0), "
            "two_sample (独立双样本 t 检验，比较 sample_a 和 sample_b 的均值), "
            "paired (配对样本 t 检验，比较 sample_a 和 sample_b 的差值)。"
            "返回 t 统计量、p 值，以及在显著性水平 alpha (默认 0.05) 下是否拒绝原假设。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="test_type", type="string", description="检验类型",
                          enum=["one_sample", "two_sample", "paired"]),
            ToolParameter(name="sample_a", type="array",
                          description="第一个样本数据列表", items_type="number"),
            ToolParameter(name="sample_b", type="array",
                          description="第二个样本数据列表（two_sample/paired 时必需）",
                          items_type="number", required=False, default=None),
            ToolParameter(name="mu0", type="number",
                          description="原假设的总体均值（仅 one_sample 时使用），默认 0",
                          required=False, default=0.0),
            ToolParameter(name="alpha", type="number",
                          description="显著性水平，默认 0.05",
                          required=False, default=0.05, minimum=0.0, maximum=1.0),
        ]

    def execute(self, **kwargs) -> ToolResult:
        test_type = kwargs["test_type"]
        a = np.array(kwargs["sample_a"], dtype=float)
        alpha = float(kwargs.get("alpha", 0.05))

        if test_type == "one_sample":
            mu0 = float(kwargs.get("mu0", 0.0))
            t, p = stats.ttest_1samp(a, mu0)
            description = f"单样本 t 检验 (H0: μ = {mu0})"

        elif test_type in ("two_sample", "paired"):
            if kwargs.get("sample_b") is None:
                return ToolResult(success=False, error="缺少 sample_b",
                                  message=f"{test_type} 检验需要两个样本")
            b = np.array(kwargs["sample_b"], dtype=float)
            if test_type == "two_sample":
                t, p = stats.ttest_ind(a, b)
                description = "独立双样本 t 检验 (H0: μ_a = μ_b)"
            else:
                if len(a) != len(b):
                    return ToolResult(success=False, error="配对样本长度不一致",
                                      message=f"sample_a 长度 {len(a)}, sample_b 长度 {len(b)}")
                t, p = stats.ttest_rel(a, b)
                description = "配对 t 检验 (H0: 差值均值 = 0)"
        else:
            return ToolResult(success=False, error=f"未知检验类型: {test_type}")

        reject = bool(p < alpha)
        conclusion = "拒绝原假设（差异显著）" if reject else "不拒绝原假设（差异不显著）"

        return ToolResult(
            success=True,
            data={
                "test_type": test_type,
                "t_statistic": float(t),
                "p_value": float(p),
                "alpha": alpha,
                "reject_null": reject,
            },
            message=f"{description}: t = {t:.4f}, p = {p:.4f}, α = {alpha}, 结论: {conclusion}",
        )


class RegressionTool(BaseTool):
    """简单线性回归工具，返回斜率、截距、R²、p 值。"""

    @property
    def name(self) -> str:
        return "linear_regression"

    @property
    def description(self) -> str:
        return (
            "对两个变量 x 和 y 进行简单线性回归分析。"
            "返回回归方程的斜率、截距、决定系数 R²、斜率显著性 p 值和回归标准误。"
            "适用于分析两变量间的线性关系强度与统计显著性。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="x", type="array",
                          description="自变量数据列表", items_type="number"),
            ToolParameter(name="y", type="array",
                          description="因变量数据列表", items_type="number"),
        ]

    def execute(self, **kwargs) -> ToolResult:
        x = np.array(kwargs["x"], dtype=float)
        y = np.array(kwargs["y"], dtype=float)

        if len(x) != len(y):
            return ToolResult(success=False, error="x 和 y 长度不一致",
                              message=f"x 长度 {len(x)}, y 长度 {len(y)}")
        if len(x) < 3:
            return ToolResult(success=False, error="数据点不足", message="线性回归至少需要 3 个数据点")

        result = stats.linregress(x, y)
        formula = f"y = {result.slope:.4f}*x + {result.intercept:.4f}"

        return ToolResult(
            success=True,
            data={
                "slope": float(result.slope),
                "intercept": float(result.intercept),
                "r_squared": float(result.rvalue ** 2),
                "p_value": float(result.pvalue),
                "std_err": float(result.stderr),
                "formula": formula,
            },
            message=(
                f"{formula}，R² = {result.rvalue**2:.4f}，"
                f"斜率 p 值 = {result.pvalue:.4g}"
            ),
        )


class CorrelationTool(BaseTool):
    """两个变量的相关性分析，支持 Pearson 和 Spearman 两种方法。"""

    @property
    def name(self) -> str:
        return "correlation_analysis"

    @property
    def description(self) -> str:
        return (
            "计算两个变量的相关系数。支持的方法: "
            "pearson (皮尔逊相关，衡量线性相关性), "
            "spearman (斯皮尔曼秩相关，衡量单调相关性，对异常值更稳健)。"
            "返回相关系数 r 和显著性 p 值。"
            "|r| < 0.3 弱相关, 0.3 ≤ |r| < 0.7 中等相关, |r| ≥ 0.7 强相关。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="x", type="array",
                          description="第一个变量数据列表", items_type="number"),
            ToolParameter(name="y", type="array",
                          description="第二个变量数据列表", items_type="number"),
            ToolParameter(name="method", type="string",
                          description="相关性计算方法，默认 pearson",
                          required=False, default="pearson",
                          enum=["pearson", "spearman"]),
        ]

    def execute(self, **kwargs) -> ToolResult:
        x = np.array(kwargs["x"], dtype=float)
        y = np.array(kwargs["y"], dtype=float)
        method = kwargs.get("method", "pearson")

        if len(x) != len(y):
            return ToolResult(success=False, error="x 和 y 长度不一致",
                              message=f"x 长度 {len(x)}, y 长度 {len(y)}")
        if len(x) < 3:
            return ToolResult(success=False, error="数据点不足", message="相关性分析至少需要 3 个数据点")

        if method == "pearson":
            r, p = stats.pearsonr(x, y)
        else:
            r, p = stats.spearmanr(x, y)

        abs_r = abs(r)
        if abs_r < 0.3:
            strength = "弱相关"
        elif abs_r < 0.7:
            strength = "中等相关"
        else:
            strength = "强相关"
        direction = "正" if r > 0 else "负"

        return ToolResult(
            success=True,
            data={
                "method": method,
                "correlation": float(r),
                "p_value": float(p),
                "strength": strength,
                "direction": direction,
            },
            message=(
                f"{method} 相关系数 r = {r:.4f} ({direction}{strength}), "
                f"p 值 = {p:.4g}"
            ),
        )
