"""数值计算工具的单元测试。"""

import math
import pytest

from src.tools.numerical import (
    MatrixOperationTool,
    NumericalIntegrationTool,
    CurveFittingTool,
    EquationSolverTool,
)


class TestMatrixOperationTool:
    def setup_method(self):
        self.tool = MatrixOperationTool()

    def test_add(self):
        result = self.tool.run(
            operation="add",
            matrix_a=[[1, 2], [3, 4]],
            matrix_b=[[5, 6], [7, 8]],
        )
        assert result.success
        assert result.data["result"] == [[6, 8], [10, 12]]

    def test_multiply(self):
        result = self.tool.run(
            operation="multiply",
            matrix_a=[[1, 2], [3, 4]],
            matrix_b=[[5, 6], [7, 8]],
        )
        assert result.success
        # [[1*5+2*7, 1*6+2*8], [3*5+4*7, 3*6+4*8]] = [[19,22],[43,50]]
        assert result.data["result"] == [[19, 22], [43, 50]]

    def test_transpose(self):
        result = self.tool.run(operation="transpose", matrix_a=[[1, 2, 3], [4, 5, 6]])
        assert result.success
        assert result.data["result"] == [[1, 4], [2, 5], [3, 6]]

    def test_inverse_identity(self):
        result = self.tool.run(operation="inverse", matrix_a=[[1, 0], [0, 1]])
        assert result.success
        assert result.data["result"] == [[1.0, 0.0], [0.0, 1.0]]

    def test_determinant(self):
        result = self.tool.run(operation="determinant", matrix_a=[[1, 2], [3, 4]])
        assert result.success
        assert math.isclose(result.data["determinant"], -2.0, abs_tol=1e-9)

    def test_eigenvalues_diagonal(self):
        result = self.tool.run(operation="eigenvalues", matrix_a=[[3, 0], [0, 5]])
        assert result.success
        assert sorted(result.data["real"]) == [3.0, 5.0]

    def test_inverse_non_square_fails(self):
        result = self.tool.run(operation="inverse", matrix_a=[[1, 2, 3], [4, 5, 6]])
        assert not result.success

    def test_missing_matrix_b_for_binary_op(self):
        result = self.tool.run(operation="add", matrix_a=[[1, 2], [3, 4]])
        assert not result.success


class TestNumericalIntegrationTool:
    def setup_method(self):
        self.tool = NumericalIntegrationTool()

    def test_polynomial(self):
        # ∫[0,1] x^2 dx = 1/3
        result = self.tool.run(expression="x**2", lower=0, upper=1)
        assert result.success
        assert math.isclose(result.data["integral"], 1 / 3, abs_tol=1e-6)

    def test_sin(self):
        # ∫[0, pi] sin(x) dx = 2
        result = self.tool.run(expression="sin(x)", lower=0, upper=math.pi)
        assert result.success
        assert math.isclose(result.data["integral"], 2.0, abs_tol=1e-6)

    def test_constant(self):
        # ∫[2, 5] 3 dx = 9
        result = self.tool.run(expression="3", lower=2, upper=5)
        assert result.success
        assert math.isclose(result.data["integral"], 9.0, abs_tol=1e-9)

    def test_unsafe_expression_rejected(self):
        result = self.tool.run(expression="__import__('os').system('echo hi')",
                               lower=0, upper=1)
        assert not result.success


class TestCurveFittingTool:
    def setup_method(self):
        self.tool = CurveFittingTool()

    def test_linear_perfect(self):
        x = [1, 2, 3, 4, 5]
        y = [3, 5, 7, 9, 11]  # y = 2x + 1
        result = self.tool.run(x=x, y=y, model="linear")
        assert result.success
        assert math.isclose(result.data["params"]["slope"], 2.0, abs_tol=1e-6)
        assert math.isclose(result.data["params"]["intercept"], 1.0, abs_tol=1e-6)
        assert math.isclose(result.data["r_squared"], 1.0, abs_tol=1e-9)

    def test_polynomial_quadratic(self):
        x = [-2, -1, 0, 1, 2]
        y = [4, 1, 0, 1, 4]  # y = x^2
        result = self.tool.run(x=x, y=y, model="polynomial", degree=2)
        assert result.success
        assert math.isclose(result.data["r_squared"], 1.0, abs_tol=1e-9)

    def test_length_mismatch(self):
        result = self.tool.run(x=[1, 2, 3], y=[1, 2], model="linear")
        assert not result.success


class TestEquationSolverTool:
    def setup_method(self):
        self.tool = EquationSolverTool()

    def test_simple_root(self):
        # x^2 - 4 = 0 在 [0, 3] 的根是 2
        result = self.tool.run(expression="x**2 - 4", lower=0, upper=3)
        assert result.success
        assert math.isclose(result.data["root"], 2.0, abs_tol=1e-6)

    def test_cubic(self):
        # x^3 - 8 = 0 在 [0, 4] 的根是 2
        result = self.tool.run(expression="x**3 - 8", lower=0, upper=4)
        assert result.success
        assert math.isclose(result.data["root"], 2.0, abs_tol=1e-6)

    def test_same_sign_endpoints(self):
        # x^2 + 1 = 0 在实数域无解，端点同号
        result = self.tool.run(expression="x**2 + 1", lower=-1, upper=1)
        assert not result.success
