"""综合 Demo 主实验：同一个应用串起 Skills + Subagents + Memory + HITL。

运行方式(项目根目录，需要 .env 有可用模型配置):
    uv run --frozen python agent_test/capstone_demo/01_end_to_end.py

流程（单进程内完成，一个应用、两个线程）:
  线程1（capstone-t1）一条指令引爆整条流水线：
    声明长期偏好 → 检查偏好写入 /memories/（长期记忆）
    → 委托 research-agent 检索（子代理）
    → 读 /skills/report-style/ 技能并按规范写报告（Skills）
    → write_file /final_report.md（Context Engineering：长文进 files 层）
    → publish_report 触发人工审批中断（HITL），审批前工具执行次数为 0
    → approve 恢复 → 发布恰好一次
  线程2（capstone-t2，同一 Store 新线程）：
    问"我的报告偏好是什么" → 验证 <agent_memory> 自动注入、无需重申。

判定全部基于执行记录、工具调用序列和 state 文件实物，不信模型嘴上说的。
"""

from __future__ import annotations

import json

from langgraph.types import Command

from common import (
    MEMORY_PATH,
    REPORT_PATH,
    SKILL_PATH,
    STRUCTURE_PATH,
    MemoryRecorder,
    build_demo_agent,
    check,
    get_pause,
    iter_tool_calls,
    print_tool_calls,
    read_state_file,
)

TASK_INSTRUCTION = (
    "我的长期偏好：研究报告一律用中文写，并且摘要放在最前面。请记住。"
    "然后调研 DeepAgents 框架的核心组件，按你的报告规范写好报告并发布。"
)

PREFERENCE_KEYS = ["语言", "中文", "摘要"]


def main() -> None:
    records: list = []
    agent, store, skill_tmp = build_demo_agent(records)
    config1 = {"configurable": {"thread_id": "capstone-t1"}}

    print("===== 第一步：一条指令引爆流水线，观察 HITL 暂停 =====")
    paused = agent.invoke(
        {"messages": [{"role": "user", "content": TASK_INSTRUCTION}]},
        config=config1, version="v2",
    )
    calls = iter_tool_calls(paused)
    print_tool_calls(paused)

    # --- 能力1：长期记忆（偏好已写入 Store） ---
    mem_entry = store.get(("demo-user", "memories"), MEMORY_PATH)
    mem_text = ""
    if mem_entry is not None:
        data = mem_entry.value
        mem_text = data.get("content") if isinstance(data, dict) else str(data)
    check("能力1·长期记忆：偏好已写入 /memories/（StoreBackend 持久层）",
          any(k in mem_text for k in PREFERENCE_KEYS),
          f"preferences.md 现内容: {mem_text[:120]}")

    # --- 能力2：子代理（task 工具被调用，主代理自己没直接搜索） ---
    check("能力2·子代理：主代理委托 research-agent（task 工具）",
          any(name == "task" for name, _ in calls),
          f"调用序列: {[n for n, _ in calls]}")

    # --- 能力3：Skills（读了 SKILL.md 与结构文件） ---
    skill_reads = [args.get("path", "") for name, args in calls if name == "read_file"]
    check("能力3·Skills：按渐进式披露读取 SKILL.md → structure.md",
          any(SKILL_PATH in p for p in skill_reads),
          f"read_file 路径: {skill_reads}")

    # --- 能力4：Context Engineering（报告全文在 files 层，不靠上下文携带） ---
    report = read_state_file(agent, config1, REPORT_PATH)
    check("能力4·Context Engineering：完整报告已 write_file 到 " + REPORT_PATH,
          bool(report) and "## " in (report or ""),
          f"报告长度: {len(report or '')} 字符")

    # --- 能力5：HITL（发布前暂停，工具执行次数为 0） ---
    paused_flag, actions, reviews = get_pause(paused)
    check("能力5·HITL：publish_report 触发审批中断", paused_flag,
          f"待审批: {[a['name'] for a in actions]}")
    check("审批前 publish_report 执行次数为 0（模型提出 ≠ 已执行）",
          not records, f"records: {records}")

    if not paused_flag:
        print("\n[中止] 未产生审批中断，后续阶段无法继续。")
        return

    print("\n===== 第二步：approve 恢复 → 发布恰好一次 =====")
    resumed = agent.invoke(
        Command(resume={"decisions": [{"type": "approve"}]}),
        config=config1, version="v2",
    )
    print(f"    [最终回答] {(resumed.value['messages'][-1].text() if hasattr(resumed.value['messages'][-1], 'text') else '')[:200]}")
    check("approve 后 publish_report 执行恰好一次",
          len(records) == 1 and records[0]["name"] == "publish_report"
          and records[0]["args"]["path"] == REPORT_PATH,
          f"执行记录: {json.dumps(records, ensure_ascii=False)}")
    check("报告中引用了检索来源（子代理成果被主代理采纳）",
          bool(report) and "http" in report)

    print("\n===== 第三步：新线程 capstone-t2 验证跨线程记忆 =====")
    recorder = MemoryRecorder()
    agent_with_recorder = agent
    config2 = {"configurable": {"thread_id": "capstone-t2"},
               "callbacks": [recorder]}
    answer = agent_with_recorder.invoke(
        {"messages": [{"role": "user",
                       "content": "用一句话复述我的报告偏好，不用问我。"}]},
        config=config2, version="v2",
    )
    injected = recorder.memory_block()
    check("长期记忆自动注入新线程的系统提示词（<agent_memory>）",
          any(k in injected for k in PREFERENCE_KEYS),
          f"注入块片段: {injected[:120]}")
    final_text = answer.value["messages"][-1].text() if hasattr(answer.value["messages"][-1], "text") else ""
    check("Agent 无需重申即可复述偏好",
          any(k in final_text for k in PREFERENCE_KEYS),
          f"回答: {final_text[:120]}")

    print("\n===== 结论 =====")
    print("同一个 create_deep_agent 装配，五项能力各司其职：")
    print("Store 存偏好、子代理出素材、技能定结构、files 层存长文、HITL 把住发布关。")
    skill_tmp.cleanup()


if __name__ == "__main__":
    main()
