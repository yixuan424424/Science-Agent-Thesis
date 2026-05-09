"""DAGPlanner 纯代码部分的单元测试（不触 LLM / 不触磁盘）。

覆盖:

- :func:`parse_plan` 的宽松解析（JSON / 带 code fence / dict）
- :class:`PlanValidator` 五类失败模式
- :func:`topological_order` 的顺序正确性
- :func:`resolve_args` 的类型保留、嵌套、错误报告
"""

from __future__ import annotations

import pytest

from src.agent.dag_planner import (
    PlanValidator,
    parse_plan,
    resolve_args,
    topological_order,
)

ALLOWED: set[str] = {
    "matrix_operation",
    "linear_regression",
    "scatter_chart",
    "descriptive_statistics",
    "line_chart",
    "curve_fitting",
}


def _make_plan(steps_raw: list[dict]):
    return parse_plan({"steps": steps_raw})


# ------------------------- parse_plan --------------------------------------


def test_parse_valid_dict():
    plan = _make_plan(
        [
            {
                "id": "s1",
                "goal": "fit",
                "tool": "linear_regression",
                "args_template": {"x": [1, 2], "y": [1, 2]},
                "depends_on": [],
            }
        ]
    )
    assert len(plan.steps) == 1
    assert plan.steps[0].tool == "linear_regression"


def test_parse_strips_code_fences():
    raw = """```json
    {"steps": [{"id": "s1", "goal": "g", "tool": "linear_regression",
       "args_template": {}, "depends_on": []}]}
    ```"""
    plan = parse_plan(raw)
    assert len(plan.steps) == 1


def test_parse_raises_on_non_object_root():
    with pytest.raises(ValueError):
        parse_plan("[]")


def test_parse_raises_when_steps_not_list():
    with pytest.raises(ValueError):
        parse_plan({"steps": "nope"})


def test_parse_accepts_legacy_args_alias():
    # 某些模型会写 "args" 而非 "args_template"，parse_plan 允许两种别名
    plan = parse_plan(
        {
            "steps": [
                {"id": "s1", "goal": "g", "tool": "linear_regression",
                 "args": {"x": [1, 2]}, "depends_on": []}
            ]
        }
    )
    assert plan.steps[0].args_template == {"x": [1, 2]}


# ------------------------- PlanValidator -----------------------------------


def test_validate_accepts_valid_plan():
    plan = _make_plan(
        [
            {
                "id": "s1",
                "goal": "stats",
                "tool": "descriptive_statistics",
                "args_template": {"data": [1, 2, 3]},
                "depends_on": [],
            }
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert v.ok, v.errors


def test_validate_rejects_unknown_tool():
    plan = _make_plan(
        [{"id": "s1", "goal": "bogus", "tool": "nuke",
          "args_template": {}, "depends_on": []}]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("not in allowed tools" in e for e in v.errors)


def test_validate_rejects_duplicate_ids():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": []},
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": []},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("Duplicate" in e for e in v.errors)


def test_validate_rejects_cycle():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s2"]},
            {"id": "s2", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s1"]},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("cycle" in e.lower() for e in v.errors)


def test_validate_rejects_self_dependency():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s1"]},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("self-dependency" in e for e in v.errors)


def test_validate_rejects_undeclared_dependency():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s9"]},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("not a declared step" in e for e in v.errors)


def test_validate_rejects_placeholder_missing_from_depends_on():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "stats", "tool": "descriptive_statistics",
             "args_template": {"data": [1, 2]}, "depends_on": []},
            {"id": "s2", "goal": "plot", "tool": "line_chart",
             "args_template": {"title": "${s1.mean}"}, "depends_on": []},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("not in depends_on" in e for e in v.errors)


def test_validate_accepts_placeholder_with_depends_on():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "stats", "tool": "descriptive_statistics",
             "args_template": {"data": [1, 2]}, "depends_on": []},
            {"id": "s2", "goal": "plot", "tool": "line_chart",
             "args_template": {"title": "${s1.mean}"}, "depends_on": ["s1"]},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert v.ok, v.errors


def test_validate_rejects_too_many_steps():
    steps = [
        {"id": f"s{i}", "goal": "g", "tool": "linear_regression",
         "args_template": {}, "depends_on": []}
        for i in range(1, 11)
    ]
    plan = _make_plan(steps)
    v = PlanValidator(allowed_tools=ALLOWED, max_steps=5).validate(plan)
    assert not v.ok
    assert any("exceeds max" in e for e in v.errors)


def test_validate_rejects_empty_plan():
    plan = _make_plan([])
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert any("no steps" in e for e in v.errors)


def test_validate_collects_multiple_errors():
    # 同时触发：未知工具、重复 ID、自依赖
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "unknown_tool",
             "args_template": {}, "depends_on": ["s1"]},
            {"id": "s1", "goal": "g", "tool": "also_unknown",
             "args_template": {}, "depends_on": []},
        ]
    )
    v = PlanValidator(allowed_tools=ALLOWED).validate(plan)
    assert not v.ok
    assert len(v.errors) >= 3  # 至少三类错误


