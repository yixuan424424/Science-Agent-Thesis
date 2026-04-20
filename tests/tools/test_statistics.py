"""统计分析工具的单元测试。"""

import math

from src.tools.statistics import (
    DescriptiveStatsTool,
    HypothesisTestTool,
    RegressionTool,
    CorrelationTool,
)


class TestDescriptiveStatsTool:
    def setup_method(self):
        self.tool = DescriptiveStatsTool()

    def test_basic_stats(self):
        result = self.tool.run(data=[1, 2, 3, 4, 5])
        assert result.success
        assert result.data["count"] == 5
        assert result.data["mean"] == 3.0
        assert result.data["median"] == 3.0
        assert result.data["min"] == 1.0
        assert result.data["max"] == 5.0

    def test_single_value(self):
        result = self.tool.run(data=[42.0])
        assert result.success
        assert result.data["mean"] == 42.0
        assert result.data["std"] == 0.0

    def test_empty_data(self):
        result = self.tool.run(data=[])
        assert not result.success

    def test_missing_param(self):
        result = self.tool.run()
        assert not result.success
        assert "缺少必需参数" in result.error

    def test_openai_schema(self):
        schema = self.tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "descriptive_statistics"
        assert "data" in schema["function"]["parameters"]["properties"]


class TestHypothesisTestTool:
    def setup_method(self):
        self.tool = HypothesisTestTool()

    def test_one_sample_no_difference(self):
        # 数据均值接近 0，期望不拒绝 H0: μ=0
        result = self.tool.run(test_type="one_sample",
                               sample_a=[-1, 0, 1, -1, 0, 1], mu0=0)
        assert result.success
        assert not result.data["reject_null"]

    def test_one_sample_significant(self):
        # 数据均值远离 0，期望拒绝 H0: μ=0
        result = self.tool.run(test_type="one_sample",
                               sample_a=[10, 11, 12, 10, 11, 12], mu0=0)
        assert result.success
        assert result.data["reject_null"]

    def test_two_sample_significant(self):
        result = self.tool.run(
            test_type="two_sample",
            sample_a=[1, 2, 3, 2, 1, 2],
            sample_b=[10, 11, 12, 11, 10, 11],
        )
        assert result.success
        assert result.data["reject_null"]

    def test_paired_length_mismatch(self):
        result = self.tool.run(test_type="paired",
                               sample_a=[1, 2, 3], sample_b=[1, 2])
        assert not result.success

    def test_two_sample_missing_b(self):
        result = self.tool.run(test_type="two_sample", sample_a=[1, 2, 3])
        assert not result.success


class TestRegressionTool:
    def setup_method(self):
        self.tool = RegressionTool()

    def test_perfect_linear(self):
        x = [1, 2, 3, 4, 5]
        y = [2, 4, 6, 8, 10]  # y = 2x
        result = self.tool.run(x=x, y=y)
        assert result.success
        assert math.isclose(result.data["slope"], 2.0, abs_tol=1e-9)
        assert math.isclose(result.data["intercept"], 0.0, abs_tol=1e-9)
        assert math.isclose(result.data["r_squared"], 1.0, abs_tol=1e-9)

    def test_length_mismatch(self):
        result = self.tool.run(x=[1, 2, 3], y=[1, 2])
        assert not result.success

    def test_too_few_points(self):
        result = self.tool.run(x=[1, 2], y=[1, 2])
        assert not result.success


class TestCorrelationTool:
    def setup_method(self):
        self.tool = CorrelationTool()

    def test_perfect_positive(self):
        result = self.tool.run(x=[1, 2, 3, 4, 5], y=[2, 4, 6, 8, 10], method="pearson")
        assert result.success
        assert math.isclose(result.data["correlation"], 1.0, abs_tol=1e-9)
        assert result.data["strength"] == "强相关"
        assert result.data["direction"] == "正"

    def test_perfect_negative(self):
        result = self.tool.run(x=[1, 2, 3, 4, 5], y=[10, 8, 6, 4, 2], method="pearson")
        assert result.success
        assert math.isclose(result.data["correlation"], -1.0, abs_tol=1e-9)
        assert result.data["direction"] == "负"

    def test_spearman(self):
        # 单调但非线性的关系，spearman 应为 1
        result = self.tool.run(x=[1, 2, 3, 4, 5], y=[1, 4, 9, 16, 25], method="spearman")
        assert result.success
        assert math.isclose(result.data["correlation"], 1.0, abs_tol=1e-9)

    def test_length_mismatch(self):
        result = self.tool.run(x=[1, 2, 3], y=[1, 2])
        assert not result.success
