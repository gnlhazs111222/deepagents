"""综合 Demo 变体：HITL 的 edit 决策 —— 人工改掉发布参数后按新参数执行。

运行方式(项目根目录):
    uv run --frozen python agent_test/capstone_demo/02_hitl_edit.py

复用与 01_end_to_end.py 完全相同的 build_demo_agent（同一个应用），
只把 resume 决策从 approve 换成 edit：改 headline 后验证
实际执行的 publish_report 用的是修改后的参数，且只执行一次。
"""

from __future__ import annotations

import json

from langgraph.types import Command

from common import (
    REPORT_PATH,
    build_demo_agent,
    check,
    get_pause,
)

TASK_INSTRUCTION = (
    "调研 DeepAgents 的子代理机制，按你的报告规范写好报告并发布。"
    "（本条不涉及偏好记忆。）"
)

EDITED_HEADLINE = "【编辑版】DeepAgents 子代理机制审阅报告"


def main() -> None:
    records: list = []
    agent, _store, skill_tmp = build_demo_agent(records)
    config = {"configurable": {"thread_id": "capstone-edit"}}

    print("===== 第一步：发起任务，等待发布审批 =====")
    paused = agent.invoke(
        {"messages": [{"role": "user", "content": TASK_INSTRUCTION}]},
        config=config, version="v2",
    )
    paused_flag, actions, _reviews = get_pause(paused)
    if not paused_flag:
        print("    [中止] 没有产生审批中断，看上一条实验的排查思路。")
        return
    original_headline = actions[0]["args"].get("headline", "")
    print(f"    待审批动作: publish_report(headline={original_headline!r})")
    check("审批前工具执行次数为 0", not records)

    print("\n===== 第二步：edit 决策 —— 人工改 headline 后恢复 =====")
    resumed = agent.invoke(
        Command(resume={"decisions": [{
            "type": "edit",
            "edited_action": {"name": "publish_report",
                              "args": {"path": REPORT_PATH,
                                       "headline": EDITED_HEADLINE}},
        }]}),
        config=config, version="v2",
    )
    check("实际执行的是修改后的 headline，且恰好一次",
          len(records) == 1 and records[0]["args"]["headline"] == EDITED_HEADLINE,
          f"执行记录: {json.dumps(records, ensure_ascii=False)}")

    print("\n===== 结论 =====")
    print("edit 决策由中间件改写工具参数后再执行：人改的不是聊天记录，")
    print("而是真正落进工具的那份 args —— 这就是 HITL 的兜底价值。")
    skill_tmp.cleanup()


if __name__ == "__main__":
    main()
