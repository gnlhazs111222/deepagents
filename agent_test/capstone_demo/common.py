"""综合 Demo 公共组件：把课程多项能力装进同一个"报告发布工作流"应用。

能力清单（对应课程章节）：
  - Context Engineering（ch06/pre01）：报告长文 write_file 进 state 的 files 层，
    不整篇塞回上下文；搜索结果超长时框架自动落盘换纸条。
  - Skills（ch07）：/skills/report-style/ 下的报告规范技能，渐进式披露，
    Agent 判断相关后自行 read_file SKILL.md → references/structure.md。
  - Subagents（ch04/ch05）：research-agent 子代理负责检索，主代理负责汇总写作。
  - Long-term Memory（ch08）：/memories/ 路由到 StoreBackend，按用户 namespace
    跨线程常驻，memory=[...] 自动注入系统提示词。
  - HITL（ch09）：publish_report 挂 interrupt_on，发布前必须人工 approve/edit/reject。

检索默认用离线语料（CAPSTONE_LIVE_SEARCH=1 时换真实 Tavily，需网络与 key），
保证 Demo 可复现、不烧配额。模型装配与 seventh_hitl 相同（.env 配置）。
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain.tools import tool
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from deepagents.backends.filesystem import FilesystemBackend
from deepagents.backends.utils import create_file_data

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


# ---------------------------------------------------------------------------
# 检索工具：默认离线语料，可切真实 Tavily
# ---------------------------------------------------------------------------

CORPUS = [
    {
        "url": "https://example.com/deepagents-overview",
        "title": "DeepAgents 框架总览",
        "content": (
            "DeepAgents 是基于 LangGraph 的深度代理框架，核心由四层组成："
            "上下文层（消息数组 + 超长结果落盘 + 85% 摘要压缩）、"
            "state 层（messages/todos/files 三键字典）、"
            "backend 层（StateBackend/StoreBackend/CompositeBackend 可换零件）、"
            "中间件层（TodoList、HITL、Summarization、Rubric 等挂件）。"
        ),
    },
    {
        "url": "https://example.com/deepagents-subagents",
        "title": "DeepAgents 子代理机制",
        "content": (
            "主代理通过 task 工具把单一话题委托给子代理。子代理默认栈不含 "
            "TodoListMiddleware，且 messages/todos 双向隔离，只共享 files 层；"
            "主代理拿回的是子代理的最终报告而非全过程。"
        ),
    },
    {
        "url": "https://example.com/deepagents-hitl",
        "title": "DeepAgents 人机协同（HITL）",
        "content": (
            "interrupt_on 配置让工具在执行前暂停，产出 action_requests 等人工决策；"
            "支持 approve/edit/reject/respond 四种决策，通过 Command(resume=...) 恢复。"
            "模型提出调用不等于工具已执行，审批发生在 after_model 节点。"
        ),
    },
]


def _format_results(query: str, results: list[dict]) -> str:
    return (
        f"🔍 Found {len(results)} result(s) for '{query}':\n\n"
        + "\n".join(
            f"## {r['title']}\n**URL:** {r['url']}\n\n{r['content']}\n\n---\n"
            for r in results
        )
    )


def make_search_tools(records: list):
    """返回 (mock_search, live_search)。live 版仅在 CAPSTONE_LIVE_SEARCH=1 时使用。"""

    @tool
    def mock_search(query: str) -> str:
        """Search the offline demo corpus for information about DeepAgents."""
        records.append({"name": "mock_search", "args": {"query": query}})
        if "deepagent" in query.lower() or "代理" in query or "DeepAgents" in query:
            return _format_results(query, CORPUS)
        return _format_results(query, [])

    try:
        from research_deepagent.tools import tavily_search as _live
    except Exception:
        _live = None

    if _live is not None:
        return mock_search, _live
    return mock_search, None


@tool
def think_tool(reflection: str) -> str:
    """Record a short reflection on research progress before writing the report."""
    return f"Reflection recorded: {reflection}"


def make_publish_tool(records: list):
    @tool
    def publish_report(path: str, headline: str) -> str:
        """Publish the report file at `path` with the given headline. Requires human approval."""
        args = {"path": path, "headline": headline}
        records.append({"name": "publish_report", "args": args})
        return json.dumps({"published": True, **args}, ensure_ascii=False)

    return publish_report


# ---------------------------------------------------------------------------
# Skill 材料：报告规范（渐进式披露的两级文件）
# ---------------------------------------------------------------------------

SKILL_PATH = "/skills/report-style/SKILL.md"
STRUCTURE_PATH = "/skills/report-style/references/structure.md"

SKILL_BODY = f"""---
name: report-style
description: 当用户要求撰写或发布研究报告时,读取本技能并严格按规范组织报告结构。
---
# 研究报告规范
1. 使用 read_file 读取 `{STRUCTURE_PATH}` 获取必需章节。
2. 报告必须包含结构文件里列出的每一个章节标题,顺序一致,不得增删。
3. 写完后把完整报告 write_file 到 /final_report.md,再调用 publish_report。
"""

STRUCTURE_BODY = """# 报告必需章节（顺序固定）
# <标题>
## 摘要
## 关键发现
## 来源
"""


def make_skill_backend() -> tuple[FilesystemBackend, tempfile.TemporaryDirectory]:
    """把技能文件写进临时目录并挂成 FilesystemBackend（virtual 模式，路径以 / 开头）。"""
    tmp = tempfile.TemporaryDirectory(prefix="capstone_skills_")
    root = Path(tmp.name)
    skill_file = root / "skills" / "report-style" / "SKILL.md"
    ref_file = root / "skills" / "report-style" / "references" / "structure.md"
    skill_file.parent.mkdir(parents=True, exist_ok=True)
    ref_file.parent.mkdir(parents=True, exist_ok=True)
    skill_file.write_text(SKILL_BODY, encoding="utf-8")
    ref_file.write_text(STRUCTURE_BODY, encoding="utf-8")
    return FilesystemBackend(root_dir=str(root), virtual_mode=True), tmp


# ---------------------------------------------------------------------------
# 长期记忆与 Agent 装配
# ---------------------------------------------------------------------------

MEMORY_PATH = "/memories/preferences.md"
USER_NS = ("demo-user", "memories")
REPORT_PATH = "/final_report.md"

SUBAGENT_PROMPT = (
    "你是检索专员。只做一件事：用搜索工具围绕分配给你的单一话题检索，"
    "最多检索两轮；每轮后用 think_tool 简短复盘。最后把找到的要点和来源 URL "
    "汇总成清单返回，不要自己写正式报告。"
)

SYSTEM_PROMPT = (
    "你是研究报告发布助手，工作流固定为五步，一步一步来：\n"
    "1. 【检索】把调研话题委托给 research-agent 子代理（task 工具），一次委托即可，"
    "自己不要直接调搜索工具。\n"
    "2. 【规范】用户要求写报告时，先用 read_file 读取 " + SKILL_PATH + "，"
    "再按技能正文指引读取结构文件。\n"
    "3. 【写作】按结构文件要求的章节，把完整报告 write_file 到 " + REPORT_PATH + "。\n"
    "4. 【发布】调用 publish_report(path=" + REPORT_PATH + ", headline=报告标题)。"
    "该工具需要人工审批，审批被拒绝时不要重试，直接询问用户意见。\n"
    "5. 【收尾】总结执行情况后结束。\n"
    "偏好规则：当用户陈述了长期偏好（如语言、格式），先用 read_file 读取 "
    + MEMORY_PATH + "，再用 edit_file 把整个文件内容替换为完整 JSON 对象"
    "（保留已有字段）；只有写入成功后才说已记住。\n"
    "演示环境搜索是离线语料，检索不到时不要空转，直接基于已有材料写报告。"
)


class UserContext:
    def __init__(self, user_id: str = "demo-user"):
        self.user_id = user_id


def build_demo_agent(records: list, store: InMemoryStore | None = None):
    """装配综合 Demo 的唯一应用。返回 (agent, store, skill_tmpdir)。"""
    skill_backend, skill_tmp = make_skill_backend()
    if store is None:
        store = InMemoryStore()
    search_tool, live_search = make_search_tools(records)
    chosen_search = live_search if os.getenv("CAPSTONE_LIVE_SEARCH") == "1" else search_tool
    agent = create_deep_agent(
        model=build_model(),
        store=store,
        checkpointer=InMemorySaver(),
        context_schema=UserContext,
        memory=[MEMORY_PATH],
        backend=CompositeBackend(
            default=StateBackend(),
            routes={
                "/skills/": skill_backend,
                "/memories/": StoreBackend(namespace=lambda rt: (rt.context.user_id, "memories")),
            },
        ),
        tools=[chosen_search, think_tool, make_publish_tool(records)],
        system_prompt=SYSTEM_PROMPT,
        subagents=[{
            "name": "research-agent",
            "description": "把单一调研话题委托给检索专员，拿回要点和来源清单。",
            "system_prompt": SUBAGENT_PROMPT,
            "tools": [chosen_search, think_tool],
        }],
        interrupt_on={
            "publish_report": {"allowed_decisions": ["approve", "edit", "reject"]},
        },
    )
    return agent, store, skill_tmp


# ---------------------------------------------------------------------------
# 通用断言 / 打印助手（与之前各章同款）
# ---------------------------------------------------------------------------

def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"    [{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))
    return ok


def iter_tool_calls(result) -> list[tuple[str, dict]]:
    """从结果里抽出全部 (工具名, 参数)。兼容 v2 结果包装。"""
    messages = result.value["messages"] if hasattr(result, "value") else result["messages"]
    calls: list[tuple[str, dict]] = []
    for m in messages:
        for tc in getattr(m, "tool_calls", None) or []:
            calls.append((tc["name"], tc["args"]))
    return calls


def print_tool_calls(result) -> None:
    for name, args in iter_tool_calls(result):
        print(f"    [工具调用] {name}({json.dumps(args, ensure_ascii=False)[:120]})")


def get_pause(result):
    if not getattr(result, "interrupts", None):
        return False, [], []
    payload = result.interrupts[0].value
    return True, payload["action_requests"], payload["review_configs"]


def read_state_file(agent, config: dict, path: str) -> str | None:
    """从 checkpoint 的 state files 层取文件全文；不在则返回 None。"""
    files = agent.get_state(config).values.get("files", {})
    entry = files.get(path)
    if entry is None:
        return None
    content = entry.get("content") if isinstance(entry, dict) else entry
    return content if isinstance(content, str) else str(content)


class MemoryRecorder(BaseCallbackHandler):
    """抓首次 SystemMessage，截取 <agent_memory> 注入块，验证长期记忆注入。"""

    def __init__(self) -> None:
        self.system: str = ""

    def on_chat_model_start(self, serialized, messages, **kwargs):
        if self.system:
            return
        for group in messages:
            for m in group:
                if isinstance(m, SystemMessage):
                    self.system = m.text()
                    return

    def memory_block(self) -> str:
        if not self.system:
            return "(没有捕获到模型请求)"
        match = re.search(r"<agent_memory>(.*?)</agent_memory>", self.system, re.S)
        return match.group(1) if match else "(系统提示词中没有 <agent_memory> 块)"
