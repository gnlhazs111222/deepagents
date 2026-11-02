"""Ch09 实验: 批量审批(按顺序配对决策) + 决策数量不匹配的真实报错。

运行方式(项目根目录):
    uv run --frozen python agent_test/seventh_hitl/03_batch_and_invalid.py

场景 A: 模型同一条消息提出两封邮件 → 一个中断打包两项待审批。
        approve 第一项、reject 第二项，按 action_requests 顺序配对。
场景 B: 同样两项待审批，只提交一项决策 → 框架抛 ValueError，工具零执行。
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


def start_batch(thread_id: str):
    """让模型给 team 和 all 各发一封通知邮件，返回 (records, agent, config, paused)。"""
    records: list = []
    agent = build_agent(records)
    config = {"configurable": {"thread_id": thread_id}}
    instruction = (
        "请发送两封上线通知邮件，在同一条消息里提出：\n"
        f"第一封收件人 team@example.com，主题「{ORIGINAL_ARGS['subject']}」，正文「{ORIGINAL_ARGS['body']}」；\n"
        f"第二封收件人 {ORIGINAL_ARGS['to']}，主题和正文与第一封相同。"
    )
    paused = agent.invoke(
        {"messages": [{"role": "user", "content": instruction}]},
        config=config, version="v2",
    )
    return records, agent, config, paused


def main() -> None:
    # ---------- 场景 A: 批量审批 ----------
    print("===== 场景 A: 两项待审批，approve + reject =====")
    records, agent, config, paused = start_batch("ch09-batch")
    if show_pause(paused, records):
        BATCH_REASON = "只通知项目组，取消全员通知，不要重试。"
        result = agent.invoke(
            Command(resume={"decisions": [
                {"type": "approve"},
                {"type": "reject", "message": BATCH_REASON},
            ]}),
            config=config, version="v2",
        )
        print_tool_calls(result)
        executed_to = [r["args"]["to"] for r in records]
        check("只有第一封(team)实际执行", executed_to == ["team@example.com"],
              f"执行记录: {executed_to}")
        replies = [m for m in result.value["messages"] if m.type == "tool"]
        check("第二封收到拒绝反馈(error ToolMessage)",
              any(m.status == "error" and BATCH_REASON in str(m.content) for m in replies))

    # ---------- 场景 B: 数量不匹配 ----------
    print("\n===== 场景 B: 两项待审批只提交一项决策(预期 ValueError) =====")
    records, agent, config, paused = start_batch("ch09-invalid")
    if show_pause(paused, records):
        try:
            agent.invoke(
                Command(resume={"decisions": [{"type": "approve"}]}),
                config=config, version="v2",
            )
        except ValueError as error:
            check("框架拒绝恢复并报数量不匹配", "does not match" in str(error),
                  str(error)[:120])
        else:
            check("框架拒绝恢复并报数量不匹配", False, "没有抛出 ValueError")
        check("校验失败时工具零执行", records == [], f"执行记录: {records}")

    print("\n===== 结论 =====")
    print("批量中断的 decisions 与 action_requests 按位置一一配对；")
    print("数量不匹配在恢复入口就被拒绝，此时工具尚未执行。")


if __name__ == "__main__":
    main()
