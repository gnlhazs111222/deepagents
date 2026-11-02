"""练习 3: 把 namespace 固定为 Alice —— 观察 Bob 为什么"工具成功但读错了数据"。

运行方式(项目根目录):
    uv run --frozen python agent_test/sixth_memory/04_fixed_namespace.py

只改一个变量: StoreBackend 的 namespace 写死 ("alice", "memories")，Bob 也走它。
预期: Bob 的 read_file 照样返回 success(文件系统层面读到了文件)，
但内容是 Alice 的偏好 —— 工具成功 ≠ 拿到自己的数据，namespace 才是隔离边界。
这也是安全章节"用户可注入他人记忆"的根源。
"""

from __future__ import annotations

import json
import uuid

from common import (
    ALICE_NS,
    BOB_INITIAL,
    MEMORY_PATH,
    SYSTEM_PROMPT,
    UserContext,
    build_agent_and_store,
    make_namespace_fn,
    preset_store,
    print_tool_calls,
)


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"    [{'PASS' if ok else 'FAIL'}] {name}" + (f" —— {detail}" if detail else ""))


def main() -> None:
    # 关键差异: namespace 固定为 alice，所有用户都路由到同一个桶
    agent, store = build_agent_and_store(make_namespace_fn(fixed_user_id="alice"), SYSTEM_PROMPT)
    preset_store(store)

    print("===== Alice 保存偏好 (thread=alice-original) =====")
    result = agent.invoke(
        {
            "messages": [{
                "role": "user",
                "content": (
                    "请记住我的代码风格偏好:注释用中文、变量名用英文，"
                    f"保存到 {MEMORY_PATH}。"
                ),
            }],
        },
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "alice-original"}},
    )
    print_tool_calls(result)

    print("\n===== Bob 开新线程读偏好(namespace 被固定为 alice) =====")
    result = agent.invoke(
        {"messages": [{"role": "user", "content": f"读取 {MEMORY_PATH}，告诉我我的偏好是什么。"}]},
        context=UserContext(user_id="bob"),
        config={"configurable": {"thread_id": str(uuid.uuid4())}},
    )
    print_tool_calls(result)
    print(f"    [最终回答] {result['messages'][-1].text()[:200]}")

    alice_json = json.loads(store.get(ALICE_NS, "/preferences.md").value["content"])
    read_ok = any(m.type == "tool" and "not found" not in str(m.content).lower()
                  for m in result["messages"])
    answer = result["messages"][-1].text()
    check("Bob 的 read_file 返回 success(工具层面没问题)", read_ok)
    check("但 Bob 读到的是 Alice 的偏好(隔离被打破)",
          "中文" in answer and "英文" in answer)
    check("Bob 自己的偏好(en/zh)并没有出现在回答里",
          not ("en" == alice_json.get("comment_language") or BOB_INITIAL == alice_json))
    print("\n结论: namespace 决定『谁能看到哪份数据』；写死 namespace 等于把所有用户拧进同一个桶。")
    print("生产含义: user_id 必须来自认证入口，不能由客户端随意提供。")


if __name__ == "__main__":
    main()
