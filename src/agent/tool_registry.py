"""工具注册表。

将一组 BaseTool 实例按 name 索引起来，供 Agent 层按名称调度执行。
对外提供：
- get_schemas(): 返回全部工具的 OpenAI function schema，直接喂给 LLMClient.chat(tools=...)
- invoke(name, arguments_json): 按名字调用工具；始终返回 ToolResult，
  错误（工具不存在、JSON 解析失败、工具内部异常）都被包装为 success=False 的结果，
  不会把异常抛给 Agent 主循环。
"""

from __future__ import annotations

import json
from typing import Any

from src.tools.base import BaseTool, ToolResult


class ToolRegistry:
    """工具注册与调度中心。"""

    def __init__(self, tools: list[BaseTool]) -> None:
        if not tools:
            raise ValueError("ToolRegistry requires at least one tool.")

        self._tools: dict[str, BaseTool] = {}
        for tool in tools:
            if tool.name in self._tools:
                raise ValueError(f"Duplicate tool name: {tool.name!r}")
            self._tools[tool.name] = tool

    @property
    def names(self) -> list[str]:
        """当前注册的所有工具名。"""
        return list(self._tools.keys())

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def get_schemas(self) -> list[dict[str, Any]]:
        """返回全部工具的 OpenAI Function Calling schema 列表。"""
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def invoke(self, name: str, arguments_json: str | dict) -> ToolResult:
        """按名字调度执行一个工具。

        Args:
            name: 工具名（对应 LLM 返回的 function.name）
            arguments_json: LLM 返回的参数。通常是 JSON 字符串；
                为了容错也接受已经解析好的 dict。

        Returns:
            ToolResult。所有异常路径（含未知工具、JSON 解析失败）都会返回 success=False。
        """
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(
                success=False,
                error=f"Unknown tool: {name!r}. Available: {self.names}",
                message=f"Tool not found: {name}",
            )

        if isinstance(arguments_json, dict):
            args: dict[str, Any] = arguments_json
        else:
            raw = arguments_json or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError as e:
                return ToolResult(
                    success=False,
                    error=f"Invalid JSON arguments: {e}",
                    message=f"Failed to parse arguments for tool {name}",
                )
            if not isinstance(parsed, dict):
                return ToolResult(
                    success=False,
                    error=f"Arguments must be a JSON object, got {type(parsed).__name__}",
                    message=f"Invalid arguments structure for tool {name}",
                )
            args = parsed

        # BaseTool.run() 内部已做参数校验与异常兜底
        return tool.run(**args)
