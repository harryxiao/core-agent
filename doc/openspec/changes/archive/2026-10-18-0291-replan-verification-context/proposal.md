# 0291 — 任务级验收反馈闭环（重拆携因 + 标准可见 + 退化守卫）

## Why

2026-10-18 的真实 `task` 冒烟：两个子任务均通过，任务级判定因「缺少 CLAUDE.md 原文引用」
失败；但重拆输入没有携带这条原因，planner 把「整理说明」当子任务又跑一遍，唯一一次重拆
预算耗尽，任务以 `PROGRESS_NOT_MET` 终态。三处缺陷同源：

1. `_replan_input` 只在 `failure.failed` 非空时输出原因，而任务级 `_Failure` 的
   `failed=[]` ⇒ 判定器给出的原因被丢弃；成功标准也从未进入重拆输入。
2. 执行者只看到 `subtask.acceptance`，看不到 `plan.success_criteria` ⇒ 首轮就不可能
   满足整体验收。
3. LLM 拆解失败回落会把 decomposer 输入原样作为 `goal`；重拆时若回执退化，该「子任务」
   会被当作新工作再执行一遍，浪费最后一次机会。

## What Changes

- **重拆输入以任务级失败信息开头**（`_replan_input`）：任务级未达标分支输出
  「任务级验收未通过：{reason}」＋「任务级成功标准」清单＋「全部子任务已完成但整体未达标」
  的明确尾句；失败段与标准各自有界（各 600 字符），原始目标也有界（600 字符），保证
  2000 字符硬截断后失败段仍存活。**子任务失败 / 死循环分支的文案与顺序逐字不变。**
- **执行者首轮看到任务级标准**（`_build_handoff`）：非空的任务级标准追加到
  `TaskHandoff.acceptance`（不新增字段、不改动 `subtask.acceptance`），组合结果整体有界
  到 `MAX_HANDOFF_CHARS`；无标准时 `acceptance` 与现状逐字节相同。
- **退化重拆 fail-fast**：重拆回执中任一子任务的 `goal`（去空白）精确等于重拆输入
  （去空白）⇒ 判 `FAILED`（`SUBTASK_VERIFY_FAILED`），不执行该回执。仅作用于重拆，
  初次拆解的离线回落保持现状。

## Non-goals

- 不放松 `LLMTaskVerifier` 判定口径，不增加重拆预算（仍为 1）。
- 不给 `TaskHandoff` 新增字段；不用任务级标准改变子任务验证语义。
- 不新增配置项、不新增 CLI 子命令、不新增错误码。

## Impact

- 代码：`src/core/orchestration/scheduler.py`。
- 规格：`orchestration` 三条 MODIFIED delta（子任务拆解 / 多 Agent 协同 / 目标监控）。
- 测试：新增 11 例（重拆 6 + 交接 5）；全量 3241 → 3252。
- 文档：ADR-0281、台账 E227、test-cases §204、orchestration 接口与模块文档。
- 缺省行为：无任务级标准、子任务失败 / 死循环重拆路径逐字不变。
