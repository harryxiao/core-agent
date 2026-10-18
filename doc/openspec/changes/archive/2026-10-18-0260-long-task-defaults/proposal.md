# Proposal 0260 — 长任务默认值（循环轮数 / 子任务超时）

## Why

对比审查（2026-10-18）确认长任务的两个缺省值偏保守：

1. **`loop.max_rounds` 缺省 10 步**：真实编码任务的最小闭环（读文件 → 改文件 → 跑测试 → 看输出 →
   修复）需要 5 步以上，稍有回环即撞上限并返回 `LOOP_LIMIT_EXCEEDED`；用户不显式配置时可用性差。
2. **`orchestration.subtask_timeout` 缺省 0（不设限）**：子任务交接没有 deadline，单个卡死的子任务
   会无限占用调度槽；缺省不设限等于把「长任务」实现成「无界任务」。

## What Changes

- `loop.max_rounds` 缺省 **10 → 20**（配置层常量 + `DefaultLoop` 构造缺省同步，避免直接构造与
  配置缺省分叉）。
- `orchestration.subtask_timeout` 缺省 **0 → 600 秒**；`0` 仍为显式合法值，语义仍是「不设限」。
  `TaskScheduler(subtask_timeout=0)` **构造缺省保持 0**（构造函数语义 = 不设限；生产由组合根
  注入配置值 600），两处缺省口径的差异在 ADR 中记录。
- 规格 `loop` / `configuration` 的缺省值描述同步（MODIFIED）；校验范围不变（`max_rounds` ≥1、
  `subtask_timeout` ≥0）。

## Impact

- `src/core/configuration/manager.py`、`src/core/loop/default.py`。
- 规格：`loop` **MODIFIED** 1 req（默认轮数）；`configuration` **MODIFIED** 2 req（循环预算 /
  编排调度缺省值）。
- 测试：`tests/test_loop_budget_config.py`、`tests/test_llm_config_hot_update.py`、
  `tests/test_orchestration_config.py` 的缺省断言同步；新增「显式 0 仍关闭」与
  「`DefaultLoop` 构造缺省与配置缺省同值」用例。
- 兼容性：显式配置值逐字不变；仅**未配置**时的缺省行为变化（属本次用户裁决）。

## 不做（明确边界）

- 不改 `loop.compact_steps`（6 仍小于 20，步数维度仍可提前触发）。
- 不改 token 预算派生、不改校验上下界、不新增配置键。
- 不给 `TaskScheduler` 构造函数改缺省（只为生产注入点改配置缺省）。
