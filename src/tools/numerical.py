"""数值计算类工具集，基于 NumPy 和 SciPy。"""

import numpy as np
from scipy import integrate, optimize

from .base import BaseTool, ToolParameter, ToolResult
from ._expr import make_function


class MatrixOperationTool(BaseTool):
    """矩阵基础运算：加法、减法、乘法、转置、求逆、行列式、特征值。"""

    @property
    def name(self) -> str:
        return "matrix_operation"

    @property
    def description(self) -> str:
        return (
            "对矩阵进行常见线性代数运算。"
            "支持的操作: add(加法), subtract(减法), multiply(矩阵乘法), "
            "transpose(转置), inverse(求逆), determinant(行列式), eigenvalues(特征值)。"
            "对于双目运算（add/subtract/multiply）需要提供 matrix_a 和 matrix_b，"
            "对于单目运算只需提供 matrix_a。矩阵以二维列表形式传入，如 [[1,2],[3,4]]。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(
                name="operation", type="string",
                description="运算类型",
                enum=["add", "subtract", "multiply", "transpose", "inverse", "determinant", "eigenvalues"],
            ),
            ToolParameter(
                name="matrix_a", type="array",
                description="第一个矩阵（必需），二维数值列表",
            ),
            ToolParameter(
                name="matrix_b", type="array",
                description="第二个矩阵（仅 add/subtract/multiply 需要），二维数值列表",
                required=False, default=None,
            ),
        ]

    def execute(self, **kwargs) -> ToolResult:
        op = kwargs["operation"]
        a = np.array(kwargs["matrix_a"], dtype=float)

        binary_ops = {"add", "subtract", "multiply"}
        if op in binary_ops:
            if kwargs.get("matrix_b") is None:
                return ToolResult(success=False, error="缺少 matrix_b", message=f"{op} 操作需要两个矩阵")
            b = np.array(kwargs["matrix_b"], dtype=float)
            if op == "add":
                result = a + b
            elif op == "subtract":
                result = a - b
            else:
                result = a @ b
            return ToolResult(
                success=True, data={"result": result.tolist(), "shape": list(result.shape)},
                message=f"{op} 运算完成，结果矩阵形状 {result.shape}",
            )

        if op == "transpose":
            result = a.T
            return ToolResult(
                success=True, data={"result": result.tolist(), "shape": list(result.shape)},
                message=f"转置完成，原形状 {a.shape} -> {result.shape}",
            )

        if op == "inverse":
            if a.shape[0] != a.shape[1]:
                return ToolResult(success=False, error="非方阵无法求逆", message=f"矩阵形状 {a.shape} 不是方阵")
            result = np.linalg.inv(a)
            return ToolResult(
                success=True, data={"result": result.tolist(), "shape": list(result.shape)},
                message=f"求逆完成，矩阵形状 {result.shape}",
            )

        if op == "determinant":
            if a.shape[0] != a.shape[1]:
                return ToolResult(success=False, error="非方阵无行列式", message=f"矩阵形状 {a.shape} 不是方阵")
            det = float(np.linalg.det(a))
            return ToolResult(success=True, data={"determinant": det}, message=f"行列式 = {det:.6f}")

        if op == "eigenvalues":
            if a.shape[0] != a.shape[1]:
                return ToolResult(success=False, error="非方阵无特征值", message=f"矩阵形状 {a.shape} 不是方阵")
            vals = np.linalg.eigvals(a)
            real_vals = [float(v.real) for v in vals]
            imag_vals = [float(v.imag) for v in vals]
            return ToolResult(
                success=True,
                data={"real": real_vals, "imag": imag_vals},
                message=f"特征值（实部）: {[round(v, 4) for v in real_vals]}",
            )

        return ToolResult(success=False, error=f"未知操作: {op}")


class NumericalIntegrationTool(BaseTool):
    """对一维函数 f(x) 在区间 [a, b] 上做数值积分。"""

    @property
    def name(self) -> str:
        return "numerical_integration"

    @property
    def description(self) -> str:
        return (
            "对一维函数在指定区间上进行数值积分。"
            "函数以字符串表达式形式给出，自变量必须为 x，"
            "可使用的数学函数: sin, cos, tan, exp, log, sqrt 等，常量: pi, e。"
            "示例表达式: 'x**2 + 2*x + 1', 'sin(x)*exp(-x)', '1/(1+x**2)'。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="expression", type="string",
                          description="被积函数表达式，自变量为 x，如 'x**2 + sin(x)'"),
            ToolParameter(name="lower", type="number", description="积分下限 a"),
            ToolParameter(name="upper", type="number", description="积分上限 b"),
        ]

    def execute(self, **kwargs) -> ToolResult:
        expr = kwargs["expression"]
        a = float(kwargs["lower"])
        b = float(kwargs["upper"])

        try:
            f = make_function(expr, ["x"])
        except (ValueError, SyntaxError) as e:
            return ToolResult(success=False, error=str(e), message=f"表达式解析失败: {e}")

        value, abs_err = integrate.quad(f, a, b)
        return ToolResult(
            success=True,
            data={"integral": float(value), "absolute_error": float(abs_err),
                  "expression": expr, "interval": [a, b]},
            message=f"积分 ∫[{a},{b}] {expr} dx = {value:.6f} (误差估计 {abs_err:.2e})",
        )


