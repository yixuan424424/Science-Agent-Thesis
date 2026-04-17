"""统计工具的单元测试。"""

from src.tools.statistics import DescriptiveStatsTool


class TestDescriptiveStatsTool:
    def setup_method(self):
        self.tool = DescriptiveStatsTool()

    def test_basic_stats(self):
        result = self.tool.run(data=[1, 2, 3, 4, 5])
        assert result.success is True
        assert result.data["count"] == 5
        assert result.data["mean"] == 3.0
        assert result.data["median"] == 3.0
        assert result.data["min"] == 1.0
        assert result.data["max"] == 5.0

    def test_single_value(self):
        result = self.tool.run(data=[42.0])
        assert result.success is True
        assert result.data["mean"] == 42.0
        assert result.data["std"] == 0.0

    def test_empty_data(self):
        result = self.tool.run(data=[])
        assert result.success is False

    def test_missing_param(self):
        result = self.tool.run()
        assert result.success is False
        assert "缺少必需参数" in result.error

    def test_openai_schema(self):
        schema = self.tool.to_openai_schema()
        assert schema["type"] == "function"
        assert schema["function"]["name"] == "descriptive_statistics"
        assert "data" in schema["function"]["parameters"]["properties"]
