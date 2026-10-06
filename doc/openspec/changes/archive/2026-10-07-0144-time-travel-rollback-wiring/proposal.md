# 0144 · 时间旅行回滚生产入口接线（skip_specs）

> 账本：`coding-plan/phase-34.md` **E73**（`TimeTravel.rollback` 不可达：检查点持久化在用，时间旅行回滚无生产调用方）
> 规格面：**无 delta**（`durability/spec.md`「时间旅行」及两个 Scenario 早已是硬 SHALL）
> ADR：**0136** ｜ 用户裁决（§6.5 终裁）：**E73 / E77 死面 = 都补齐接线**

## Why

`durability/spec.md`「时间旅行」SHALL「将执行态回滚（rollback）到任意历史检查点……与 tool-use
副作用级 EffectId undo 栈协同，不新建撤销机制」，并以两个 Scenario 定格：「回滚到历史检查点」
（**上层请求**回滚 ⇒ 执行态恢复到该检查点快照）与「与副作用级回滚协同」（沿历史逆序调用各写类
工具的撤销函数）。而实现是**死面**（E73）：

- `durability/manager.py:132-149` `TimeTravel.rollback()` 实现完整，`runtime.py:853` 以
  **生产真源**（`CheckpointStore(_checkpoint_path())` + 与 `tools` / `memory` **共享**的
  `EffectTracker`）构造、`:1033` 注入 `Runtime`，但**全仓零生产调用方** —— 仅测试直调
  （`test_durability.py` / `test_phase15.py`）⇒ 「上层请求」这一环**不存在**。
- 检查点**持久化**本身在用（`task --resume` 依赖，E12 指此路径）⇒ 缺的不是存储，而是
  **回滚请求的入口**。

## What

**不改规格、不改动既有语义**，只补一个生产入口把 `Runtime.time_travel.rollback` 接通
（全部为**增量**，既有命令面/行为逐字不变）：

1. **CLI 入口**：新增顶层动词 `core-agent time-travel <checkpoint-id>`（`entry._add_time_travel_parser`
   + `_time_travel` handler + `_HANDLERS` 路由）。
2. **复用生产装配，不另起存储真源**：handler 经 `build_runtime(_config_manager(args))` 取
   `runtime.time_travel` —— 与 `task` / `run` 同一组合根、同一 `$CORE_STATE_DIR/checkpoints.jsonl`、
   同一共享 `EffectTracker`（`test_phase15` 已锚定 `tools._tracker is time_travel._effect_tracker`）。
3. **结构化失败**：检查点不存在 ⇒ `DurabilityError(CHECKPOINT_NOT_FOUND)` 转 `回滚失败: …`
   + 退出码 1（不伪造成功、不静默）。
4. **回执**：打印回滚到的检查点 id、恢复的状态键数与撤销集（`state["trace_ids"]`）条数。

## 影响

- **零回归**：既有 32 动词、14 flag、全部行为不变；新动词只**增量**加入命令面（33 动词），
  `cli-contract-baseline.md` / `user-guide.md` / `entry` 模块 docstring 的计数同步 32 → 33。
- **`durability/manager.py` 一行未改**：本 change 是**纯接线**（E73 定性为「设计缺失（死面）」，
  非实现缺陷）⇒ 撤销集语义（`state["trace_ids"]` 为该检查点的撤销集，`test_phase15` 锚定）
  与「沿快照差异逆序」的既有实现**不动**（见 ADR-0136 已知局限①）。
- **跨进程撤销集天然为空**：`Effect` 的 `undo` 是进程内闭包、不可持久化 ⇒ 一次性 CLI 进程
  调用时撤销循环为空转，**快照恢复与错误语义仍生效**；撤销协同在**同进程**（`serve` / REPL /
  同一 runtime 内的 `task`）生效 —— 与 `test_phase15` 的运行时路径一致（见已知局限②）。

## 验证

- `.venv/bin/ruff check src tests` / `ruff format --check` 全绿；`pyright` **0/0/0**。
- `.venv/bin/pytest -q` ⇒ 基线 1693 + 本 change 新增（`test_entry` +3、`test_durability` +1）。
- `openspec validate --all` ⇒ 30 passed / 0 failed（无 delta ⇒ 计数不变）。

## 风险与已知局限

- **CLI 新动词**：命令面 32 → 33，三处计数文档同步（`cli-contract-baseline.md` §1/§2.12、
  `user-guide.md`、`entry.py` docstring）；`tests/test_entry.py::_TOP_LEVEL_COMMANDS` 同步 +1
  （该集合为**子集断言**，新增动词不破坏断言，但须钉住以守恒）。
- **无 Rust/JS 面**：本 change 全 Python，四门禁即可覆盖。
