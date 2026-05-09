"""DAGPlanner 数据类与纯代码校验器。

本模块只包含与 LLM 无关的部分，即论文 Algorithm 2（Plan Validation）中
那个"0 次 LLM 调用"的校验阶段以及辅助的占位符解析。对 LLM 的 Plan 调用、
Fix 调用、Answer 调用在 :mod:`src.agent.dag_agent` 中实现。

核心对象:

- :class:`PlanStep` / :class:`Plan` — DAG 计划的形式化数据类
- :func:`parse_plan` — 把 LLM 返回的 JSON 字符串/字典转成 Plan
- :class:`PlanValidator` — 5 类结构校验（可独立消融）
- :func:`topological_order` — 返回拓扑排序后的 step id 列表
- :func:`resolve_args` — 解析 args_template 里的 ``${sX.field}`` 占位符

占位符语法:

- ``${sX}`` 引用 step sX 的完整 ``data``
- ``${sX.field}`` 引用 step sX 的 ``data.field``（支持多级点号，如
  ``${s1.result.slope}``；列表用整数下标 ``${s1.xs.0}``）
"""

from __future__ import annotations

import graphlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# 占位符语法：${sX} 或 ${sX.field[.subfield]*}
_PLACEHOLDER_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?:\.([^}]+))?\}")


@dataclass
class PlanStep:
    """DAG 中的单一步骤。"""

    id: str
    goal: str
    tool: str
    args_template: dict[str, Any] = field(default_factory=dict)
    depends_on: list[str] = field(default_factory=list)


@dataclass
class Plan:
    """完整的 DAG 计划。"""

    steps: list[PlanStep] = field(default_factory=list)

    def step_by_id(self, sid: str) -> PlanStep | None:
        for s in self.steps:
            if s.id == sid:
                return s
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "steps": [
                {
                    "id": s.id,
                    "goal": s.goal,
                    "tool": s.tool,
                    "args_template": s.args_template,
                    "depends_on": s.depends_on,
                }
                for s in self.steps
            ]
        }


@dataclass
class ValidationResult:
    """校验结果，一次性返回所有错误供 LLM 统一修正。"""

    ok: bool
    errors: list[str] = field(default_factory=list)

    def add(self, msg: str) -> None:
        self.errors.append(msg)
        self.ok = False


def parse_plan(raw: str | dict) -> Plan:
    """把 LLM 返回的 JSON 字符串或字典解析成 :class:`Plan`。

    只做结构化解析，合法性由 :class:`PlanValidator` 负责。
    对被 ```` ```json ... ``` ```` 包裹的文本做兜底剥离。
    """
    if isinstance(raw, dict):
        data = raw
    else:
        text = (raw or "").strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text)
            text = re.sub(r"\s*```\s*$", "", text)
        data = json.loads(text)

    if not isinstance(data, dict):
        raise ValueError("Plan JSON root must be an object.")

    steps_raw = data.get("steps", [])
    if not isinstance(steps_raw, list):
        raise ValueError("Plan.steps must be a list.")

    steps: list[PlanStep] = []
    for idx, s in enumerate(steps_raw):
        if not isinstance(s, dict):
            raise ValueError(f"Step #{idx} is not an object.")
        steps.append(
            PlanStep(
                id=str(s.get("id", f"s{idx + 1}")),
                goal=str(s.get("goal", "")),
                tool=str(s.get("tool", "")),
                args_template=dict(s.get("args_template") or s.get("args") or {}),
                depends_on=list(s.get("depends_on") or []),
            )
        )
    return Plan(steps=steps)


