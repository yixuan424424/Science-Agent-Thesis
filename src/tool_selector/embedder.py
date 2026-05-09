"""嵌入向量提供方。

主路径：OpenAI 兼容的 embedding 接口（通义千问 text-embedding-v3 等）。
离线/测试回退：`HashEmbedder`，基于 token 哈希的确定性伪嵌入，无需任何
网络调用。用于单元测试与 API 不可用时的降级。

两种实现共用抽象基类 `Embedder`，`default_embedder()` 会先尝试 OpenAIEmbedder，
失败则降级到 HashEmbedder。
"""

from __future__ import annotations

import hashlib
import logging
import re
import time
from abc import ABC, abstractmethod
from typing import Any

import numpy as np

from src.config import LLM_API_KEY, LLM_BASE_URL

logger = logging.getLogger(__name__)


class Embedder(ABC):
    """嵌入向量提供方抽象基类。"""

    @property
    @abstractmethod
    def dim(self) -> int:
        """嵌入向量维度。"""
        ...

    @abstractmethod
    def embed(self, texts: list[str]) -> list[list[float]]:
        """对一批文本批量产生嵌入向量。

        返回的 list 长度必须与输入一致，顺序对齐。
        """
        ...


class OpenAIEmbedder(Embedder):
    """基于 OpenAI 兼容接口的嵌入器。

    默认用通义千问 ``text-embedding-v3``（1024 维）。对瞬时错误做简单重试。
    """

    def __init__(
        self,
        model: str = "text-embedding-v3",
        api_key: str = LLM_API_KEY,
        base_url: str = LLM_BASE_URL,
        timeout: float = 30.0,
        max_retries: int = 2,
        batch_size: int = 10,
    ) -> None:
        if not api_key:
            raise ValueError("LLM_API_KEY is required for OpenAIEmbedder.")
        from openai import OpenAI  # 延迟导入，避免无 API Key 的测试环境加载 openai

        self._client = OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        self.model = model
        self.max_retries = max_retries
        # 通义 text-embedding-v3 单次最多 10 条，故默认分批上限 10
        self.batch_size = max(1, batch_size)
        self._dim = 1024  # text-embedding-v3 默认维度，首次调用后按实际返回更新

    @property
    def dim(self) -> int:
        return self._dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            batch = texts[i : i + self.batch_size]
            out.extend(self._embed_batch(batch))
        return out

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """对单个批次做带重试的 embedding 调用。"""
        from openai import APIConnectionError, APITimeoutError, RateLimitError

        last_err: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._client.embeddings.create(model=self.model, input=texts)
                vecs = [d.embedding for d in resp.data]
                if vecs:
                    self._dim = len(vecs[0])
                return vecs
            except (APIConnectionError, APITimeoutError, RateLimitError) as e:
                last_err = e
                if attempt >= self.max_retries:
                    break
                time.sleep(2 ** attempt)
            except Exception:
                raise
        raise RuntimeError(
            f"Embedding call failed after {self.max_retries + 1} attempts: {last_err}"
        )


class HashEmbedder(Embedder):
    """无需网络的确定性嵌入器。

    采用"带符号的特征哈希 (feature hashing)"策略：
    - 用正则抽出 token（ASCII 字母串 + 单个 CJK 字符）
    - 每个 token 经 MD5 哈希后映射到固定维度的索引位置
    - 根据哈希高位决定正负号，累加到对应 slot
    - 最终 L2 归一化

    不是语义嵌入，但具有以下属性适合单元测试：
    - 完全确定（无随机种子），无 API / 无网络
    - 同一 token 永远映射到同一位置 → 重复 token 描述得到相同向量
    - 文本之间共享的 token 越多 → 余弦相似度越高
    """

    def __init__(self, dim: int = 512) -> None:
        if dim <= 0:
            raise ValueError(f"dim must be positive, got {dim}")
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        # ASCII 字母串 + 单个 CJK 字符都算 token
        return [t.lower() for t in re.findall(r"[A-Za-z]+|[\u4e00-\u9fff]", text) if t]

    def embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for text in texts:
            vec = np.zeros(self._dim, dtype=np.float64)
            for tok in self._tokenize(text):
                h = int(hashlib.md5(tok.encode("utf-8")).hexdigest(), 16)
                idx = h % self._dim
                sign = 1.0 if ((h >> 8) & 1) else -1.0
                vec[idx] += sign
            norm = float(np.linalg.norm(vec))
            if norm > 0.0:
                vec = vec / norm
            out.append(vec.tolist())
        return out


def default_embedder() -> Embedder:
    """优先尝试 OpenAIEmbedder，任何异常都降级到 HashEmbedder。

    用于无法提前判断是否有 API Key 的环境（CI / 离线开发）。
    """
    try:
        return OpenAIEmbedder()
    except Exception as e:
        logger.warning("OpenAIEmbedder unavailable (%s), falling back to HashEmbedder.", e)
        return HashEmbedder()


__all__: list[str] = ["Embedder", "OpenAIEmbedder", "HashEmbedder", "default_embedder"]

# 让 mypy / IDE 知道 Any 被使用（部分签名依赖 Any）
_ = Any
