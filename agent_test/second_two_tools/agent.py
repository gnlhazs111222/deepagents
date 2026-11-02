"""实验 2：给 Agent 第二个工具，并且两个工具之间有依赖关系。

看什么（跑之前先猜，跑之后对照）：
1. 模型会不会自己排出「先 get_weather 查气温 → 再拿气温问穿衣」的顺序？
   顺序要求没写在系统提示词里，只写在 get_clothing_advice 的描述里。
2. 多了一个工具，每轮输入的 token 比实验 1 涨多少？（工具 schema 是固定开销）
3. 穿衣建议这次来自工具，和实验 1 里模型自己编的建议比，有什么不一样？
4. 它会把 7 和 18 哪个温度传给穿衣工具？还是会传两次？

运行（在项目根目录）：
    uv run --frozen python agent_test/second_two_tools/agent.py "北京今天该穿什么？"
"""

import argparse
import json
import os

# 实验独立的 LangSmith 项目，trace 不和实验 1 混在一起
os.environ.setdefault("LANGSMITH_PROJECT", "second-tools")

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
from langchain_core.tools import StructuredTool
from langchain_core.tracers.context import collect_runs
from langchain_openai import ChatOpenAI

WEATHER_DB = {
    "北京": {"condition": "晴", "high_c": 18, "low_c": 7, "wind": "西北风 3 级", "aqi": 55},
    "上海": {"condition": "多云", "high_c": 22, "low_c": 16, "wind": "东风 2 级", "aqi": 48},
    "广州": {"condition": "阵雨", "high_c": 28, "low_c": 23, "wind": "南风 2 级", "aqi": 40},
    "哈尔滨": {"condition": "大雪", "high_c": -8, "low_c": -18, "wind": "西北风 5 级", "aqi": 35},
    "三亚": {"condition": "晴", "high_c": 31, "low_c": 26, "wind": "西南风 3 级", "aqi": 25},
}


def _get_weather(city: str) -> str:
    city = city.strip()
    if city not in WEATHER_DB:
        return f"未知城市：{city}。仅支持：{'、'.join(WEATHER_DB)}"
    return json.dumps({"city": city, **WEATHER_DB[city]}, ensure_ascii=False)


def _clothing_advice(temp_c: int) -> str:
    t = int(temp_c)
    if t <= -5:
        advice = "羽绒服、帽子、手套，全套防寒"
    elif t <= 5:
        advice = "厚外套加毛衣，注意防风保暖"
    elif t <= 15:
        advice = "夹克或风衣加长袖，早晚加件薄外套"
    elif t <= 25:
        advice = "长袖T恤或薄衬衫即可"
    else:
        advice = "短袖即可，注意防晒补水"
    return json.dumps({"temp_c": t, "advice": advice}, ensure_ascii=False)


get_weather = StructuredTool.from_function(
    func=_get_weather,
    name="get_weather",
    description=(
        "查询中国城市当前天气。参数 city 是不带「市」后缀的中文城市名。"
        "仅支持：北京、上海、广州、哈尔滨、三亚。"
    ),
)

get_clothing_advice = StructuredTool.from_function(
    func=_clothing_advice,
    name="get_clothing_advice",
    description=(
        "根据气温（摄氏度，整数）返回穿衣建议。"
        "必须先用 get_weather 查到目标城市的气温，再把气温作为 temp_c 传入；禁止凭空猜测气温。"
    ),
)

SYSTEM_PROMPT = "你是一个乐于助人的助手。"


def build_agent():
    model = ChatOpenAI(
        model=os.getenv("AGENTSEEK_MODEL", "glm-4.5-air"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        timeout=180,
    )
    return create_deep_agent(
        model=model,
        tools=[get_weather, get_clothing_advice],
        system_prompt=SYSTEM_PROMPT,
    )


def _text(message) -> str:
    content = message.content
    return content if isinstance(content, str) else str(content)


def _clip(text: str, limit: int) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="实验 2：两个有依赖关系的工具")
    parser.add_argument("question", help="用户问题")
    args = parser.parse_args()

    print(f"[配置] project={os.environ['LANGSMITH_PROJECT']}")

    agent = build_agent()

    with collect_runs() as cb:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.question}]},
            config={"run_name": "second-two-tools"},
        )

    print(f"[消息数组] 共 {len(result['messages'])} 条：")
    for m in result["messages"]:
        if getattr(m, "tool_calls", None):
            for tc in m.tool_calls:
                print(f"  [{m.type}] 调用工具 {tc['name']}({tc['args']})")
        elif m.type == "tool":
            print(f"  [{m.type}] {m.name} -> {_clip(_text(m), 120)}")
        else:
            print(f"  [{m.type}] {_clip(_text(m), 200)}")

    print("\n===== 最终回答 =====")
    print(_text(result["messages"][-1]))

    if cb.traced_runs:
        print(f"\n[LangSmith] 本地id={cb.traced_runs[0].id}（仅供对照，根 trace 以 trace list 为准）")


if __name__ == "__main__":
    main()
