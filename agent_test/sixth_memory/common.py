"""Ch08 长期记忆实验的公共组件：模型、Agent 装配、请求记录器、打印工具。

四个实验脚本（01~04）共用这里的东西，各自只改一个变量。
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.utils import create_file_data
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

load_dotenv()


def build_model():
    """与 fifth_skills 实验相同的模型装配，读 .env 里的配置。"""
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


MEMORY_PATH = "/memories/preferences.md"
DRAFT_PATH = "/draft.md"
ALICE_NS = ("alice", "memories")
BOB_NS = ("bob", "memories")

# 预置偏好：Alice 空、Bob 已有一条 —— memory=[...] 只读已有文件，不自动创建
ALICE_INITIAL = {}
BOB_INITIAL = {"comment_language": "en", "variable_language": "zh"}


def preset_store(store: InMemoryStore) -> None:
    store.put(ALICE_NS, "/preferences.md", create_file_data(json.dumps(ALICE_INITIAL, ensure_ascii=False)))
    store.put(BOB_NS, "/preferences.md", create_file_data(json.dumps(BOB_INITIAL, ensure_ascii=False)))


@dataclass
class UserContext:
    user_id: str


def make_namespace_fn(fixed_user_id: str | None = None):
    """返回 namespace 工厂；传 fixed_user_id 则固定（练习 04 用）。"""
    def namespace(rt):
        if fixed_user_id is not None:
            return (fixed_user_id, "memories")
        return (rt.context.user_id, "memories")
    return namespace


def build_agent(namespace_fn, system_prompt: str, store: InMemoryStore | None = None):
    """装配 Agent；不传 store 则内部新建。需要事后查 Store 内容时用
    build_agent_and_store()。"""
    return create_deep_agent(
        model=build_model(),
        store=store or InMemoryStore(),
        checkpointer=InMemorySaver(),
        context_schema=UserContext,
        memory=[MEMORY_PATH],
        backend=CompositeBackend(
            default=StateBackend(),
            routes={"/memories/": StoreBackend(namespace=namespace_fn)},
        ),
        system_prompt=system_prompt,
    )


def build_agent_and_store(namespace_fn, system_prompt: str):
    """装配 Agent 并同时返回它用的 Store，方便实验后直接核对写入内容。"""
    store = InMemoryStore()
    return build_agent(namespace_fn, system_prompt, store=store), store


SYSTEM_PROMPT = (
    "你是一个偏好感知的写作助手。规则：\n"
    f"1. 当用户要求保存/更新代码风格偏好时：先用 read_file 读取 {MEMORY_PATH}，"
    "再用 edit_file 更新它。edit_file 的 old_string 和 new_string 必须是纯字符串，"
    "不要传 JSON 对象。更新时把整个文件内容替换为完整的 JSON 偏好对象，"
    "保留用户已有的其他偏好字段，不要另建文件。\n"
    "2. 只有写入工具返回成功后，才告诉用户已记住。\n"
    "3. 用户要求写/读草稿时，直接用 write_file / read_file 操作 /draft.md。\n"
    "4. 回答问题或写代码时，遵守已注入的偏好。"
)


class ModelRequestRecorder(BaseCallbackHandler):
    """记录每次发给模型的请求，用于验证 memory 是否真的注入了系统提示词。"""

    def __init__(self) -> None:
        self.systems: list[str] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        for group in messages:
            for m in group:
                if isinstance(m, SystemMessage):
                    self.systems.append(m.text())
                    return

    def memory_injection(self) -> str:
        """从首次 SystemMessage 中截取 <agent_memory> 块里的偏好正文。"""
        if not self.systems:
            return "(没有捕获到任何模型请求)"
        system = self.systems[0]
        match = re.search(r"<agent_memory>(.*?)</agent_memory>", system, re.S)
        block = match.group(1) if match else "(系统提示词中没有 <agent_memory> 块)"
        # 只保留 preferences.md 相关的片段，方便人眼对照
        if MEMORY_PATH in block:
            return block[block.index(MEMORY_PATH):][:500]
        return block[:500]


def print_tool_calls(result: dict) -> None:
    """打印本轮 Agent 实际执行的工具调用和返回，这是判定的实物证据。"""
    for m in result["messages"]:
        for tc in getattr(m, "tool_calls", None) or []:
            print(f"    [工具调用] {tc['name']}({json.dumps(tc['args'], ensure_ascii=False)[:120]})")
        if m.type == "tool":
            text = m.content if isinstance(m.content, str) else str(m.content)
            print(f"    [工具返回] {m.name} -> {text[:150]}")