class PlanValidator:
    """DAG 计划的纯代码校验器（无 LLM 调用）。

    消融用：单独跑 Plan 不走 Validator vs. 跑 Plan+Validator 的差异，即可量化
    "算法级校验"相对"纯 Prompt 规划"的收益。

    五类校验（全部失败都会被收集，一次性返回）:

    1. 结构：steps 非空、不超过 ``max_steps``、ID 唯一
    2. 工具：每个 step 的 tool 在 ``allowed_tools`` 集合内
    3. 依赖：``depends_on`` 引用的 step 已声明、不自依赖
    4. 无环：对 (id, depends_on) 做拓扑排序，捕获 ``CycleError``
    5. 占位符：``args_template`` 中的 ``${sX.field}`` 占位符对应的 step 必须
       同时出现在该 step 的 ``depends_on`` 里
    """

    def __init__(
        self,
        allowed_tools: set[str],
        max_steps: int = 8,
    ) -> None:
        if not allowed_tools:
            raise ValueError("PlanValidator requires a non-empty allowed_tools set.")
        self.allowed_tools: set[str] = set(allowed_tools)
        self.max_steps: int = max_steps

    def validate(self, plan: Plan) -> ValidationResult:
        result = ValidationResult(ok=True)

        # 1a) 至少 1 步
        if not plan.steps:
            result.add("Plan has no steps.")
            return result

        # 1b) 不超过 max_steps
        if len(plan.steps) > self.max_steps:
            result.add(
                f"Plan has {len(plan.steps)} steps, exceeds max {self.max_steps}."
            )

        # 1c) ID 唯一
        ids: list[str] = [s.id for s in plan.steps]
        id_set: set[str] = set(ids)
        if len(id_set) != len(ids):
            dup = sorted({i for i in ids if ids.count(i) > 1})
            result.add(f"Duplicate step IDs: {dup}.")

        # 2) 工具可用
        for s in plan.steps:
            if not s.id:
                result.add("Step has empty id.")
            if not s.tool:
                result.add(f"Step {s.id!r} has empty tool.")
            elif s.tool not in self.allowed_tools:
                result.add(
                    f"Step {s.id!r}: tool {s.tool!r} not in allowed tools. "
                    f"Allowed: {sorted(self.allowed_tools)}"
                )

        # 3) depends_on 合法性
        for s in plan.steps:
            for dep in s.depends_on:
                if dep == s.id:
                    result.add(f"Step {s.id!r}: self-dependency on {dep!r}.")
                elif dep not in id_set:
                    result.add(
                        f"Step {s.id!r}: depends_on {dep!r} which is not a declared step."
                    )

        # 4) 无环
        try:
            ts = graphlib.TopologicalSorter()
            for s in plan.steps:
                ts.add(s.id, *s.depends_on)
            ts.prepare()
        except graphlib.CycleError as e:
            cycle = e.args[1] if len(e.args) > 1 else e
            result.add(f"Plan contains a cycle: {cycle}")
        except Exception as e:  # 防御性，理论上不应发生
            result.add(f"Topological sort failed: {e}")

        # 5) 占位符 -> depends_on 一致性
        for s in plan.steps:
            placeholders = _find_placeholders(s.args_template)
            dep_set = set(s.depends_on)
            for ref_id, _path in placeholders:
                if ref_id not in id_set:
                    result.add(
                        f"Step {s.id!r}: placeholder references {ref_id!r} "
                        f"which is not a declared step."
                    )
                elif ref_id not in dep_set:
                    result.add(
                        f"Step {s.id!r}: placeholder uses {ref_id!r} "
                        f"but it is not in depends_on."
                    )

        return result


def _find_placeholders(obj: Any) -> list[tuple[str, str]]:
    """递归查找占位符，返回 ``[(step_id, path), ...]`` 。

    path 为空字符串表示占位符是 ``${sX}`` 整体引用 data 对象。
    """
    out: list[tuple[str, str]] = []
    if isinstance(obj, str):
        for m in _PLACEHOLDER_RE.finditer(obj):
            out.append((m.group(1), m.group(2) or ""))
    elif isinstance(obj, dict):
        for v in obj.values():
            out.extend(_find_placeholders(v))
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            out.extend(_find_placeholders(v))
    return out


