"""Ch13 实验 2(主实验): 验收闭环 —— needs_revision 带着差距回到生成环节。

运行方式(项目根目录,需要 .env 有可用模型配置):
    uv run --frozen python agent_test/thirteenth_rubric/02_revision_loop.py

流程:
  第一步 用"引导模型写出 set 版"的提示发起任务 → 预期第一轮评分
         needs_revision(gap=test_unhashable),Middleware 注入差距后
         工作模型修订 → 第二轮 satisfied
  第二步 检查工具调用归属: run_test_suite 的调用全部来自评分模型,
         工作模型从头到尾没有这个工具
判定基于 on_evaluation 回调记录与统一工具记录,不信最终消息的措辞。

若模型第一轮就直接写出正确实现,脚本会如实报告"未走修订路径",
并仍核对验收门逻辑 —— 案例重点是跑通状态机,不是强制产生两轮。
"""

from __future__ import annotations

from langchain.messages import HumanMessage

from common import (
    RUBRIC,
    STEER_PREFIX,
    TASK,
    acceptance_gate,
    build_rubric_agent,
    check,
    make_eval_logger,
    make_records,
    print_code_head,
)


def main() -> None:
    all_records, grader_tool = make_records()
    evaluations, _, record = make_eval_logger()
    agent = build_rubric_agent(grader_tools=[grader_tool], on_evaluation=record)
    config = {"configurable": {"thread_id": "ch13-revision-loop"}}

    print("===== 第一步: 发起任务(引导先用 set),观察评分循环 =====")
    start = len(evaluations)
    result = agent.invoke(
        {"messages": [HumanMessage(content=STEER_PREFIX + TASK)], "rubric": RUBRIC},
        config=config,
    )

    run_evals = evaluations[start:]
    if not run_evals:
        check("至少产生一轮评审(传入非空 rubric)", False, "回调记录为空")
        return

    check("传入非空 rubric 后评分模型确实运行了", len(run_evals) >= 1,
          f"共 {len(run_evals)} 轮评审")
    print_code_head(result)

    revised = run_evals[0]["result"] == "needs_revision"
    if revised:
        check("第一轮结论为 needs_revision(不是直接放行)", True,
              run_evals[0]["explanation"][:80])
        check("未通过标准携带了可执行 gap",
              any(c.get("gap") for c in run_evals[0].get("criteria", []) if not c.get("passed")))
    else:
        check("第一轮结论为 needs_revision(模型一次写对,未走修订路径)",
              False, f"第一轮即 {run_evals[0]['result']},如实记录")
    check("最后一轮结论为 satisfied", run_evals[-1]["result"] == "satisfied",
          f"最终结论: {run_evals[-1]['result']}")

    print("\n===== 第二步: 工具调用归属 =====")
    grader_calls = [r for r in all_records if r["tool"] == "run_test_suite" and "code_head" in r]
    check("run_test_suite 至少被调用一次(评分取证)", len(grader_calls) >= 1,
          f"共 {len(grader_calls)} 次")
    check("修订后重新取证(最后一轮证据对应当前候选)",
          run_evals[-1]["result"] == "satisfied" and len(grader_calls) >= len(run_evals),
          f"评审 {len(run_evals)} 轮 / 取证 {len(grader_calls)} 次")
    worker_tools = {tc["name"] for m in result["messages"] for tc in getattr(m, "tool_calls", None) or []}
    check("工作模型从未调用 run_test_suite(RubricMiddleware 工具不外漏)",
          "run_test_suite" not in worker_tools, f"工作模型工具: {worker_tools or '无'}")

    print("\n===== 第三步: Fail-Closed 验收门 =====")
    accepted = acceptance_gate(run_evals)
    check("验收门放行(最后结论是 satisfied)", accepted)
    check("最终消息存在且验收通过,两者同时成立",
          accepted and bool(result["messages"]))

    print("\n===== 结论 =====")
    print("自然停止只给候选;评分模型取证后用 needs_revision 把具体差距")
    print("送回对话,工作模型针对同一标准修订,重新取证通过才 satisfied;")
    print("应用只在 satisfied 时放行 —— Fail-Closed。")


if __name__ == "__main__":
    main()