class CurveFittingTool(BaseTool):
    """函数拟合：给定一组 (x, y) 数据点和模型类型，返回拟合参数与 R²。"""

    @property
    def name(self) -> str:
        return "curve_fitting"

    @property
    def description(self) -> str:
        return (
            "对一组数据点 (x, y) 进行曲线拟合。支持的模型: "
            "linear (线性 y=a*x+b), "
            "polynomial (多项式 y=∑c_i*x^i, 通过 degree 指定阶数), "
            "exponential (指数 y=a*exp(b*x))。"
            "返回拟合参数和决定系数 R²。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="x", type="array", description="x 坐标数据列表", items_type="number"),
            ToolParameter(name="y", type="array", description="y 坐标数据列表", items_type="number"),
            ToolParameter(name="model", type="string", description="拟合模型类型",
                          enum=["linear", "polynomial", "exponential"]),
            ToolParameter(name="degree", type="number",
                          description="多项式阶数（仅 polynomial 时使用），默认 2",
                          required=False, default=2, minimum=1, maximum=10),
        ]

    def execute(self, **kwargs) -> ToolResult:
        x = np.array(kwargs["x"], dtype=float)
        y = np.array(kwargs["y"], dtype=float)
        model = kwargs["model"]

        if len(x) != len(y):
            return ToolResult(success=False, error="x 和 y 长度不一致",
                              message=f"x 长度 {len(x)}, y 长度 {len(y)}")
        if len(x) < 2:
            return ToolResult(success=False, error="数据点不足", message="至少需要 2 个数据点")

        if model == "linear":
            coef = np.polyfit(x, y, 1)
            y_pred = np.polyval(coef, x)
            params = {"slope": float(coef[0]), "intercept": float(coef[1])}
            formula = f"y = {coef[0]:.4f}*x + {coef[1]:.4f}"

        elif model == "polynomial":
            degree = int(kwargs.get("degree", 2))
            coef = np.polyfit(x, y, degree)
            y_pred = np.polyval(coef, x)
            params = {"coefficients": coef.tolist(), "degree": degree}
            terms = [f"{c:.4f}*x^{degree - i}" for i, c in enumerate(coef)]
            formula = "y = " + " + ".join(terms)

        elif model == "exponential":
            try:
                popt, _ = optimize.curve_fit(lambda x, a, b: a * np.exp(b * x), x, y, p0=[1.0, 0.1])
            except Exception as e:
                return ToolResult(success=False, error=str(e), message=f"指数拟合失败: {e}")
            y_pred = popt[0] * np.exp(popt[1] * x)
            params = {"a": float(popt[0]), "b": float(popt[1])}
            formula = f"y = {popt[0]:.4f}*exp({popt[1]:.4f}*x)"
        else:
            return ToolResult(success=False, error=f"未知模型: {model}")

        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r_squared = 1 - ss_res / ss_tot if ss_tot > 0 else 1.0

        return ToolResult(
            success=True,
            data={"model": model, "params": params, "r_squared": float(r_squared), "formula": formula},
            message=f"{formula}，R² = {r_squared:.4f}",
        )


class EquationSolverTool(BaseTool):
    """求解非线性方程 f(x) = 0 的根。"""

    @property
    def name(self) -> str:
        return "equation_solver"

    @property
    def description(self) -> str:
        return (
            "求解一元非线性方程 f(x) = 0 的根。"
            "提供方程左侧表达式（自变量 x）和搜索区间 [lower, upper]，"
            "要求 f(lower) 和 f(upper) 异号（符号相反）。"
            "适合求形如 'x**3 - 2*x - 5 = 0' 的方程。"
        )

    @property
    def parameters(self) -> list[ToolParameter]:
        return [
            ToolParameter(name="expression", type="string",
                          description="方程左侧 f(x) 的表达式，使方程形如 f(x) = 0，例如 'x**3 - 2*x - 5'"),
            ToolParameter(name="lower", type="number", description="搜索区间下界"),
            ToolParameter(name="upper", type="number", description="搜索区间上界"),
        ]

    def execute(self, **kwargs) -> ToolResult:
        expr = kwargs["expression"]
        a = float(kwargs["lower"])
        b = float(kwargs["upper"])

        try:
            f = make_function(expr, ["x"])
        except (ValueError, SyntaxError) as e:
            return ToolResult(success=False, error=str(e), message=f"表达式解析失败: {e}")

        fa, fb = f(a), f(b)
        if fa * fb > 0:
            return ToolResult(
                success=False,
                error="区间端点函数值同号",
                message=f"f({a})={fa:.4f}, f({b})={fb:.4f} 同号，无法保证区间内有根，请调整区间",
            )

        root = optimize.brentq(f, a, b)
        residual = float(f(root))
        return ToolResult(
            success=True,
            data={"root": float(root), "residual": residual, "expression": expr, "interval": [a, b]},
            message=f"方程 {expr} = 0 在 [{a},{b}] 内的根为 x = {root:.6f} (残差 {residual:.2e})",
        )
