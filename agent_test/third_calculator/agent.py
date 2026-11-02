"""实验 3（教程第 2 章「小试牛刀」）：计算器 Agent。

代码与教程原样一致（两个工具、同一句提问），只把模型接线换成读项目 .env，
不用注册教程推荐的硅基流动，直接用你现成的智谱 key。

教程原文：https://datawhalechina.github.io/deepagents-in-action/chapters/ch02-quickstart/

运行（在项目根目录）：
    uv run --frozen python agent_test/third_calculator/agent.py
"""

import os

os.environ.setdefault("LANGSMITH_PROJECT", "calculator")

from pathlib import Path

from dotenv import load_dotenv


def _find_env_file():
    for parent in Path(__file__).resolve().parents[:6]:
        candidate = parent / ".env"
        if candidate.exists():
            return candidate
    return None


load_dotenv(_find_env_file())

from deepagents import create_deep_agent
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    model=os.getenv("AGENTSEEK_MODEL", "glm-4.5-air"),
    api_key=os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv("OPENAI_API_BASE"),
    timeout=180,
)


def calculate(expression: str) -> float:
    """Evaluate a math expression and return the result.

    Args:
        expression: A math expression, e.g. "1 + 2 * 3".
    """
    # 仅做演示，实际项目应使用安全的解析库而非 eval（教程原注释）
    return eval(expression)


def convert_currency(amount: float, from_currency: str, to_currency: str = "CNY") -> dict:
    """Convert an amount from one currency to another.

    Args:
        amount: The amount to convert.
        from_currency: The source currency code, e.g. "USD".
        to_currency: The target currency code, defaults to "CNY".
    """
    # 这里用固定汇率做演示；真实场景可接入汇率 API（教程原注释）
    rates = {"USD": 7.2, "CNY": 1.0, "EUR": 7.8}
    cny = amount * rates[from_currency]
    return {"amount": round(cny / rates[to_currency], 2), "currency": to_currency}


agent = create_deep_agent(
    model=model,
    tools=[calculate, convert_currency],
    system_prompt="你是一个计算助手，能帮用户做数学运算和货币换算。",
)

if __name__ == "__main__":
    result = agent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "帮我把 100 美元换算成人民币，再用它乘以 1.08 的通胀系数。",
                }
            ]
        }
    )
    print(result["messages"][-1].content)
