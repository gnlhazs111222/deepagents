"""Ch07 进阶实验:description 质量对 Skill 召回的影响(A/B 对照)。

运行方式(项目根目录):
    uv run python agent_test/fifth_skills/skills_description_ab_test.py

设计:同一个 release-check Skill,只改 description,其余全部不变,各跑一次:
  - A 组(好 description):具体、含触发条件"发布前检查清单";
  - B 组(差 description):模糊的"一个有用的技能"。
观察指标:
  1. Agent 是否触发了 Skill(有没有 read_file 那个 SKILL.md);
  2. 首轮 system prompt 里两种 description 的差异(都会注入,但可读性不同);
  3. 最终答复是否编造检查项。
不做硬断言(真实模型行为有随机性),脚本打印对照结果供分析。
"""

from __future__ import annotations

import os
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


SKILL_PATH = "/skills/release-check/SKILL.md"
REFERENCE_PATH = "/skills/release-check/references/checks.md"
REFERENCE_TEXT = """# 发布前检查清单
- 单元测试通过
- 构建产物中没有调试日志
"""

DESCRIPTION_GOOD = "当用户需要发布前检查清单时,读取本地资料并列出检查项。"
DESCRIPTION_BAD = "一个有用的技能。"

USER_QUESTION = "帮我做发布前检查,列出检查项。"


class ReadFileTracker(BaseCallbackHandler):
    """记录发给模型的消息,并统计 read_file 调用的路径。"""

    def __init__(self) -> None:
        self.first_system = ""
        self.read_paths: list[str] = []

    def on_chat_model_start(self, serialized, messages, **kwargs):
        if not self.first_system:
            self.first_system = "\n".join(
                m.text for m in messages[0] if isinstance(m, SystemMessage)
            )

    def collect_from_result(self, result: dict) -> None:
        calls = {
            c["id"]: c
            for m in result["messages"]
            if hasattr(m, "tool_calls")
            for c in m.tool_calls
        }
        for message in result["messages"]:
            if isinstance(message, ToolMessage) and calls.get(message.tool_call_id, {}).get("name") == "read_file":
                self.read_paths.append(calls[message.tool_call_id]["args"].get("file_path", ""))


def run_case(label: str, description: str) -> None:
    print(f"\n{'=' * 70}\n{label}\ndescription = {description!r}\n{'=' * 70}")

    root = Path(tempfile.mkdtemp(prefix="ch07-ab-"))
    tracker = ReadFileTracker()
    try:
        skill_file = root / SKILL_PATH.lstrip("/")
        reference_file = root / REFERENCE_PATH.lstrip("/")
        reference_file.parent.mkdir(parents=True)
        skill_file.write_text(
            f"---\nname: release-check\ndescription: {description}\n---\n"
            "# 发布检查技能\n"
            f"1. 使用 read_file 读取 `{REFERENCE_PATH}`。\n"
            "2. 只按参考清单列出检查项,不要添加资料中没有的要求。\n"
            "3. 如果读取失败,报告缺失路径并停止,不要猜测检查项。\n",
            encoding="utf-8",
        )
        reference_file.write_text(REFERENCE_TEXT, encoding="utf-8")

        agent = create_deep_agent(
            model=build_model(),
            backend=FilesystemBackend(root_dir=str(root), virtual_mode=True),
            skills=["/skills/"],
            system_prompt="你是发布助手。",
        )
        result = agent.invoke(
            {"messages": [{"role": "user", "content": USER_QUESTION}]},
            config={"configurable": {"thread_id": "ab-test"}, "callbacks": [tracker]},
        )
        tracker.collect_from_result(result)

        triggered = SKILL_PATH in tracker.read_paths
        final = result["messages"][-1].text
        hallucinated = "单元测试通过" in final and not triggered

        print(f"\n首轮 system prompt 中的 Skill 条目片段:")
        idx = tracker.first_system.find("release-check")
        print("  " + tracker.first_system[max(0, idx - 50): idx + 200].replace("\n", "\n  "))
        print(f"\nread_file 调用: {tracker.read_paths or '(无)'}")
        print(f"是否触发 Skill(读了 SKILL.md): {'是' if triggered else '否'}")
        print(f"最终答复(前 200 字): {final.strip()[:200]}")
        print(f"未触发却给出检查项(疑似凭记忆编造): {'是' if hallucinated else '否'}")
    finally:
        shutil.rmtree(root, ignore_errors=True)


def main() -> None:
    run_case("A 组:具体 description(预期:触发 Skill,按清单回答)", DESCRIPTION_GOOD)
    run_case("B 组:模糊 description(观察:是否还能被召回)", DESCRIPTION_BAD)
    print("\n对照实验结束。对比两组的'是否触发 Skill'即可看出 description 的召回作用。")


if __name__ == "__main__":
    main()
