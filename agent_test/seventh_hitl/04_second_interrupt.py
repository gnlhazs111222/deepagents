"""Ch09 实验: 同一会话的第二次中断 —— 第一回答已生效 ≠ 整次运行已完成。

运行方式(项目根目录):
    uv run --frozen python agent_test/seventh_hitl/04_second_interrupt.py

流程(同一个 Agent、同一个 thread_id):
  1. 让模型调用 ask_user 问第一个问题 → respond 回答
  2. 检查本批效果(第一回答已生效)，但观察 snapshot.next 与中断:
     整次运行可能仍在等待第二个问题的审批
  3. 提交第二回答，验收整次完成，且 ask_user 占位函数始终零执行
"""

from __future__ import annotations

from langgraph.types import Command

from common import (
    build_agent,
    check,
    print_tool_calls,
    show_pause,
)

FIRST_ANSWER = "按季度汇总，并排除测试数据。"
SECOND_ANSWER = "输出 PDF，附上明细表格。"


def main() -> None:
    records: list = []
    agent = build_agent(records)
    config = {"configurable": {"thread_id": "ch09-followup"}}
    instruction = (
        "你要帮我确认报告的两个需求，必须用 ask_user 逐个提问，一次只问一个：\n"
        "先问：报告按月还是按季度汇总？\n"
        "收到回答后，再问：报告输出 PDF 还是表格？\n"
        "收到两个回答后总结并结束。"
    )

    print("===== 第一轮: 第一个问题的审批 =====")
    paused = agent.invoke(
        {"messages": [{"role": "user", "content": instruction}]},
        config=config, version="v2",
    )
    if not show_pause(paused, records):
        return

    print("\n===== respond 第一回答 =====")
    result = agent.invoke(
        Command(resume={"decisions": [{"type": "respond", "message": FIRST_ANSWER}]}),
        config=config, version="v2",
    )
    print_tool_calls(result)
    replies = [m for m in result.value["messages"] if m.type == "tool"]
    check("第一回答已成为 success 工具结果",
          any(m.status == "success" and FIRST_ANSWER in str(m.content) for m in replies))
    check("ask_user 占位函数始终零执行", records == [])

    snapshot = agent.get_state(config)
    complete = (not result.interrupts and not snapshot.interrupts and not snapshot.next)
    if complete:
        print("    [INFO] 模型一次问完了，没有第二次中断(真实模型行为有随机性)。实验到此结束。")
        return

    print("\n===== 观察: 第一回答已生效，但整次运行仍在等待 =====")
    check("仍有待执行节点(第二次审批)", bool(snapshot.next), f"next={snapshot.next}")
    check("仍有待解决中断", len(snapshot.interrupts) == 1)
    for pending in snapshot.interrupts:
        for action in pending.value["action_requests"]:
            print(f"    待审批动作: {action['name']} 参数={action['args']}")
    print("    >>> 本批决策效果已通过，但整次运行未完成 —— 两个判断要分开。")

    print("\n===== respond 第二回答 =====")
    final = agent.invoke(
        Command(resume={"decisions": [{"type": "respond", "message": SECOND_ANSWER}]}),
        config=config, version="v2",
    )
    print_tool_calls(final)
    print(f"    [最终回答] {final.value['messages'][-1].text()[:200]}")
    replies = [m for m in final.value["messages"] if m.type == "tool"]
    check("两轮回答都成为工具结果",
          all(any(ANS in str(m.content) for m in replies)
              for ANS in (FIRST_ANSWER, SECOND_ANSWER)))
    snap2 = agent.get_state(config)
    check("整次运行已完成",
          not final.interrupts and not snap2.interrupts and not snap2.next)
    check("ask_user 占位函数仍然零执行", records == [])

    print("\n===== 结论 =====")
    print("同一会话可以多次中断；每次 resume 只解决当前一批待审批动作，")
    print("『本批生效』和『整次完成』是两个判断，后者要查 snapshot.next 与中断。")


if __name__ == "__main__":
    main()
