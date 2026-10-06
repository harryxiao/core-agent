# Tasks · 0144 时间旅行回滚生产入口接线（skip_specs）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（`durability/spec.md`「时间旅行」+ 两 Scenario 早已是硬 SHALL，缺的是
      **入口**而非语义 ⇒ conformance）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`）
- [x] 1.2 `openspec validate 0144-time-travel-rollback-wiring` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_durability.py`：`TimeTravel.rollback` 未知检查点 ⇒ `CHECKPOINT_NOT_FOUND`
      （该错误路径此前**无测试**，而它正是新入口的失败面）
- [x] 2.2 `tests/test_entry.py`：`_TOP_LEVEL_COMMANDS` 钉住 `time-travel`（命令面守恒）
- [x] 2.3 `tests/test_entry.py`：`time-travel <cp>` **委派**到 `runtime.time_travel.rollback`
      （桩记录入参 ⇒ 反回归「无生产调用方」），退出码 0 + 回执含检查点 id
- [x] 2.4 `tests/test_entry.py`：检查点不存在 ⇒ 退出码 1 + `回滚失败` 走 stderr
- [x] 2.5 `tests/test_entry.py`：**跨进程**真子进程 `python -m core.entry time-travel <cp>`
      —— 检查点落盘可寻址（`$CORE_STATE_DIR/checkpoints.jsonl`）⇒ 退出码 0、打印该 id
- [x] 2.6 **验绿**：实现后全绿（红因动词未接线 —— argparse 不识别 `time-travel`）

## 3. 实现

- [x] 3.1 `src/core/entry.py`：`_add_time_travel_parser(sub)` —— `time-travel <checkpoint-id>`
- [x] 3.2 `src/core/entry.py`：`_time_travel(args)` —— `build_runtime` 取生产真源
      `runtime.time_travel.rollback(cp)`；`DurabilityError` ⇒ `回滚失败: …` + 退出码 1
- [x] 3.3 `src/core/entry.py`：`_HANDLERS["time-travel"] = _time_travel` + `core.durability` 导入
- [x] 3.4 `src/core/entry.py`：模块 docstring 命令面计数 32 → 33

## 4. 文档

- [x] 4.1 `coding-plan/cli-contract-baseline.md`：§1 计数 32 → 33 + §2.12 时间旅行表（CMD 33）
- [x] 4.2 `doc/03-interfaces/durability-interface.md`：§4 `TimeTravel` 补 CLI 入口口径
- [x] 4.3 `doc/00-product/user-guide.md`：命令面基线计数 32 → 33
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0136 + `## 变更追踪` 行
- [x] 4.5 `doc/04-testing/test-cases.md`：§60（TC-TIMETRAVEL，change 0144 / ADR-0136，账本 E73）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1697 passed**（基线 1693 + 4）
- [x] 5.5 `openspec validate --all` —— 31 passed / 0 failed（归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0144-time-travel-rollback-wiring/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E73 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(durability): 时间旅行回滚生产入口接线（change 0144）`）
