"""练习 1: 把"新线程"改回旧线程 ID —— 观察草稿从 File not found 变成可读。

运行方式(项目根目录):
    uv run --frozen python agent_test/sixth_memory/02_same_thread_id.py

只改一个变量: 读草稿时不再换新 thread_id，而是复用写草稿的那个。
预期: 草稿读取成功 —— 证明 State 文件的可见性完全由 thread_id 决定。
"""

from __future__ import annotations

from common import (
    DRAFT_PATH,
    MEMORY_PATH,
    SYSTEM_PROMPT,
    UserContext,
    build_agent,
    make_namespace_fn,
    preset_store,
    print_tool_calls,
)

DRAFT_TEXT = "# 调研草稿\n- 待补充:对比 DeepAgents 与 LangGraph 原生方案"


def main() -> None:
    store = preset_store_and_return()
    agent = build_agent(make_namespace_fn(), SYSTEM_PROMPT)

    print("===== 第一步: 同一线程内保存偏好并写草稿 (thread=t1) =====")
    result = agent.invoke(
        {
            "messages": [{
                "role": "user",
                "content": (
                    f"请记住我的代码风格偏好:注释用中文、变量名用英文，保存到 {MEMORY_PATH}。"
                    f"然后再把下面的草稿写到 {DRAFT_PATH}:\n{DRAFT_TEXT}"
                ),
            }],
        },
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "t1"}},
    )
    print_tool_calls(result)

    print("\n===== 第二步A: 同一个线程 t1 里读草稿(预期成功) =====")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"读取 {DRAFT_PATH} 并告诉我草稿内容。"}]},
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "t1"}},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")

    print("\n===== 第二步B: 新线程 t2 里读草稿(预期 File not found) =====")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"读取 {DRAFT_PATH} 并告诉我草稿内容。"}]},
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "t2"}},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")
    print("\n对照结论: 同 thread 可读、新线程不可读 —— State 文件按 thread_id 隔离。")


def preset_store_and_return():
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    preset_store(store)
    return store


if __name__ == "__main__":
    main()
