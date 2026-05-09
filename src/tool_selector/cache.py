"""工具嵌入向量的磁盘缓存。

Key 由三部分组成：``tool_name`` + ``desc_hash`` + ``model_id``。
- desc_hash 只取 MD5 前 8 位，足以避免描述被改动后旧缓存继续命中
- model_id 区分不同 embedding 模型的向量

缓存文件默认写到 ``outputs/tool_embedding_cache.json``，不进 Git，
跨机器/跨环境会各自重新算一次，算完仅需 1 次 API 调用（12 个工具一批）。
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


DEFAULT_CACHE_PATH: Path = OUTPUT_DIR / "tool_embedding_cache.json"


def _desc_hash(description: str) -> str:
    """描述文本 -> 8 位哈希，用于 cache key 中快速失效旧条目。"""
    return hashlib.md5(description.encode("utf-8")).hexdigest()[:8]


class EmbeddingCache:
    """工具嵌入向量的持久化缓存。

    单个 JSON 文件，内容形如：
        {"matrix_operation::a1b2c3d4::text-embedding-v3": [0.12, ...], ...}

    对外暴露 get / put / save 三个方法。load 在构造时自动完成，
    文件损坏时静默清空（不影响后续 build 重算）。
    """

    def __init__(self, path: Path | str = DEFAULT_CACHE_PATH) -> None:
        self.path: Path = Path(path)
        self._data: dict[str, list[float]] = {}
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    self._data = {
                        k: list(v) for k, v in loaded.items() if isinstance(v, list)
                    }
            except (OSError, json.JSONDecodeError) as e:
                logger.warning("Embedding cache at %s is unreadable (%s); starting fresh.", self.path, e)
                self._data = {}

    @staticmethod
    def make_key(tool_name: str, description: str, model: str) -> str:
        """生成缓存 key。任何一项改变都会使旧条目失效。"""
        return f"{tool_name}::{_desc_hash(description)}::{model}"

    def get(self, key: str) -> list[float] | None:
        return self._data.get(key)

    def put(self, key: str, vector: list[float]) -> None:
        self._data[key] = list(vector)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(self._data, ensure_ascii=False),
            encoding="utf-8",
        )

    def __len__(self) -> int:
        return len(self._data)


__all__: list[str] = ["EmbeddingCache", "DEFAULT_CACHE_PATH"]
