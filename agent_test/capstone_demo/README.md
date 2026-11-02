# 综合可复现 Demo：报告发布工作流（Capstone）

> 把课程多项能力装进**同一个** `create_deep_agent` 装配，一条流水线串起来。
> 位置：`agent_test/capstone_demo/`。默认用离线检索语料，可复现、不烧 Tavily 配额。

## 一、应用设计

场景：**"研究报告发布工作流"** —— Agent 调研话题 → 按技能规范写报告 → 人工审批 → 发布，并把用户偏好长期记住。

一次装配，五项能力各就各位（对应课程章节）：

| 能力 | 课程出处 | 在 Demo 里的落点 | 怎么验证（全部看实物证据） |
|---|---|---|---|
| Long-term Memory | ch08 | `/memories/` 路由到 `StoreBackend`，`memory=[...]` 自动注入 | Store 里 `preferences.md` 出现偏好字段；新线程系统提示词有 `<agent_memory>` 块 |
| Subagents | ch04/ch05 | `research-agent` 子代理专职检索，主代理只汇总写作 | 调用序列里出现 `task` 工具；报告引用了语料 URL |
| Skills | ch07 | `/skills/report-style/` 两级技能文件，渐进式披露 | `read_file` 先读 SKILL.md 再读 references；报告章节齐全 |
| Context Engineering | ch06/pre01 | 长报告 `write_file` 进 state 的 files 层，超长检索结果框架自动落盘换纸条 | checkpoint 的 files 层里有完整 `/final_report.md` |
| HITL | ch09 | `publish_report` 挂 `interrupt_on`，发布前必须人审 | 暂停时执行次数为 0；approve/edit 后恰好执行一次、参数与决策一致 |

装配要点（与之前各章验证过的写法一致）：

- `backend=CompositeBackend(default=StateBackend(), routes={"/skills/": FilesystemBackend(临时目录), "/memories/": StoreBackend(...)})` —— 三种 backend 各管一段路径；
- `interrupt_on={"publish_report": {"allowed_decisions": ["approve", "edit", "reject"]}}`；
- 取证工具 `publish_report` 只往 `records` 列表追加，不发真实请求；模型装配读 `.env`，与 `seventh_hitl` 相同。

## 二、运行方式（用户执行）

```bash
cd ~/projects/research_deepagent

# 主实验：一条指令引爆全流水线（约 2~4 分钟，视模型速度）
uv run --frozen python agent_test/capstone_demo/01_end_to_end.py

# 变体：HITL 的 edit 决策（人工改掉 headline 后按新参数发布）
uv run --frozen python agent_test/capstone_demo/02_hitl_edit.py

# 可选：换真实 Tavily 检索（需网络与 key，结果不再逐字可复现）
CAPSTONE_LIVE_SEARCH=1 uv run --frozen python agent_test/capstone_demo/01_end_to_end.py
```

预期输出：`01_end_to_end.py` 分三步打印，每步若干 `[PASS]` 检查（偏好入库 → task 委托 → 技能读取 → 报告落 files 层 → 暂停时 0 次执行 → approve 后恰好 1 次 → 新线程 `<agent_memory>` 注入并复述偏好），最后打印五项能力结论。若有 `[FAIL]`，优先怀疑：模型没走 task 直接自己搜了、或没读技能就写报告 —— 把工具调用序列打印贴回来分析。

已知非确定性：模型可能跳过 think_tool、偏好 JSON 字段名不定，检查项都做了容忍（关键词包含式判定）。

## 三、总结心得

1. **组合的难点不在单个能力，在"路由边界"。** 三个 backend 共存时，`/skills/`、`/memories/`、默认 state 各管一段，拼错前缀就静默失效；子代理与主代理只有 files 层共享（messages/todos 双向隔离），所以"任务书和素材写成文件"是组合能跑通的隐含前提。
2. **HITL 是整条流水线的"验收关"，不是装饰。** 前面所有自动化的产出（检索、写作）都可能有错，`publish_report` 的人工闸门把"模型提出调用 ≠ 已执行"这条纪律落到了产品行为上：审批前执行次数为 0，edit 改的是真正落进工具的 args。
3. **记忆的价值在第二个线程才显现。** 写入偏好只是 `edit_file`，真正的能力是跨线程的 `<agent_memory>` 自动注入——用户不用重申，行为就变了。这提示我们：验证长期记忆必须开新线程，同线程只能证明"写进去了"。
4. **可复现性要主动设计。** 把检索换成离线语料后，Demo 不再受 Tavily 网络、配额、搜索结果变化影响，PASS/FAIL 才有判定意义；真实检索留一个环境变量开关即可，不必二选一。
5. **Context Engineering 是"隐形地基"。** 它没有独立实验脚本，却是报告长文不撑爆上下文的前提——长文住在 files 层，上下文里只有纸条。能力组合时，最值得信任的往往是这些默认就发生、不声不响的机制。
