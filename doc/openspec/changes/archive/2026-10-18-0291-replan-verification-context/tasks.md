# 任务 — 0291 任务级验收反馈闭环

## 1. 规格

- [x] 1.1 `specs/orchestration/spec.md`：MODIFIED「子任务拆解」（重拆携任务级上下文、
      退化回执 fail-fast；初拆回落不变）。
- [x] 1.2 同文件 MODIFIED「目标监控」（任务级未达标时原因与标准进入重拆请求，有界）。
- [x] 1.3 同文件 MODIFIED「多 Agent 协同」（`acceptance` 组合任务级标准、整体有界、
      子任务验证语义不变；无标准时逐字一致）。
- [x] 1.4 `openspec validate 2026-10-18-0291-replan-verification-context` 全绿。

## 2. 代码（测试先行）

- [x] 2.1 `tests/test_orchestration.py`：任务级理由+标准进入重拆输入、顺序在「已完成」之前、
      6000 字目标仍保留失败段、子任务失败分支不变。
- [x] 2.2 同文件：退化回执 fail-fast（执行器只被调用一次 = 首计划执行，退化回执的子任务
      不执行）、部分退化同样 fail-fast。
- [x] 2.3 `tests/test_orchestration_handoff.py`：标准追加进 acceptance、无标准逐字节不变、
      组合有界（1900 字 + 5 条长标准）、首轮 prompt 含标准、子任务验证器仍收原文 acceptance。
- [x] 2.4 `src/core/orchestration/scheduler.py`：`_MAX_REPLAN_GOAL_CHARS` /
      `_MAX_REPLAN_CRITERIA_CHARS`、`_task_criteria_text`、`_replan_input` 分支、
      `_build_handoff` 组合、退化守卫。

## 3. 文档

- [x] 3.1 `doc/01-architecture/adr.md`：ADR-0281。
- [x] 3.2 `coding-plan/known-risk.md`：E227 行 + ADR-0281 局限索引。
- [x] 3.3 `doc/04-testing/test-cases.md`：§204。
- [x] 3.4 `doc/03-interfaces/orchestration-interface.md`：重拆输入内容与边界、
      `acceptance` 组合。
- [x] 3.5 `doc/02-modules/orchestration.md`：重拆回路与交接标准可见。

## 4. 门禁

- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`
- [x] 4.4 `.venv/bin/pytest -q`（3241 → 3252）
- [x] 4.5 反证 3/3（cp 到 /tmp，禁 `git checkout`；复原后 md5sum 一致）。
- [x] 4.6 端到端：真实模型 + 真实调度器的注入式 e2e（固定任务级判定失败以触发重拆）
      确认重拆输入含原因与标准；真实 planner 回落 echo 时退化回执按
      `SUBTASK_VERIFY_FAILED` 收口；真实 `task` CLI 冒烟通过、零告警。
- [x] 4.7 `openspec archive -y 2026-10-18-0291-replan-verification-context` 后再跑
      `validate --all`。
- [x] 4.8 仅暂存本 change 路径并提交。
