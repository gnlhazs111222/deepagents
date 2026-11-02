"""Ch09 HITL 实验公共组件：教学工具、Agent 装配、暂停检查助手。

与 sixth_memory 相同的模型装配；工具只写入内存列表，不发真实邮件。
"""

from __future__ import annotations

import json
import os
from copy import deepcopy

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model

from deepagents import create_deep_agent
from langchain.tools import tool
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv()


def build_model():
    provider = (os.getenv("AGENTSEEK_MODEL_PROVIDER") or "openai").strip().lower()
    raw = (
        os.getenv("AGENTSEEK_MODEL")
        or os.getenv("DEEPAGENTS_MODEL")
        or "deepseek-ai/DeepSeek-V3.2"
    )
    model_name = raw.split(":", 1)[1] if ":" in raw else raw
    kwargs: dict = {"model": model_name, "model_provider": provider}
    if provider == "openai":
        if os.getenv("OPENAI_API_KEY"):
            kwargs["api_key"] = os.getenv("OPENAI_API_KEY").strip()
        if os.getenv("OPENAI_API_BASE"):
            kwargs["base_url"] = os.getenv("OPENAI_API_BASE").strip()
    elif provider == "anthropic":
        if os.getenv("ANTHROPIC_API_KEY"):
            kwargs["api_key"] = os.getenv("ANTHROPIC_API_KEY").strip()
        if os.getenv("ANTHROPIC_API_URL"):
            kwargs["base_url"] = os.getenv("ANTHROPIC_API_URL").strip()
    return init_chat_model(**kwargs)


ORIGINAL_ARGS = {
    "to": "all@example.com",
    "subject": "上线通知",
    "body": "测试与构建已通过，计划明天上线。",
}


def make_tools(records: list):
    """教学工具：只往 records 追加执行记录，便于核对执行次数与实际参数。"""

    @tool
    def send_email(to: str, subject: str, body: str) -> str:
        """记录教学邮件的收件人、主题和正文，不发送真实邮件。"""
        args = {"to": to, "subject": subject, "body": body}
        records.append({"name": "send_email", "args": args})
        return json.dumps(args, ensure_ascii=False)

    @tool
    def ask_user(question: str) -> str:
        """提出需要人类回答的问题；通过 HITL respond 提供真实回答。"""
        records.append({"name": "ask_user", "args": {"question": question}})
        return "占位工具已运行，尚未取得用户回答。"

    return [send_email, ask_user]


DEFAULT_INTERRUPT_ON = {
    "send_email": {"allowed_decisions": ["approve", "edit", "reject"]},
    "ask_user": {"allowed_decisions": ["respond"]},
}

SYSTEM_PROMPT = (
    "你是上线通知助手。用户要求发邮件时，必须调用 send_email 工具，"
    "收件人、主题、正文严格按用户给出的参数，不要改动、不要用其他方式发送。"
    "用户要求向你提问收集信息时，调用 ask_user 提出问题，一次只问一个。"
    "收到工具结果或审批反馈后，总结并结束，不要再次调用工具。"
    "教学邮件只记录参数，不是真实邮件服务。"
)


def build_agent(records: list, interrupt_on: dict | None = None, system_prompt: str = SYSTEM_PROMPT):
    return create_deep_agent(
        model=build_model(),
        tools=make_tools(records),
        checkpointer=InMemorySaver(),
        interrupt_on=interrupt_on or DEFAULT_INTERRUPT_ON,
        system_prompt=system_prompt,
    )


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"    [{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
    return ok


def print_tool_calls(result) -> None:
    for m in result.value["messages"] if hasattr(result, "value") else result["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            print(f"    [工具调用] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:120]})")
        if getattr(m, "type", None) == "tool":
            text = m.content if isinstance(m.content, str) else str(m.content)
            print(f"    [工具返回] {m.name} status={m.status} -> {text[:150]}")


def get_pause(result):
    """返回 (是否暂停, action_requests, review_configs)。v2 结果专用。"""
    if not getattr(result, "interrupts", None):
        return False, [], []
    payload = result.interrupts[0].value
    return True, payload["action_requests"], payload["review_configs"]


def show_pause(result, records: list) -> bool:
    paused, actions, reviews = get_pause(result)
    if not paused:
        print("    [WARN] 没有产生审批中断——模型可能没有提出工具调用，看下面的消息历史。")
        print_tool_calls(result)
        return False
    for i, (action, review) in enumerate(zip(actions, reviews), start=1):
        print(f"    待审批动作 {i}: {action['name']} 参数={json.dumps(action['args'], ensure_ascii=False)}")
        print(f"      允许决策: {', '.join(review['allowed_decisions'])}")
    print(f"    工具执行次数: {len(records)} (应为 0 —— 模型提出了请求，但工具还没运行)")
    return True