# ------------------------- topological_order ------------------------------


def test_topological_order_correct():
    plan = _make_plan(
        [
            {"id": "s2", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s1"]},
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": []},
            {"id": "s3", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s2"]},
        ]
    )
    order = topological_order(plan)
    assert order.index("s1") < order.index("s2") < order.index("s3")


def test_topological_order_diamond_ok():
    plan = _make_plan(
        [
            {"id": "s1", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": []},
            {"id": "s2", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s1"]},
            {"id": "s3", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s1"]},
            {"id": "s4", "goal": "g", "tool": "linear_regression",
             "args_template": {}, "depends_on": ["s2", "s3"]},
        ]
    )
    order = topological_order(plan)
    assert order.index("s1") < order.index("s2") < order.index("s4")
    assert order.index("s1") < order.index("s3") < order.index("s4")


# ------------------------- resolve_args -----------------------------------


def test_resolve_args_full_placeholder_preserves_type():
    obs = {"s1": {"success": True, "data": {"slope": 2.0, "intercept": 1.0}}}
    template = {"m": "${s1.slope}", "b": "${s1.intercept}"}
    resolved, unresolved = resolve_args(template, obs)
    assert resolved == {"m": 2.0, "b": 1.0}
    assert unresolved == []


def test_resolve_args_list_indexing():
    obs = {"s1": {"success": True, "data": {"xs": [10, 20, 30]}}}
    template = {"first": "${s1.xs.0}", "third": "${s1.xs.2}"}
    resolved, unresolved = resolve_args(template, obs)
    assert resolved == {"first": 10, "third": 30}
    assert unresolved == []


def test_resolve_args_whole_data_reference():
    obs = {"s1": {"success": True, "data": {"result": [1, 2, 3], "shape": [1, 3]}}}
    template = {"matrix_a": "${s1}"}  # 整个 data 对象
    resolved, unresolved = resolve_args(template, obs)
    assert resolved == {"matrix_a": {"result": [1, 2, 3], "shape": [1, 3]}}
    assert unresolved == []


def test_resolve_args_reports_missing_field():
    obs = {"s1": {"success": True, "data": {"slope": 2.0}}}
    template = {"x": "${s1.intercept}"}
    _, unresolved = resolve_args(template, obs)
    assert unresolved
    assert "intercept" in unresolved[0]


def test_resolve_args_reports_failed_step():
    obs = {"s1": {"success": False, "error": "boom"}}
    template = {"x": "${s1.slope}"}
    _, unresolved = resolve_args(template, obs)
    assert unresolved
    assert "failed" in unresolved[0] or "step not executed" in unresolved[0]


def test_resolve_args_literals_unchanged():
    obs: dict = {}
    template = {"data": [1, 2, 3], "name": "hello", "flag": True}
    resolved, unresolved = resolve_args(template, obs)
    assert resolved == template
    assert unresolved == []


def test_resolve_args_embedded_string():
    obs = {"s1": {"success": True, "data": {"slope": 2.0}}}
    template = {"title": "Fit: slope=${s1.slope}"}
    resolved, _ = resolve_args(template, obs)
    assert "slope=2.0" in resolved["title"]


def test_resolve_args_nested_dict_and_list():
    obs = {"s1": {"success": True, "data": {"coef": [1.0, 2.0]}}}
    template = {"outer": {"coef_list": "${s1.coef}", "info": ["${s1.coef.0}"]}}
    resolved, unresolved = resolve_args(template, obs)
    assert resolved == {"outer": {"coef_list": [1.0, 2.0], "info": [1.0]}}
    assert unresolved == []
