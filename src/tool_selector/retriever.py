"""RATS: 检索增强的工具选择算法。

算法概述（对应论文 Algorithm 1）:

    输入: 用户任务 T, 工具库 P = {t_1,..., t_N}, 预算 K, 阈值 θ
    输出: 精简工具集 S ⊆ P

    [阶段 1 — 离线预计算] 对每个工具 t_i 构造复合文本
        text_i = name ⊕ normalized_name ⊕ description ⊕ params
        e_i    = Embed(text_i)              # 结果写入磁盘缓存
    [阶段 2 — 在线检索]
        e_T         = Embed(T)
        score_i     = cosine(e_T, e_i)
        candidates  = top_K(score_i, K)
    [阶段 3 — 特征重排]
        对每个候选 t_j 计算多维特征：
        - emb_score_j   : cosine(e_T, e_j)
        - arg_overlap_j : |tokens(T) ∩ tokens(t_j.params ∪ t_j.desc)| / |tokens(T)|
        - category_j    : 若 t_j 的类别与 top-3 多数派一致则 1 否则 0
        - hist_j        : 历史成功率（未启用时取 1.0）
        rerank_j = w_emb * emb + w_arg * arg + w_cat * category + w_hist * hist
    [阶段 4 — 阈值过滤]
        S = { t_j | rerank_j ≥ θ }   并保证 |S| ≥ K_min
    返回 S

算法特性:
- 离线算一次、在线只算 task 向量：12 工具 * 1 + N tasks * 1 次 API 调用
- 规则重排不依赖训练，权重与特征全部可解释
- 支持替换 embedder（测试环境 HashEmbedder / 生产 OpenAIEmbedder）
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any

import numpy as np

from src.tool_selector.cache import EmbeddingCache
from src.tool_selector.embedder import Embedder, default_embedder
from src.tools.base import BaseTool

logger = logging.getLogger(__name__)


# 与 src/tools/__init__.py 的 ALL_TOOL_CLASSES 保持一致的类别映射
DEFAULT_TOOL_CATEGORIES: dict[str, str] = {
    "matrix_operation": "numerical",
    "numerical_integration": "numerical",
    "curve_fitting": "numerical",
    "equation_solver": "numerical",
    "descriptive_statistics": "statistics",
    "hypothesis_test": "statistics",
    "linear_regression": "statistics",
    "correlation_analysis": "statistics",
    "line_chart": "visualization",
    "scatter_chart": "visualization",
    "bar_chart": "visualization",
    "heatmap": "visualization",
}


@dataclass
class ToolScore:
    """单个工具的详细打分，便于消融分析与日志。

    ``rerank_score`` 是最终用来排序/过滤的加权和；其它字段是用于
    绘制消融表（只用 embedding / 加 arg_overlap / 加 category / 加 history）的来源。
    """

    tool_name: str
    embedding_score: float = 0.0
    arg_overlap: float = 0.0
    category_bonus: float = 0.0
    history_success: float = 1.0
    rerank_score: float = 0.0


@dataclass
class RATSConfig:
    """RATS 超参数配置。

    - k: 阶段 2 截取的候选数量（默认 6）。运行时 `select(k=...)` 可覆盖
    - k_min: 返回结果的最小数量（确保阈值过滤后仍有工具可选）
    - threshold: rerank_score 阈值，低于阈值的工具被过滤，但 k_min 是硬下限
    - w_*: 四个特征的加权系数，默认与论文一致 (0.6, 0.2, 0.1, 0.1)
    """

    k: int = 6
    k_min: int = 3
    threshold: float = 0.0
    w_embedding: float = 0.6
    w_arg_overlap: float = 0.2
    w_category: float = 0.1
    w_history: float = 0.1


class RATS:
    """检索增强的工具选择器。

    典型用法：

        from src.tool_selector import RATS
        from src.tools import build_all_tools

        selector = RATS(tools=build_all_tools())
        selector.build()                       # 一次性预算所有工具向量
        selected = selector.select(task_text)  # 返回精简后的 BaseTool 列表

    亦可通过 ``score()`` 拿到完整的特征打分（含每个特征值），用于论文消融。
    """

    def __init__(
        self,
        tools: list[BaseTool],
        embedder: Embedder | None = None,
        cache: EmbeddingCache | None = None,
        config: RATSConfig | None = None,
        categories: dict[str, str] | None = None,
        history: dict[str, float] | None = None,
    ) -> None:
        if not tools:
            raise ValueError("RATS requires at least one tool.")
        self._tools: dict[str, BaseTool] = {t.name: t for t in tools}
        self._embedder: Embedder = embedder if embedder is not None else default_embedder()
        self._cache: EmbeddingCache = cache if cache is not None else EmbeddingCache()
        self.config: RATSConfig = config if config is not None else RATSConfig()
        self._categories: dict[str, str] = (
            categories if categories is not None else DEFAULT_TOOL_CATEGORIES
        )
        self._history: dict[str, float] = history if history is not None else {}
        self._tool_vectors: dict[str, np.ndarray] = {}
        self._built: bool = False

    @staticmethod
    def _compose_tool_text(tool: BaseTool) -> str:
        """为一个工具拼接检索文本。

        特意把工具名"去下划线"后也放进来（例如 `matrix_operation` → `matrix operation`），
        让 HashEmbedder / 多语言 embedder 都能捕捉到。
        """
        parts: list[str] = [
            tool.name,
            tool.name.replace("_", " "),
            tool.description,
        ]
        for p in tool.parameters:
            desc = (p.description or "").strip()
            parts.append(f"{p.name}: {desc}")
            if p.enum:
                parts.append(f"enum: {', '.join(str(e) for e in p.enum)}")
        return " | ".join(parts)

    def build(self) -> None:
        """计算所有工具的嵌入向量，并落盘缓存。

        对命中缓存的工具不会重复调用 embedder。
        """
        model_id: str = getattr(self._embedder, "model", self._embedder.__class__.__name__)

        texts_to_embed: list[str] = []
        keys_to_embed: list[str] = []
        names_to_embed: list[str] = []

        for name, tool in self._tools.items():
            text = self._compose_tool_text(tool)
            key = EmbeddingCache.make_key(name, text, model_id)
            cached = self._cache.get(key)
            if cached is not None:
                self._tool_vectors[name] = np.asarray(cached, dtype=np.float64)
            else:
                texts_to_embed.append(text)
                keys_to_embed.append(key)
                names_to_embed.append(name)

        if texts_to_embed:
            vectors = self._embedder.embed(texts_to_embed)
            for name, key, vec in zip(names_to_embed, keys_to_embed, vectors):
                arr = np.asarray(vec, dtype=np.float64)
                self._tool_vectors[name] = arr
                self._cache.put(key, arr.tolist())
            try:
                self._cache.save()
            except OSError as e:
                logger.warning("Failed to save embedding cache to %s: %s", self._cache.path, e)

        self._built = True

    @staticmethod
    def _cosine(a: np.ndarray, b: np.ndarray) -> float:
        na = float(np.linalg.norm(a))
        nb = float(np.linalg.norm(b))
        if na == 0.0 or nb == 0.0:
            return 0.0
        return float(np.dot(a, b) / (na * nb))

    @staticmethod
    def _tokenize(text: str) -> set[str]:
        """为 arg_overlap 抽取小写英文 token（长度 >=3）。

        中文 token 不参与 arg_overlap，只参与 embedding（因为简单词袋对中文不可靠）。
        """
        return {w.lower() for w in re.findall(r"[A-Za-z]{3,}", text or "")}

    def _arg_overlap(self, task: str, tool: BaseTool) -> float:
        """任务 token 与工具（name/description/params）token 的 Jaccard 式占比。

        分母用 |task_tokens|（而非并集）让分数保持 [0, 1] 且偏向"任务词覆盖率"。
        """
        task_tokens = self._tokenize(task)
        if not task_tokens:
            return 0.0
        tool_tokens: set[str] = set()
        tool_tokens.update(self._tokenize(tool.name))
        tool_tokens.update(self._tokenize(tool.name.replace("_", " ")))
        tool_tokens.update(self._tokenize(tool.description))
        for p in tool.parameters:
            tool_tokens.update(self._tokenize(p.name))
            tool_tokens.update(self._tokenize(p.description or ""))
            if p.enum:
                for e in p.enum:
                    tool_tokens.update(self._tokenize(str(e)))
        if not tool_tokens:
            return 0.0
        return len(task_tokens & tool_tokens) / max(1, len(task_tokens))

    def select(self, task: str, k: int | None = None) -> list[BaseTool]:
        """选择一个精简工具集，返回按 rerank_score 降序排列的 BaseTool 列表。"""
        scores = self.score(task, k=k)
        return [self._tools[s.tool_name] for s in scores]

    def score(self, task: str, k: int | None = None) -> list[ToolScore]:
        """对每个候选工具打分并返回过滤后的结果。

        返回列表已按 ``rerank_score`` 降序排序，含每个特征的原始值。
        """
        if not self._built:
            self.build()

        k_use = k if k is not None else self.config.k
        k_use = max(self.config.k_min, min(k_use, len(self._tools)))

        task_vec_raw = self._embedder.embed([task])
        if not task_vec_raw:
            return []
        task_vec = np.asarray(task_vec_raw[0], dtype=np.float64)

        # 阶段 1: 对每个工具算 embedding 相似度
        emb_scores: list[tuple[str, float]] = [
            (name, self._cosine(task_vec, vec)) for name, vec in self._tool_vectors.items()
        ]
        emb_scores.sort(key=lambda x: x[1], reverse=True)
        candidates = emb_scores[:k_use]
        if not candidates:
            return []

        # 阶段 2: 统计 top-3 主导类别，供 category_bonus 使用
        top3_names = [c[0] for c in candidates[: min(3, len(candidates))]]
        cat_counts: dict[str, int] = {}
        for name in top3_names:
            cat = self._categories.get(name)
            if cat:
                cat_counts[cat] = cat_counts.get(cat, 0) + 1
        majority_cat: str | None = (
            max(cat_counts.items(), key=lambda x: x[1])[0] if cat_counts else None
        )

        # 阶段 3: 计算每个候选的 rerank_score
        cfg = self.config
        results: list[ToolScore] = []
        for name, emb_s in candidates:
            tool = self._tools[name]
            arg_s = self._arg_overlap(task, tool)
            cat_bonus = (
                1.0 if (majority_cat and self._categories.get(name) == majority_cat) else 0.0
            )
            hist = self._history.get(name, 1.0)
            rerank = (
                cfg.w_embedding * emb_s
                + cfg.w_arg_overlap * arg_s
                + cfg.w_category * cat_bonus
                + cfg.w_history * hist
            )
            results.append(
                ToolScore(
                    tool_name=name,
                    embedding_score=emb_s,
                    arg_overlap=arg_s,
                    category_bonus=cat_bonus,
                    history_success=hist,
                    rerank_score=rerank,
                )
            )
        results.sort(key=lambda s: s.rerank_score, reverse=True)

        # 阶段 4: 阈值过滤（保底 k_min）
        kept = [r for r in results if r.rerank_score >= cfg.threshold]
        if len(kept) < cfg.k_min:
            kept = results[: cfg.k_min]
        return kept

    def get_schemas(self, task: str, k: int | None = None) -> list[dict[str, Any]]:
        """便捷接口：返回精简工具集的 OpenAI Function Calling schema 列表。"""
        selected = self.select(task, k=k)
        return [t.to_openai_schema() for t in selected]

    @property
    def tool_names(self) -> list[str]:
        """已注册工具的名字列表，用于调试与日志。"""
        return list(self._tools.keys())


__all__: list[str] = [
    "RATS",
    "RATSConfig",
    "ToolScore",
    "DEFAULT_TOOL_CATEGORIES",
]
