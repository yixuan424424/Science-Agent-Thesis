"""RATS — 检索增强工具选择模块。

对外暴露 RATS / RATSConfig / ToolScore 与若干 Embedder 实现。
"""

from src.tool_selector.cache import EmbeddingCache
from src.tool_selector.embedder import Embedder, HashEmbedder, OpenAIEmbedder, default_embedder
from src.tool_selector.retriever import DEFAULT_TOOL_CATEGORIES, RATS, RATSConfig, ToolScore

__all__ = [
    "Embedder",
    "OpenAIEmbedder",
    "HashEmbedder",
    "default_embedder",
    "EmbeddingCache",
    "RATS",
    "RATSConfig",
    "ToolScore",
    "DEFAULT_TOOL_CATEGORIES",
]
