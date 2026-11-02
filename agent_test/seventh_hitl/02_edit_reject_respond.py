"""Ch09 实验: edit / reject / respond 三种决策的对照。

运行方式(项目根目录):
    uv run --frozen python agent_test/seventh_hitl/02_edit_reject_respond.py

三个独立 Agent + 独立 thread，互不影响:
  - edit   : 把收件人改成 team@example.com，验证实际执行的是新参数
  - reject : 拒绝发送，验证工具零执行 + 拒绝原因进入 error 的 ToolMessage
  - respond: ask_user 占位工具不执行，人的回答原样成为 success 工具结果
"""

from __future__ import annotations

from langgraph.types import Command

from common import (
    ORIGINAL_ARGS,
    build_agent,
    check,
    print_tool_calls,
    show_pause,
)

EMAIL_INSTRUCTION = (
    f"请发送一封上线通知邮件。收件人 {ORIGINAL_ARGS['to']}，"
    f"主题「{ORIGINAL_ARGS['subject']}」，正文「{ORIGINAL_ARGS['body']}」。"
)


def run_case(title: str, thread_id: str, instruction: str, decisions: list):
    records: list = []
    agent = build_agent(records)
    config = {"configurable": {"thread_id": thread_id}}
    print(f"\n===== {title} =====")
    paused = agent.invoke(
        {"messages": [{"role": "user", "content": instruction}]},
        config=config, version="v2",
    )
    if not show_pause(paused, records):
        return records, None
    result = agent.invoke(Command(resume={"decisions": decisions}), config=config, version="v2")
    print_tool_calls(result)
    print(f"    [最终回答] {result.value['messages'][-1].text()[:180]}")
    return records, result


def main() -> None:
    # ---------- edit ----------
    EDITED_TO = "team@example.com"
    edited_args = {**ORIGINAL_ARGS, "to": EDITED_TO}
    records, _ = run_case(
        "决策 1: edit —— 改收件人再执行", "ch09-edit", EMAIL_INSTRUCTION,
        [{"type": "edit", "edited_action": {"name": "send_email", "args": edited_args}}],
    )
    check("实际执行的是修改后的收件人", records and records[0]["args"]["to"] == EDITED_TO,
          f"执行记录: {records}")
    check("原请求的收件人没有被执行", records and records[0]["args"]["to"] != ORIGINAL_ARGS["to"])

    # ---------- reject ----------
    REJECT_REASON = "用户拒绝发送，请只保留草稿，不要重试发送。"
    records, result = run_case(
        "决策 2: reject —— 工具不执行", "ch09-reject", EMAIL_INSTRUCTION,
        [{"type": "reject", "message": REJECT_REASON}],
    )
    check("工具零执行(副作用没有发生)", records == [], f"执行记录: {records}")
    replies = [m for m in result.value["messages"] if m.type == "tool"] if result else []
    reject_reply = [m for m in replies if m.status == "error"]
    check("拒绝原因完整反馈给模型(error 的 ToolMessage)",
          bool(reject_reply) and REJECT_REASON in str(reject_reply[0].content),
          reject_reply[0].content[:100] if reject_reply else "(没找到 error 工具消息)")

    # ---------- respond ----------
    HUMAN_ANSWER = "按季度汇总，并排除测试数据。"
    records, result = run_case(
        "决策 3: respond —— 人的回答代替占位工具", "ch09-respond",
        "你想确认报告的汇总方式。请调用 ask_user 问用户：报告按月还是按季度汇总？",
        [{"type": "respond", "message": HUMAN_ANSWER}],
    )
    check("ask_user 占位函数没有执行", records == [], f"执行记录: {records}")
    replies = [m for m in result.value["messages"] if m.type == "tool"] if result else []
    answer_reply = [m for m in replies if m.status == "success"]
    check("人的回答原样成为 success 工具结果",
          bool(answer_reply) and HUMAN_ANSWER in str(answer_reply[0].content),
          answer_reply[0].content[:100] if answer_reply else "(没找到 success 工具消息)")

    print("\n===== 结论 =====")
    print("edit 改变实际参数；reject 零执行 + 原因反馈；respond 不运行工具、人即结果。")
    print("副作用工具(删除/发送)拒绝时用 reject，不要用 respond。")


if __name__ == "__main__":
    main()
