# Proposal 0239: 并行批次五红收口 —— post-turn 跨 loop 取消传播 ＋ benchmark 桩适配 0236

## 为什么

change `0238` 收口时全量 pytest 有 **5 个行为性红**（`git stash` 于干净 HEAD 原样复现 ⇒
均为并行批次 7357a11（change 0233）与 0236（387aee2）引入的回归，非 0238 所致）：

**红组一（3 个，`CancelledError`）**：`test_history_persistence::test_second_turn_makes_history_grow`、
`test_longtask_e2e::test_compaction_product_reaches_next_turn_system_prompt`、
`test_orchestration::test_scheduler_astream_failure_visible`。

**红组二（2 个，空壳门拒）**：`test_benchmark_runner::{test_gate_off_still_freezes_despite_registered_benchmark,
test_gate_on_produces_held_out_score}`。

## 根因

**组一（生产真缺陷，非测试假象）**：7357a11 把轮末收尾（`_notify_turn`/`_maintain`）改为
**实例属性上的后台 task**（`_post_turn_task`，`create_task` 于当轮 loop）。走 `astream` 的
调用方（scheduler / 事件流消费者）在 `loop_finished` 后**不等**收尾 ⇒ task 残留实例上。
下一次调用若在**新 event loop**（`DefaultLoop.run()` 同步入口、`TaskScheduler.run`、测试驱动
—— 每次 `asyncio.run` 新建 loop），旧 loop 关闭清理已把残留 task **cancel** ⇒ 新一轮
`_await_post_turn` 的 `await task` 在已取消 task 上**重放 `CancelledError`**，杀死整轮。
生产可达：同一 loop 实例连续两次 `run()`（同步入口）即触发。

**组二（测试桩漂移）**：0236 装配 `Proposer(writer=skill_content_writer_with(_llm_text))` ＋
`Validator(require_skill_content=True)`（空壳 fail-closed）。`test_benchmark_runner` 的
`_StubProvider` 对**所有**模型请求回同一句 `"PASS"` ⇒ 内容蒸馏 `json.loads("PASS")` 失败 ⇒
writer 回 `None` ⇒ 候选无 content ⇒ 门在 review 前 fail-fast 拒 ⇒ `eval=None`，两用例断言
`eval`/`frozen` 失败。0212 时期的桩不知道「内容生成」这一类请求。

## 做什么

1. **`default.py::_await_post_turn`**：捕获 `CancelledError` 后以 `task.cancelled()` 区分 ——
   task 自身已被宿主取消（loop 关闭清理）⇒ **放行**（后台收尾本是尽力而为语义，取消态不得
   杀死新一轮）；当前协程被取消（用户打断等）⇒ 照常 `raise` 传播。
2. **`test_benchmark_runner.py` 桩**：`acompletion` 按 prompt 分派 —— 含 0236 蒸馏 prompt 头
   「技能内容蒸馏器」⇒ 回合法 `SkillContent` JSON（`task_types` 非空 + `instructions` 非空 +
   `param_schema` dict）；其余照旧回 `"PASS"`。

## 能力

- loop / evolution（**规格中性**：loop spec 无「跨 loop 取消传播」面约束 —— 0233 未动 loop
  spec；组二为测试桩适配 0236 既有规格语义，规格零改动）

## 影响

| 面 | 影响 |
|---|---|
| `src/core/loop/default.py` | `_await_post_turn` 增 `except CancelledError` ＋ `task.cancelled()` 分野（+7 行含注释） |
| `tests/test_benchmark_runner.py` | 桩 `acompletion` 按 prompt 分派 ＋ `_SKILL_CONTENT_JSON` 常量 |
| 测试基线 | 2650 → **2655**（5 红转绿，无新增用例 —— 既有红测试即承重锚） |
| 显式不做 | 不改 `_schedule_post_turn` 的挂出时机；不给跨 loop 残留做主动清扫（`await` 时的分野已足够）；不收窄 0236 空壳门；不改 0233/0236 的 spec delta（0233 归档欠账另行处理） |
