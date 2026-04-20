"""端到端演示脚本：跑 3 个示例任务，验证 ReAct Agent 全链路。

运行方式（在项目根目录）：
    .venv\\Scripts\\activate
    python demos/try_agent.py

脚本会消耗真实的 LLM 额度（约 5-15 次调用 / 任务）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Windows PowerShell 默认 GBK，模型返回的中文 thought 在 print 时容易触发 UnicodeEncodeError。
# 这里把 stdout/stderr 重配为 UTF-8，并把无法编码的字符替换为占位符，保证 demo 不会因打印崩溃。
for _stream_name in ("stdout", "stderr"):
    _stream = getattr(sys, _stream_name, None)
    if _stream is not None and hasattr(_stream, "reconfigure"):
        try:
            _stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

# 让脚本直接 python demos/try_agent.py 运行时也能 import src.*
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.agent import ReActAgent  # noqa: E402
from src.tools import build_all_tools  # noqa: E402


TASKS: list[str] = [
    # 1. 简单：描述性统计 + 柱状图
    "I have a small dataset: [1.2, 3.4, 5.6, 7.8, 2.3, 9.1]. "
    "Please compute the mean and standard deviation, and also plot a bar chart of the values.",

    # 2. 多步：线性回归 + 带拟合线散点图
    "Here are two arrays: x = [1, 2, 3, 4, 5] and y = [2.1, 3.9, 6.2, 8.1, 9.8]. "
    "Run a linear regression to get the slope and intercept, then draw a scatter plot with the fitted line overlaid.",

    # 3. 复合：数值积分 + 与解析值比较
    "Please numerically integrate sin(x) over the interval [0, pi], "
    "then compare the numerical result with the analytic value 2.0 and report the absolute error.",
]


def _truncate(text: str, limit: int = 200) -> str:
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def run_one(idx: int, task: str, agent: ReActAgent) -> None:
    print("=" * 80)
    print(f"Task #{idx}: {task}")
    print("-" * 80)

    result = agent.run(task)

    print(f"Stopped reason : {result.stopped_reason}")
    print(f"Iterations used: {result.iterations_used}")
    print(f"Trajectory     : {len(result.trajectory)} step(s)")
    print()
    print("--- Trajectory ---")
    for step in result.trajectory:
        print(" ", step.summary())
        if step.thought:
            print(f"    thought : {_truncate(step.thought, 180)}")
        if step.tool_name is not None:
            print(f"    args    : {_truncate(json.dumps(step.tool_arguments, ensure_ascii=False), 180)}")
            obs = step.observation or {}
            if obs.get("success"):
                data_str = json.dumps(obs.get("data"), ensure_ascii=False)
                print(f"    data    : {_truncate(data_str, 180)}")
            else:
                print(f"    error   : {_truncate(obs.get('error', ''), 180)}")

    print()
    print("--- Final answer ---")
    print(result.final_answer)
    print()


def main() -> None:
    print("Building tools and agent...")
    tools = build_all_tools()
    agent = ReActAgent(tools=tools, max_iterations=10, verbose=False)
    print(f"Registered {len(tools)} tool(s): {[t.name for t in tools]}")
    print()

    for idx, task in enumerate(TASKS, start=1):
        try:
            run_one(idx, task, agent)
        except Exception as e:
            print(f"Task #{idx} crashed: {type(e).__name__}: {e}")
            print()

    print("=" * 80)
    print("All demo tasks finished.")


if __name__ == "__main__":
    main()
