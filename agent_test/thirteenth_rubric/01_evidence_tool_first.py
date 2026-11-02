"""Ch13 实验 1(不耗模型): 先独立验证 Evidence Tool,再谈评分。

运行方式(项目根目录):
    uv run --frozen python agent_test/thirteenth_rubric/01_evidence_tool_first.py

观察点:
  1. 坏候选(set 版)在 test_unhashable 上 TypeError → ok=false
  2. 好候选(列表比较版)四组用例全过 → ok=true
  3. 全程没有调用任何模型 —— 工具验证与模型问题是两类问题

判定全部基于工具返回的结构化 dict(ok/failures),不看任何自然语言。
"""

from __future__ import annotations

from common import BAD_CANDIDATE, GOOD_CANDIDATE, check, run_test_suite


def main() -> None:
    print("===== 候选 1: set 版(看似合理,实际有缺陷) =====")
    bad = run_test_suite.invoke({"code": BAD_CANDIDATE})
    print(f"    结果: {bad}")

    check("ok 为 False", bad["ok"] is False, f"ok={bad['ok']}")
    check(
        "失败点正是不可哈希边界(test_unhashable TypeError)",
        any("test_unhashable" in f and "unhashable" in f for f in bad["failures"]),
        f"failures={bad['failures']}",
    )

    print("\n===== 候选 2: 列表比较版(修订后的实现) =====")
    good = run_test_suite.invoke({"code": GOOD_CANDIDATE})
    print(f"    结果: {good}")

    check("ok 为 True", good["ok"] is True, f"ok={good['ok']}")
    check("failures 为空", good["failures"] == [])

    print("\n===== 结论 =====")
    print("工具返回的是结构化事实(ok + 逐条 failures),不是日志文本;")
    print("在接入评分模型之前,确定性检查本身必须先被验证可靠 ——")
    print("工具错了,后面整条验收链路都在为错误证据背书。")
    print("本次运行没有调用任何模型。")


if __name__ == "__main__":
    main()
