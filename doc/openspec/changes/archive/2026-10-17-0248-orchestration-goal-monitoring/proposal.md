# Proposal — 目标监控（change 0248）

## 为什么

只读盘点（`/tmp/orchestration-review.txt` P1-8）确认规格 R6「目标监控」三项承诺均未落地：

1. **成功标准无生产者**：`_DECOMPOSE_SYSTEM` 只输出 `subtasks`，`Plan.success_criteria`
   仅能由调用方显式传入；`task` CLI / TUI 入口都不传 ⇒ 产线计划恒为空标准。
2. **任务级判定接不上**：`TaskScheduler.success_checker` 签名是 `Callable[[list[str]], bool]`，
   判定器只看标准文本、看不到子任务结果；组合根（`runtime.py`）**未注入** checker ——
   若 planner 开始生成标准，所有生产任务会以 `MISSING_SUCCESS_CHECKER` 失败。
3. **进度只有完成集**：`ProgressTracker` 只记 `completed`，无从区分「已开始 / 失败待恢复 /
   已完成」，规格要求的「每子任务进度 + 整体推进」没有可观测面。

用户裁决（2026-10-17）：成功标准 **planner 拆解时自动生成、缺省开启**，任务终态由 LLM
对照判定。

## 改什么

- `models.py` 新增 `DecomposeResult(subtasks, success_criteria)`；`Planner` 协议接受
  `list[Subtask] | DecomposeResult`（既有返回 list 的测试桩全部兼容）。
- `LLMSubtaskPlanner`：拆解 prompt 顶层改为
  `{"success_criteria": [...], "subtasks": [...]}`；`_parse` 解析标准（非空字符串、strip、
  去重、至多 5 条），并顺带修两处拆解正确性 —— `depends_on` 先 strip 再判成员（现会静默
  丢空白依赖）、重复 id 保留首个（现会误报 `DEADLOOP_DETECTED`）。回落单子任务**不带标准**
  （planner 失败时同源判定 fail-closed 会把任务拖死）。
- `SubtaskDecomposer.decompose`：显式非空标准优先，否则采用 planner 生成标准；
  `Plan.success_criteria` 落定。重拆沿用 0246 的「原标准非空则保留」。
- 新增 `LLMTaskVerifier`（`planner.py`）：**复用** `_VERIFY_SYSTEM` 与单次重试 / fail-closed
  路径；输入 Goal + 标准 + 子任务结果摘要（有界、经 `redact_secrets` 脱敏）。
- `TaskScheduler.success_checker` 签名改为
  `Callable[[str, list[str], list[SubtaskOutcome]], VerifyResult | Awaitable[VerifyResult]]`；
  `_success_met` 改 async 并接收 outcomes；判定器异常/非法返回 fail-closed；未达标接入
  0246 恢复回路（重拆预算未用尽则重拆，否则 `FAILED`）。
- `ProgressTracker` 增 `started` / `failed` 两态与 `progress()` 计数；重试开始与 `record`
  清除失败标记；重拆 `reset` 清空三态；`detect_stall` 仍以 completed 签名判定。
- 组合根注入 `LLMTaskVerifier(llm, model=app.llm.model)`（缺省开启；与标准生成**同 change**
  落地，避免 `MISSING_SUCCESS_CHECKER` 全量失败）。
- prompt 钉死副本与镜像同步（常量行 + 落点行号）。

## 影响面

- `src/core/orchestration/{models,planner,decomposer,scheduler,__init__}.py`
- `src/core/runtime.py`（checker 注入）
- 规格：`orchestration` R6「目标监控」**MODIFIED**（+3 Scenario）
- 文档：`03-interfaces/prompts.md`、`03-interfaces/orchestration-interface.md`、
  `02-modules/orchestration.md`
- 测试：`tests/test_orchestration.py`、`tests/test_orchestration_difficulty.py`、
  `tests/test_prompt_pinning.py`；新增目标监控用例

## 不做

- 不新增配置键（用户裁决缺省开启；无开关）。
- 不新增 prompt 常量（任务级判定复用 `_VERIFY_SYSTEM`，镜像无新增条目）。
- 不改子任务验收门（`LLMVerifier`）与既有事件序列；成功路径事件逐字不变。
- 不把 `SubtaskOutcome` 迁入 `models.py`（无必要重构）。