def topological_order(plan: Plan) -> list[str]:
    """返回 plan 的拓扑排序 step id 列表。

    前置条件：plan 已通过 PlanValidator。存在环时抛出 ``graphlib.CycleError``。
    """
    ts = graphlib.TopologicalSorter()
    for s in plan.steps:
        ts.add(s.id, *s.depends_on)
    return list(ts.static_order())


def resolve_args(
    args_template: Any,
    observations: dict[str, dict[str, Any]],
) -> tuple[Any, list[str]]:
    """把 ``args_template`` 里的占位符替换为上游 observations 中的真实值。

    Args:
        args_template: 原始参数字典（也可能是嵌套 dict / list / str）
        observations: 以 step id 为键的 ``ToolResult.to_dict()`` 映射
            （成功步骤下 ``observations[sid]["data"]`` 就是该步的实际数据）

    Returns:
        ``(resolved_args, unresolved_placeholders)``。unresolved 非空表示执行
        阶段需要触发错误路由（通常走重规划）。

    占位符替换规则:

    - ``value == "${sX}"`` 或 ``"${sX.field}"`` 单独出现（fullmatch）→ 保留
      值的原始类型（可能是 list / dict / number）
    - 嵌入字符串内（如 ``"title: ${s1.slope}"``）→ 按 str() 拼接
    """
    unresolved: list[str] = []
    resolved = _resolve(args_template, observations, unresolved)
    return resolved, unresolved


def _resolve(obj: Any, obs: dict[str, dict[str, Any]], unresolved: list[str]) -> Any:
    if isinstance(obj, str):
        # 情况 1：整个字符串就是一个占位符，返回原始类型
        m = _PLACEHOLDER_RE.fullmatch(obj)
        if m:
            ref, path = m.group(1), m.group(2)
            val = _lookup(ref, path or "", obs, unresolved)
            return val if val is not None else obj

        # 情况 2：嵌入式占位符，按 str 替换
        def _sub(m: re.Match[str]) -> str:
            ref, path = m.group(1), m.group(2) or ""
            val = _lookup(ref, path, obs, unresolved)
            return "" if val is None else str(val)

        return _PLACEHOLDER_RE.sub(_sub, obj)
    if isinstance(obj, dict):
        return {k: _resolve(v, obs, unresolved) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_resolve(v, obs, unresolved) for v in obj]
    return obj


def _lookup(
    ref_id: str,
    path: str,
    obs: dict[str, dict[str, Any]],
    unresolved: list[str],
) -> Any:
    """按 ``ref_id.path`` 在 observations 中取值；失败时往 unresolved 追加诊断。"""
    entry = obs.get(ref_id)
    if not entry or not entry.get("success"):
        tag = f"${{{ref_id}{'.' + path if path else ''}}}"
        unresolved.append(f"{tag}: step not executed or failed.")
        return None
    data = entry.get("data")
    if not path:
        return data
    cursor: Any = data
    for seg in path.split("."):
        seg_stripped = seg.strip()
        if isinstance(cursor, dict):
            if seg_stripped in cursor:
                cursor = cursor[seg_stripped]
            else:
                unresolved.append(
                    f"${{{ref_id}.{path}}}: field {seg_stripped!r} missing "
                    f"in {list(cursor.keys())}."
                )
                return None
        elif isinstance(cursor, (list, tuple)):
            try:
                idx = int(seg_stripped)
            except ValueError:
                unresolved.append(
                    f"${{{ref_id}.{path}}}: segment {seg_stripped!r} "
                    f"is not an int index."
                )
                return None
            if 0 <= idx < len(cursor):
                cursor = cursor[idx]
            else:
                unresolved.append(
                    f"${{{ref_id}.{path}}}: index {idx} out of range."
                )
                return None
        else:
            unresolved.append(
                f"${{{ref_id}.{path}}}: cannot index into {type(cursor).__name__}."
            )
            return None
    return cursor


__all__: list[str] = [
    "PlanStep",
    "Plan",
    "ValidationResult",
    "PlanValidator",
    "parse_plan",
    "topological_order",
    "resolve_args",
]
