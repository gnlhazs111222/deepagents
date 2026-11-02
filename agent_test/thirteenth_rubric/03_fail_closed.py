"""Ch13 实验 3: 预算耗尽与失败关闭 —— 有最终消息 ≠ 验收通过。

运行方式(项目根目录,需要 .env 有可用模型配置):
    uv run --frozen python agent_test/thirteenth_rubric/03_fail_closed.py

流程:
  用 max_iterations=1 发起同一个任务。若第一轮评分 needs_revision,
  预算立刻耗尽,运行以 max_iterations_reached 结束 —— 但候选答案
  仍留在 result["messages"] 里。

观察点:
  1. 最后一轮回调结论是 max_iterations_reached(不是 needs_revision:
     预算用尽的最后一轮会先被中间件改写为预算耗尽结论再回调)
  2. result["messages"] 里确实存在候选答案
  3. Fail-Closed 验收门拒绝它;而 bool(result["messages"]) 这个
     错误判断会放行它 —— 对照两种判断的分歧

若模型第一轮就写对并直接 satisfied,实验如实报告"未触发预算耗尽",
并额外用一次"故意无法满足的 Rubric"验证失败关闭路径。
"""

from __future__ import annotations

from langchain.messages import HumanMessage

from common import (
    IMPOSSIBLE_RUBRIC,
    RUBRIC,
    STEER_PREFIX,
    TASK,
    acceptance_gate,
    build_rubric_agent,
    check,
    make_eval_logger,
    print_code_head,
)


def main() -> None:
    evaluations, _, record = make_eval_logger()
    agent = build_rubric_agent(max_iterations=1, on_evaluation=record)
    config = {"configurable": {"thread_id": "ch13-fail-closed"}}

    print("===== 第一步: max_iterations=1 + 引导 set 版,观察预算耗尽 =====")
    start = len(evaluations)
    result = agent.invoke(
        {"messages": [HumanMessage(content=STEER_PREFIX + TASK)], "rubric": RUBRIC},
        config=config,
    )
    run_evals = evaluations[start:]
    print_code_head(result)

    if not run_evals:
        check("至少产生一轮评审", False, "回调记录为空")
        return

    final_result = run_evals[-1]["result"]
    if final_result == "max_iterations_reached":
        check("最后一轮结论被中间件改写为 max_iterations_reached", True,
              f"共 {len(run_evals)} 轮,最终: {final_result}")
    elif final_result == "satisfied":
        check("最后一轮结论为 max_iterations_reached", False,
              "模型第一轮就通过了,未触发预算耗尽 —— 进入第二步用不可能 Rubric 验证")
    else:
        check("最终结论为 max_iterations_reached", False, f"实际: {final_result}")

    print("\n===== 第二步: 候选答案仍在,验收门必须拒绝 =====")
    check("result['messages'] 里存在最终候选消息", bool(result["messages"]),
          "自然停止了,消息就在那里 —— 这正是危险之处")

    wrong_gate = bool(result["messages"])
    right_gate = acceptance_gate(run_evals)
    check("错误判断 bool(messages) 会放行(演示反例)", wrong_gate,
          "这正是'拿到最终消息就当通过'的陷阱")
    check("Fail-Closed 验收门拒绝(最终结论 ≠ satisfied)", not right_gate,
          f"accepted={right_gate}")
    check("两种判断结论相反,证明必须用验收门", wrong_gate != right_gate)

    if final_result == "satisfied":
        print("\n===== 第三步: 用不可能 Rubric 强制验证失败关闭 =====")
        evaluations2, _, record2 = make_eval_logger()
        agent2 = build_rubric_agent(max_iterations=2, on_evaluation=record2)
        config2 = {"configurable": {"thread_id": "ch13-fail-closed-impossible"}}
        start2 = len(evaluations2)
        result2 = agent2.invoke(
            {"messages": [HumanMessage(content=STEER_PREFIX + TASK)],
             "rubric": IMPOSSIBLE_RUBRIC},
            config=config2,
        )
        evals2 = evaluations2[start2:]
        print_code_head(result2)
        if evals2:
            check("不可能 Rubric 下验收门拒绝", not acceptance_gate(evals2),
                  f"最终结论: {evals2[-1]['result']}")
        else:
            check("不可能 Rubric 下产生了评审记录", False)

    print("\n===== 结论 =====")
    print("达到评分上限时循环终止,但候选答案仍留在 messages 中;")
    print("任何'有消息就算过'的判断都会把未验收结果放行给下游。")
    print("只有最后一轮 result == satisfied 才接收 —— 未知状态默认拒绝。")


if __name__ == "__main__":
    main()
