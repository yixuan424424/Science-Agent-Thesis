"""可视化工具的单元测试。

可视化的"正确性"难以自动断言（图形是否好看），所以我们只验证：
- 调用成功
- 文件被生成且非空
- 返回的元信息合理
"""

import os

from src.tools.visualization import (
    LineChartTool, ScatterChartTool, BarChartTool, HeatmapTool,
)


def _assert_file_ok(result):
    assert result.success, result.error
    path = result.data["file_path"]
    assert os.path.exists(path), f"文件未生成: {path}"
    assert os.path.getsize(path) > 0, f"文件大小为 0: {path}"


class TestLineChartTool:
    def setup_method(self):
        self.tool = LineChartTool()

    def test_single_series(self):
        result = self.tool.run(x=[1, 2, 3, 4], y=[1, 4, 9, 16], title="quadratic")
        _assert_file_ok(result)

    def test_multi_series(self):
        result = self.tool.run(
            x=[1, 2, 3, 4],
            y=[[1, 2, 3, 4], [4, 3, 2, 1]],
            series_labels=["asc", "desc"],
        )
        _assert_file_ok(result)


class TestScatterChartTool:
    def setup_method(self):
        self.tool = ScatterChartTool()

    def test_basic(self):
        result = self.tool.run(x=[1, 2, 3, 4, 5], y=[2, 4, 5, 4, 5])
        _assert_file_ok(result)

    def test_with_fit_line(self):
        result = self.tool.run(
            x=[1, 2, 3, 4, 5], y=[2, 4, 6, 8, 10], fit_line=True,
        )
        _assert_file_ok(result)

    def test_length_mismatch(self):
        result = self.tool.run(x=[1, 2, 3], y=[1, 2])
        assert not result.success


class TestBarChartTool:
    def setup_method(self):
        self.tool = BarChartTool()

    def test_basic(self):
        result = self.tool.run(
            categories=["A", "B", "C", "D"],
            values=[10, 25, 15, 30],
            title="bar demo",
        )
        _assert_file_ok(result)

    def test_length_mismatch(self):
        result = self.tool.run(categories=["A", "B"], values=[1, 2, 3])
        assert not result.success


class TestHeatmapTool:
    def setup_method(self):
        self.tool = HeatmapTool()

    def test_basic(self):
        result = self.tool.run(matrix=[[1.0, 0.8, 0.3], [0.8, 1.0, 0.5], [0.3, 0.5, 1.0]])
        _assert_file_ok(result)

    def test_with_labels(self):
        result = self.tool.run(
            matrix=[[1.0, 0.8], [0.8, 1.0]],
            row_labels=["x", "y"],
            col_labels=["x", "y"],
            title="correlation matrix",
        )
        _assert_file_ok(result)

    def test_label_length_mismatch(self):
        result = self.tool.run(
            matrix=[[1, 2], [3, 4]],
            row_labels=["a", "b", "c"],
        )
        assert not result.success
