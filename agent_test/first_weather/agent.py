"""天气 Agent：一个能看懂的最小 DeepAgents 教学案例。

用途（配合 LangSmith）：
- 观察一次 agent 运行在「本地消息数组」和「LangSmith Trace」里分别长什么样；
- 对比 v1/v2 两档配置（系统提示词 + 工具描述），理解调优杠杆及其边界。

运行（在项目根目录）：
    uv run --frozen python agent_test/first_weather/agent.py --level v1 "北京和杭州今天天气怎么样？我该穿什么？"
    uv run --frozen python agent_test/first_weather/agent.py --level v2 "北京和杭州今天天气怎么样？我该穿什么？"
"""

import argparse
import json
import os

# 必须在导入 langchain 之前、且在 load_dotenv 之前设置：
# load_dotenv 默认不覆盖已存在的环境变量，这样本次运行的 Trace
# 会进入 weather-agent 项目，不和课程 research 的 Trace 混在一起。
os.environ.setdefault("LANGSMITH_PROJECT", "weather-agent")

from pathlib import Path

from dotenv import load_dotenv


def _find_env_file():
    """向上逐级找 .env：本目录以后再往 agent_test 深处挪一层也照常能跑。"""
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

# ---------------------------------------------------------------- 工具层

# 模拟数据库：确定性数据让「好坏判断」可复现（接真实天气 API 反而引入网络噪声）。
WEATHER_DB = {
    "北京": {"condition": "晴", "high_c": 18, "low_c": 7, "wind": "西北风 3 级", "aqi": 55},
    "上海": {"condition": "多云", "high_c": 22, "low_c": 16, "wind": "东风 2 级", "aqi": 48},
    "广州": {"condition": "阵雨", "high_c": 28, "low_c": 23, "wind": "南风 2 级", "aqi": 40},
    "哈尔滨": {"condition": "大雪", "high_c": -8, "low_c": -18, "wind": "西北风 5 级", "aqi": 35},
    "三亚": {"condition": "晴", "high_c": 31, "low_c": 26, "wind": "西南风 3 级", "aqi": 25},
}


def _get_weather_impl(city: str) -> str:
    """工具的实现体；对模型展示的描述由 make_get_weather 按 v1/v2 注入。"""
    city = city.strip()
    if city not in WEATHER_DB:
        return f"未知城市：{city}。本工具仅支持：{'、'.join(WEATHER_DB)}"
    return json.dumps({"city": city, **WEATHER_DB[city]}, ensure_ascii=False)


TOOL_DESCRIPTIONS = {
    # v1：故意写得很含糊 —— 用来观察模型怎么「盲用」这个工具
    "v1": "查询天气。",
    # v2：把参数格式、支持范围、失败行为全部讲清楚
    "v2": (
        "查询中国城市当前天气。参数 city 必须是不带「市」后缀的中文城市名，如「北京」。"
        "仅支持：北京、上海、广州、哈尔滨、三亚。"
        "用户提到的任何城市都必须先调用本工具，禁止凭记忆回答天气；"
        "返回「未知城市」时如实转告用户并给出支持列表，不要猜测。"
    ),
}


def make_get_weather(version: str) -> StructuredTool:
    return StructuredTool.from_function(
        func=_get_weather_impl,
        name="get_weather",
        description=TOOL_DESCRIPTIONS[version],
    )


# ---------------------------------------------------------------- 提示词层

SYSTEM_PROMPTS = {
    # v1：几乎不设防 —— 用来观察默认行为和失败模式
    "v1": "你是一个乐于助人的天气助手。",
    # v2：明确工具使用纪律、事实性边界和输出契约
    "v2": (
        "你是天气助手。规则：\n"
        "1. 用户提到的每个城市都必须调用 get_weather 查询；\n"
        "2. 工具返回「未知城市」时，如实说明不支持，禁止编造任何天气数值；\n"
        "3. 所有温度、风力、空气质量只能来自工具返回，不许改动；\n"
        "4. 每个城市按「天气/气温/风力/AQI/穿衣建议」输出，穿衣建议必须由气温推导并说明理由。"
    ),
}

# ---------------------------------------------------------------- 装配


def build_agent(level: str):
    model = ChatOpenAI(
        model=os.getenv("AGENTSEEK_MODEL", "glm-4.5-air"),
        api_key=os.getenv("OPENAI_API_KEY"),
        base_url=os.getenv("OPENAI_API_BASE"),
        timeout=180,
    )
    return create_deep_agent(
        model=model,
        tools=[make_get_weather(level)],
        system_prompt=SYSTEM_PROMPTS[level],
    )


def _text(message) -> str:
    content = message.content
    return content if isinstance(content, str) else str(content)


def _clip(text: str, limit: int) -> str:
    return text[:limit] + ("…" if len(text) > limit else "")


def main() -> None:
    parser = argparse.ArgumentParser(description="最小天气 Agent（LangSmith 教学案例）")
    parser.add_argument("question", help="用户问题")
    parser.add_argument("--level", choices=["v1", "v2"], default="v1", help="配置档位")
    args = parser.parse_args()

    print(f"[配置] level={args.level} project={os.environ['LANGSMITH_PROJECT']}")

    agent = build_agent(args.level)

    with collect_runs() as cb:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": args.question}]},
            config={"run_name": f"weather-{args.level}"},
        )

    # 本地视角：打印消息数组的生长过程 —— 这就是「上下文」的实物
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
        print(f"\n[LangSmith] trace_id={cb.traced_runs[0].id}")
        print("到 LangSmith 网页的 weather-agent 项目打开这条 Trace，或把 ID 发给编码助手一起读。")


if __name__ == "__main__":
    main()
