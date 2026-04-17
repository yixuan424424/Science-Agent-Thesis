"""
科学工具抽象基类。

所有科学计算工具都继承自 BaseTool，遵循统一的接口规范：
- name / description / parameters：工具的元信息，用于生成 LLM 的 function schema
- execute()：实际执行逻辑，由子类实现
- to_openai_schema()：将工具描述转为 OpenAI Function Calling 格式
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ToolParameter:
    """工具参数的描述信息，用于生成 JSON Schema。"""

    name: str
    type: str  # "number", "string", "array", "boolean", "object"
    description: str
    required: bool = True
    default: Any = None
    # 用于 array 类型，描述元素类型
    items_type: str | None = None
    # 用于 number 类型的范围约束
    minimum: float | None = None
    maximum: float | None = None
    # 用于 string 类型的枚举约束
    enum: list[str] | None = None


@dataclass
class ToolResult:
    """工具执行结果的统一封装。

    Attributes:
        success: 是否执行成功
        data: 执行成功时的结果数据（数值、字典、列表等）
        error: 执行失败时的错误信息
        message: 面向用户的可读描述
    """

    success: bool
    data: Any = None
    error: str | None = None
    message: str = ""

    def to_dict(self) -> dict:
        result = {"success": self.success, "message": self.message}
        if self.success:
            result["data"] = self._serialize(self.data)
        else:
            result["error"] = self.error
        return result

    @staticmethod
    def _serialize(obj: Any) -> Any:
        """将 numpy 等特殊类型转为 JSON 可序列化的 Python 原生类型。"""
        try:
            import numpy as np

            if isinstance(obj, np.ndarray):
                return obj.tolist()
            if isinstance(obj, (np.integer,)):
                return int(obj)
            if isinstance(obj, (np.floating,)):
                return float(obj)
        except ImportError:
            pass

        if isinstance(obj, dict):
            return {k: ToolResult._serialize(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [ToolResult._serialize(item) for item in obj]
        return obj


class BaseTool(ABC):
    """所有科学工具的抽象基类。

    子类需要实现：
    - name: 工具名称（英文，用于 function calling）
    - description: 工具功能描述（中文，用于 LLM 理解工具用途）
    - parameters: 参数列表
    - execute(**kwargs) -> ToolResult: 实际执行逻辑
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """工具名称，英文标识符，如 'linear_regression'。"""
        ...

    @property
    @abstractmethod
    def description(self) -> str:
        """工具功能描述，供 LLM 理解工具用途。"""
        ...

    @property
    @abstractmethod
    def parameters(self) -> list[ToolParameter]:
        """工具接受的参数列表。"""
        ...

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """执行工具逻辑。子类必须实现此方法。"""
        ...

    def validate_params(self, **kwargs) -> str | None:
        """校验参数合法性。返回 None 表示通过，否则返回错误描述。"""
        for param in self.parameters:
            value = kwargs.get(param.name)

            if param.required and value is None and param.default is None:
                return f"缺少必需参数: {param.name}"

            if value is None:
                continue

            if param.type == "number" and not isinstance(value, (int, float)):
                return f"参数 {param.name} 应为数值类型，实际为 {type(value).__name__}"

            if param.type == "string" and not isinstance(value, str):
                return f"参数 {param.name} 应为字符串类型，实际为 {type(value).__name__}"

            if param.type == "array" and not isinstance(value, (list, tuple)):
                return f"参数 {param.name} 应为数组类型，实际为 {type(value).__name__}"

            if param.type == "boolean" and not isinstance(value, bool):
                return f"参数 {param.name} 应为布尔类型，实际为 {type(value).__name__}"

            if param.minimum is not None and isinstance(value, (int, float)):
                if value < param.minimum:
                    return f"参数 {param.name} 的值 {value} 小于最小值 {param.minimum}"

            if param.maximum is not None and isinstance(value, (int, float)):
                if value > param.maximum:
                    return f"参数 {param.name} 的值 {value} 大于最大值 {param.maximum}"

            if param.enum is not None and value not in param.enum:
                return f"参数 {param.name} 的值 {value} 不在允许范围 {param.enum} 内"

        return None

    def run(self, **kwargs) -> ToolResult:
        """对外暴露的执行入口：先校验参数，再执行。"""
        # 填充默认值
        for param in self.parameters:
            if param.name not in kwargs and param.default is not None:
                kwargs[param.name] = param.default

        error = self.validate_params(**kwargs)
        if error:
            return ToolResult(success=False, error=error, message=f"参数校验失败: {error}")

        try:
            return self.execute(**kwargs)
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"{type(e).__name__}: {e}",
                message=f"工具 {self.name} 执行异常: {e}",
            )

    def to_openai_schema(self) -> dict:
        """将工具描述转为 OpenAI Function Calling 的 JSON Schema 格式。

        这个格式同样兼容通义千问等使用 OpenAI 兼容接口的模型。
        """
        properties = {}
        required = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.items_type:
                prop["items"] = {"type": param.items_type}
            if param.enum:
                prop["enum"] = param.enum
            if param.minimum is not None:
                prop["minimum"] = param.minimum
            if param.maximum is not None:
                prop["maximum"] = param.maximum

            properties[param.name] = prop
            if param.required:
                required.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }
