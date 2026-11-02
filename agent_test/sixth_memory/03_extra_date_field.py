"""练习 2: 给偏好对象加一个 date 字段 —— 观察严格比较为什么失败。

运行方式(项目根目录):
    uv run --frozen python agent_test/sixth_memory/03_extra_date_field.py

只改一个变量: 保存的偏好里多一个 "date" 字段。
预期: 按 Notebook 的严格验收标准(整个 JSON 对象完全相等，多一个字段都不行)，
date 字段会让断言失败 —— 记忆验收应当是严格 dict 相等而非"包含关键词"。
"""

from __future__ import annotations

import json

from common import (
    ALICE_NS,
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
    agent, store = build_agent_and_store(make_namespace_fn(), SYSTEM_PROMPT)
    preset_store(store)

    print("===== 保存带 date 字段的偏好 (thread=t1) =====")
    result = agent.invoke(
        {
            "messages": [{
                "role": "user",
                "content": (
                    "请记住我的代码风格偏好:注释用中文、变量名用英文，"
                    f"并额外记录 date=2026-11-02，一起保存到 {MEMORY_PATH}。"
                ),
            }],
        },
        context=UserContext(user_id="alice"),
        config={"configurable": {"thread_id": "t1"}},
    )
    print_tool_calls(result)

    saved = store.get(ALICE_NS, "/preferences.md")
    if saved is None:
        print("    [FAIL] 偏好文件没写进 Store，把上面输出贴回分析。")
        return
    written = json.loads(saved.value["content"])
    expected = {"comment_language": "zh", "variable_language": "en"}

    print("\n===== 用 Notebook 的严格标准核对 =====")
    print(f"    实际写入: {written}")
    check("严格 dict 相等(expected 恰好两个字段)", written == expected,
          "date 字段使严格比较失败 —— 验收必须是整个对象完全匹配")
    check("宽松『包含关键词』会漏掉多余字段", written != expected,
          "这正是 Notebook 用严格 dict 相等做验收的原因")


if __name__ == "__main__":
    main()
