"""RATS 单元测试。

全部使用 HashEmbedder，完全离线、不触碰 API。
"""

from __future__ import annotations

import numpy as np
import pytest

from src.tool_selector.cache import EmbeddingCache
from src.tool_selector.embedder import HashEmbedder
from src.tool_selector.retriever import RATS, RATSConfig
from src.tools import build_all_tools


@pytest.fixture
def selector(tmp_path):
    """共用的 RATS fixture：12 工具 + HashEmbedder + 临时 cache 路径。"""
    cache = EmbeddingCache(path=tmp_path / "cache.json")
    return RATS(
        tools=build_all_tools(),
        embedder=HashEmbedder(dim=512),
        cache=cache,
        config=RATSConfig(k=6, k_min=3),
    )


def test_build_populates_all_tool_vectors(selector):
    selector.build()
    assert len(selector._tool_vectors) == 12
    for name, vec in selector._tool_vectors.items():
        assert isinstance(vec, np.ndarray)
        assert vec.shape == (512,)


def test_select_returns_between_kmin_and_k(selector):
    result = selector.select("Compute the determinant of a 3x3 matrix", k=4)
    assert 3 <= len(result) <= 4


def test_select_respects_k_min_when_threshold_too_high(selector):
    # 阈值极高 -> 所有工具都过不了阈值，但 k_min=3 是硬下限
    selector.config.threshold = 999.0
    result = selector.select("noop task", k=6)
    assert len(result) == 3


def test_matrix_task_retrieves_matrix_tool_in_topK(selector):
    task = "matrix determinant operation linear algebra inverse"
    names = {t.name for t in selector.select(task, k=4)}
    assert "matrix_operation" in names


def test_visualization_task_retrieves_chart_tool(selector):
    task = "draw a line chart visualization plot figure image"
    names = {t.name for t in selector.select(task, k=4)}
    assert any(n in names for n in ("line_chart", "scatter_chart", "bar_chart", "heatmap"))


def test_regression_task_retrieves_regression_or_fitting(selector):
    task = "linear regression slope intercept curve fit coefficients"
    names = {t.name for t in selector.select(task, k=4)}
    assert "linear_regression" in names or "curve_fitting" in names


def test_cache_is_populated_after_build_and_reused(selector):
    selector.build()
    cache_path = selector._cache.path
    assert cache_path.exists()

    vectors_before = {name: vec.copy() for name, vec in selector._tool_vectors.items()}
    # 模拟进程重启：清空内存向量但保留磁盘缓存
    selector._tool_vectors = {}
    selector._built = False
    selector.build()
    for name, vec in vectors_before.items():
        assert np.allclose(vec, selector._tool_vectors[name])


def test_score_returns_descending_rerank(selector):
    scores = selector.score("fit a line to some data points and get slope", k=6)
    rs = [s.rerank_score for s in scores]
    assert rs == sorted(rs, reverse=True)


def test_score_includes_per_feature_values(selector):
    scores = selector.score("matrix determinant", k=4)
    assert scores, "expected at least one score"
    s = scores[0]
    assert 0.0 <= s.arg_overlap <= 1.0
    assert s.category_bonus in (0.0, 1.0)
    assert 0.0 <= s.history_success <= 1.0


def test_category_bonus_applied_for_majority(selector):
    # 纯统计类任务，top-3 应当主导在 statistics 类别
    scores = selector.score("mean variance standard deviation statistics", k=6)
    top3_cats = [
        selector._categories.get(s.tool_name) for s in scores[:3]
    ]
    # 至少 2/3 应为 statistics，否则 category_bonus 机制不成立
    assert top3_cats.count("statistics") >= 2


def test_get_schemas_returns_openai_format(selector):
    schemas = selector.get_schemas("compute mean of a dataset", k=3)
    assert len(schemas) >= 3
    for sch in schemas:
        assert sch["type"] == "function"
        assert "name" in sch["function"]
        assert "parameters" in sch["function"]


def test_rats_requires_nonempty_tools():
    with pytest.raises(ValueError):
        RATS(tools=[], embedder=HashEmbedder())


def test_k_min_floor_when_k_below(selector):
    # 请求 k=1 但 k_min=3 -> 应返回 3 个
    result = selector.select("matrix", k=1)
    assert len(result) == 3
