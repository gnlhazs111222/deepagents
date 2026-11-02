"""Ch07 实验:用真实模型验证 Skill 的渐进式披露(Progressive Disclosure)。

运行方式(项目根目录):
    uv run python agent_test/fifth_skills/skills_progressive_disclosure.py

复用项目 .env 的模型配置(AGENTSEEK_MODEL / OPENAI_API_KEY / OPENAI_API_BASE),
与 src/research_deepagent/agent.py 的接法一致。

实验做三件事:
1. 在临时目录写一个 release-check Skill(SKILL.md + references/checks.md);
2. 用回调抓取每轮发给模型的消息,验证:
   - 第一轮 system prompt 里只有 name/description/路径,没有正文和资源内容;
   - Agent 按 description 判断相关后,先 read_file SKILL.md,再按正文指引读 references;
3. 删掉 references 文件再跑一遍,验证读取失败时 Agent 按指令停止而不瞎猜。
"""

from __future__ import annotations

import os
import re
import shutil
import tempfile
from pathlib import Path

from dotenv import load_dotenv
from langchain.chat_models import init_chat_model
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import SystemMessage, ToolMessage

from deepagents import create_deep_agent
from deepagents.backends.filesystem import FilesystemBackend

load_dotenv()

# ---------------------------------------------------------------------------
# 模型:与 src/research_deepagent/agent.py 相同的 .env 接法
# ---------------------------------------------------------------------------


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
# Skill 材料
# ---------------------------------------------------------------------------

SKILL_PATH = "/skills/release-check/SKILL.md"
REFERENCE_PATH = "/skills/release-check/references/checks.md"
DESCRIPTION = "当用户需要发布前检查清单时,读取本地资料并列出检查项。"
BODY_MARKER = "只按参考清单列出检查项"
REFERENCE_MARKER = "单元测试通过"
SECOND_CHECK = "构建产物中没有调试日志"

SKILL_TEXT = f"""---
name: release-check
description: {DESCRIPTION}
---
# 发布检查技能
1. 使用 read_file 读取 `{REFERENCE_PATH}`。
2. {BODY_MARKER},不要添加资料中没有的要求。
3. 如果读取失败,报告缺失路径并停止,不要猜测检查项。
"""

REFERENCE_TEXT = f"""# 发布前检查清单
- {REFERENCE_MARKER}
- {SECOND_CHECK}
"""


class PromptRecorder(BaseCallbackHandler):
    """记录每轮发给模型的完整消息,用于验证渐进式披露。"""

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        model_messages = messages[0]
        self.requests.append({
            "system": "\n".join(
                m.text for m in model_messages if isinstance(m, SystemMessage)
            ),
            "context": "\n".join(m.text for m in model_messages),
        })


def build_agent(root: Path):
    return create_deep_agent(
        model=build_model(),
        backend=FilesystemBackend(root_dir=str(root), virtual_mode=True),
        skills=["/skills/"],
        system_prompt="你是发布助手,严格按 Skill 指令执行。",
    )


def show_reads(label: str, result: dict) -> None:
    print(f"\n=== {label} ===")
    calls = {
        c["id"]: c
        for m in result["messages"]
        if hasattr(m, "tool_calls")
        for c in m.tool_calls
    }
    for message in result["messages"]:
        if isinstance(message, ToolMessage):
            call = calls[message.tool_call_id]
            print(f"  {call['name']}({call['args']}) → {message.status}")
            text = message.text.strip().replace("\n", " | ")
            print(f"    返回: {text[:120]}{'...' if len(text) > 120 else ''}")
    print(f"  最终答复: {result['messages'][-1].text.strip()[:200]}")


def run(root: Path, question: str) -> tuple[dict, PromptRecorder]:
    recorder = PromptRecorder()
    agent = build_agent(root)
    result = agent.invoke(
        {"messages": [{"role": "user", "content": question}]},
        config={"configurable": {"thread_id": "ch07-demo"}, "callbacks": [recorder]},
    )
    return result, recorder


def check_disclosure(recorder: PromptRecorder, *, resource_exists: bool) -> None:
    """验证核心命题:启动时只有元数据,正文和资源都是后来按需读的。"""
    first = recorder.requests[0]
    assert "release-check" in first["system"], "元数据 name 应在首轮 system prompt"
    assert DESCRIPTION in first["system"], "description 应在首轮 system prompt"
    assert SKILL_PATH in first["system"], "Skill 路径应在首轮 system prompt"
    assert BODY_MARKER not in first["context"], "首轮不应出现 SKILL.md 正文!"
    assert REFERENCE_MARKER not in first["context"], "首轮不应出现 references 内容!"

    if resource_exists:
        full = recorder.requests[-1]["context"]
        assert BODY_MARKER in full, "最终轮应能看到 SKILL.md 正文(按需读取后)"
        assert REFERENCE_MARKER in full, "最终轮应能看到参考清单(按需读取后)"
    print("  [PASS] 渐进式披露验证通过:元数据先行,正文/资源按需进入上下文")


def main() -> None:
    root = Path(tempfile.mkdtemp(prefix="ch07-skills-"))
    try:
        skill_file = root / SKILL_PATH.lstrip("/")
        reference_file = root / REFERENCE_PATH.lstrip("/")
        reference_file.parent.mkdir(parents=True)
        skill_file.write_text(SKILL_TEXT, encoding="utf-8")
        reference_file.write_text(REFERENCE_TEXT, encoding="utf-8")

        # 场景一:资料齐全,观察三级加载顺序
        result, recorder = run(root, "帮我做发布前检查,列出检查项。")
        show_reads("场景一:资料存在", result)
        check_disclosure(recorder, resource_exists=True)

        # 场景二:删掉 references,验证失败时按指令停止
        reference_file.unlink()
        result, recorder = run(root, "帮我做发布前检查,列出检查项。")
        show_reads("场景二:资料缺失", result)
        final = result["messages"][-1].text
        assert SECOND_CHECK not in final, "资料缺失时不应编造检查项!"
        print("  [PASS] 缺失场景验证通过:Agent 未编造检查项")
    finally:
        shutil.rmtree(root, ignore_errors=True)
    print("\n临时技能目录已清理,实验结束。")


if __name__ == "__main__":
    main()
