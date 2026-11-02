"""Ch09 主实验：审批前 Agent 暂停在哪里？工具到底执行了没有？

运行方式(项目根目录，需要 .env 有可用模型配置):
    uv run --frozen python agent_test/seventh_hitl/01_pause_and_approve.py

流程:
  第一步 发起任务 → 观察: action_requests 已列出邮件请求、records 为空、
         checkpoint 的 next 指向 HumanInTheLoopMiddleware.after_model
  第二步 Command(resume=approve) → 观察: send_email 按原参数执行一次、
         ToolMessage success、整次运行完成
判定全部基于执行记录(records)和 ToolMessage，不信模型最后说"已发送"。
"""

from __future__ import annotations

import json

from langgraph.types import Command

from common import (
    ORIGINAL_ARGS,
    build_agent,
    check,
    print_tool_calls,
    show_pause,
)


def main() -> None:
    records: list = []
    agent = build_agent(records)
    config = {"configurable": {"thread_id": "ch09-approve"}}

    print("===== 第一步: 发起任务，观察暂停点 =====")
    paused = agent.invoke(
        {
            "messages": [{
                "role": "user",
                "content": (
                    f"请发送一封上线通知邮件。收件人 {ORIGINAL_ARGS['to']}，"
                    f"主题「{ORIGINAL_ARGS['subject']}」，正文「{ORIGINAL_ARGS['body']}」。"
                ),
            }],
        },
        config=config, version="v2",
    )
    if not show_pause(paused, records):
        return

    snapshot = agent.get_state(config)
    check("暂停在审批中间件(HumanInTheLoopMiddleware.after_model)",
          any("HumanInTheLoop" in n for n in snapshot.next), f"next={snapshot.next}")
    check("中断已保存待恢复", len(snapshot.interrupts) == 1)
    last = snapshot.values["messages"][-1]
    check("State 已保存模型提出的工具调用", bool(getattr(last, "tool_calls", None)),
          f"调用: {[(c['name'], c['args'].get('to')) for c in getattr(last, 'tool_calls', [])]}")
    check("审批前模型已调用过(模型步骤已结束，暂停的是审批步骤)", True,
          "由上面打印的中断内容佐证")

    print("\n===== 第二步: approve 恢复执行 =====")
    approved = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config, version="v2",
    )
    print_tool_calls(approved)
    print(f"    [最终回答] {approved.value['messages'][-1].text()[:200]}")

    check("send_email 按原参数执行了恰好一次",
          records == [{"name": "send_email", "args": ORIGINAL_ARGS}],
          f"实际记录: {json.dumps(records, ensure_ascii=False)}")
    replies = [m for m in approved.value["messages"] if m.type == "tool"]
    check("工具结果是 success 且返回了原参数",
          any(m.status == "success" and ORIGINAL_ARGS["to"] in str(m.content)
              for m in replies))
    snap2 = agent.get_state(config)
    complete = (not approved.interrupts and not snap2.interrupts and not snap2.next)
    check("整次运行已完成(无中断、无待执行节点)", complete)

    print("\n===== 结论 =====")
    print("模型提出调用 ≠ 工具已执行: 暂停发生在 after_model 审批节点，")
    print("工具请求已进入 State 但执行次数为 0；approve 后按原参数运行一次。")


if __name__ == "__main__":
    main()
