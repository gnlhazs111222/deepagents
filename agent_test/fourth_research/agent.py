"""实验 4（教程第 2 章「实战」）：研究助手 —— 能联网搜索、写研究报告的 Agent。

代码与教程 Step 2-4 原样一致（internet_search 工具、研究员提示词、
TodoListMiddleware、同一句提问「什么是 LangGraph？」），
只把模型接线换成读项目 .env（智谱 key + 你已有的 TAVILY_API_KEY）。

教程原文：https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/

运行（在项目根目录）：
    uv run --frozen python agent_test/fourth_research/agent.py
"""

import os

os.environ.setdefault("LANGSMITH_PROJECT", "research-assistant")

from pathlib import Path

from dotenv import load_dotenv


def _find_env_file():
    for parent in Path(__file__).resolve().parents[:6]:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


load_dotenv(_find_env_file())

from typing import Literal

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langchain_openai import ChatOpenAI
from tavily import TavilyClient

model = ChatOpenAI(
    model=os.getenv("AGENTSEEK_MODEL", "glm-4.5-air"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE"),
    timeout=300,
)

tavily_client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])


def internet_search(
    query: str,
    max_results: int = 5,
    topic: Literal["general", "news", "finance"] = "general",
    include_raw_content: bool = False,
):
    """Run a web search for the given query.

    Args:
        query: The search query string.
        max_results: Maximum number of results to return.
        topic: The topic category for the search.
        include_raw_content: Whether to include raw page content.
    """
    return tavily_client.search(
        query,
        max_results=max_results,
        include_raw_content=include_raw_content,
        topic=topic,
    )


research_instructions = """你是一位专业的研究员。
你的工作是进行深入研究，然后撰写一份完整的研究报告。

你可以使用 internet_search 工具搜索互联网获取信息。
"""

agent = create_deep_agent(
    model=model,
    tools=[internet_search],
    system_prompt=research_instructions,
    middleware=[TodoListMiddleware()],
)

if __name__ == "__main__":
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "什么是 LangGraph？"}]}
    )
    print(result["messages"][-1].content)
