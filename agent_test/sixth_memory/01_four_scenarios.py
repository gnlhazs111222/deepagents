"""Ch08 主实验：四场景验证「共享偏好 vs 线程内草稿」的边界。

运行方式(项目根目录，需要 .env 有可用模型配置):
    uv run --frozen python agent_test/sixth_memory/01_four_scenarios.py

四个场景:
  1. Alice 保存偏好 + 写草稿(线程 alice-original)
  2. Alice 开新线程(alice-fresh):偏好可读、草稿应"File not found"
  3. Alice 回到旧线程(alice-original):草稿还在
  4. Bob 新线程:只能读到 Bob 自己的偏好，与 Alice 无关

判定原则:每个场景打印真实工具调用/返回 + Store 内容 + 注入模型系统提示词的
memory 块，PASS/FAIL 逐项打印。不信 Agent 最后一句"已完成"。
"""

from __future__ import annotations

import json
import uuid

from langgraph.store.memory import InMemoryStore

from common import (
    ALICE_INITIAL,
    BOB_INITIAL,
    DRAFT_PATH,
    MEMORY_PATH,
    ALICE_NS,
    BOB_NS,
    ModelRequestRecorder,
    SYSTEM_PROMPT,
    UserContext,
    build_agent,
    make_namespace_fn,
    preset_store,
    print_tool_calls,
)

DRAFT_TEXT = "# 调研草稿\n- 待补充:对比 DeepAgents 与 LangGraph 原生方案"
NEW_PREFS = {"comment_language": "zh", "variable_language": "en"}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))


def main() -> None:
    store = InMemoryStore()
    preset_store(store)
    agent = build_agent(make_namespace_fn(), SYSTEM_PROMPT)

    # ---------- 场景 1: Alice 保存偏好 + 写草稿 ----------
    print("\n===== 场景 1: Alice 保存偏好并写草稿 (thread=alice-original) =====")
    recorder1 = ModelRequestRecorder()
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
        config={"configurable": {"thread_id": "alice-original"}, "callbacks": [recorder1]},
    )
    print_tool_calls(result)
    saved = store.get(ALICE_NS, "/preferences.md")
    saved_json = json.loads(saved.value["content"]) if saved else None
    check("Store 中 Alice 偏好已更新", saved_json == NEW_PREFS,
          f"实际: {saved_json}")
    check("本轮注入的还是旧值(符合预期)",
          json.dumps(ALICE_INITIAL, ensure_ascii=False) in recorder1.memory_injection(),
          "更新后的值要在场景 2 的新线程才能注入")

    # ---------- 场景 2: 同用户新线程 ----------
    print("\n===== 场景 2: Alice 新线程 (thread=alice-fresh) =====")
    recorder2 = ModelRequestRecorder()
    result = agent.invoke(
        {"messages": [{
            "role": "user",
            "content": (
                f"先读取 {MEMORY_PATH} 告诉我我的偏好;再读取 {DRAFT_PATH} 告诉我草稿内容。"
            ),
        }]},
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "alice-fresh"}, "callbacks": [recorder2]},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")
    injection = recorder2.memory_injection()
    print(f"    [注入的 memory 块] {injection[:200]}")
    check("新线程注入了更新后的偏好", json.dumps(NEW_PREFS, ensure_ascii=False) in injection)
    check("新线程读不到草稿(File not found 是预期边界)",
          "not found" in result["messages"][-1].text().lower()
          or any(m.type == "tool" and "not found" in str(m.content).lower()
                 for m in result["messages"]))

    # ---------- 场景 3: 回到旧线程 ----------
    print("\n===== 场景 3: Alice 回到旧线程 (thread=alice-original) =====")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"读取 {DRAFT_PATH} 并告诉我草稿内容。"}]},
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "alice-original"}},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")
    state = agent.get_state({"configurable": {"thread_id": "alice-original"}})
    state_files = state.values.get("files", {})
    check("checkpoint 的 State 里有草稿", any(DRAFT_PATH in k for k in state_files),
          f"State 文件: {list(state_files)}")
    check("State 里没有偏好文件(偏好只存在于 Store)", not any("/memories/" in k for k in state_files))

    # ---------- 场景 4: Bob ----------
    print("\n===== 场景 4: Bob 新线程 (namespace 隔离) =====")
    recorder4 = ModelRequestRecorder()
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"读取 {MEMORY_PATH}，告诉我我的偏好是什么。"}]},
        context=UserContext(user_id="bob"),
        config={"configurable": {"thread_id": str(uuid.uuid4())}, "callbacks": [recorder4]},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")
    bob_injection = recorder4.memory_injection()
    bob_json = json.loads(store.get(BOB_NS, "/preferences.md").value["content"])
    check("Bob 的 Store 记录是他自己的偏好", bob_json == BOB_INITIAL, f"实际: {bob_json}")
    check("注入中包含 Bob 的偏好", json.dumps(BOB_INITIAL, ensure_ascii=False) in bob_injection)
    check("注入中没有 Alice 的偏好(隔离生效)",
          json.dumps(NEW_PREFS, ensure_ascii=False) not in bob_injection)

    print("\n===== 总结 =====")
    print("全部 PASS: 偏好跨线程共享(Store)，草稿线程隔离(State)，用户间 namespace 隔离。")
    print("注意: 一切都在内存里，进程退出即清空；跨线程可见 ≠ 重启后仍在。")


if __name__ == "__main__":
    main()
