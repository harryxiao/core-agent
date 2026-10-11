# Tasks 0214 — 主循环会话轮级检查点（`turn.<trace_id>`）

## 1. 规格（spec-first）

- [x] `specs/durability/spec.md`：**ADDED**「会话轮级检查点」＋ Scenario ×5（轮首未完结 / 轮末完结 /
      中途中断留未完结 / 启动扫描独立呈现不提示续跑 / 缺省关零写入）
- [x] ADR-0204 +「变更追踪」表行
- [x] 既有 `durability` Requirement（检查点与快照 / 崩溃恢复 / 时间旅行 / 生命周期与保留策略）
      **逐字保留**（本 change **不** MODIFY 任何既有 Requirement）

## 2. 测试先行（红）

- [x] 新 `tests/test_turn_checkpoint.py`（离线 loop 模板 `test_longtask_e2e.py`）：
  - 正常轮 ⇒ 同一 `turn.<trace_id>` 的两次写序为 `done=False` → `done=True`（轮首/轮末）
  - 注入异常的 `act` ⇒ 只到 `done=False`（**留未完结**，不误报完结）
  - 达 `max_rounds` 的终止轮 ⇒ 仍写 `done=True`（轮末在 `limit_reason` 分支之外）
  - 中断轮呈现**不含** `task --resume`；编排任务仍含
  - 缺省关（`turn_checkpoint=None`）⇒ 零写入（零回归锚）
  - 配置三面：`loop.turn_checkpoint: true` ⇒ 组合根接线；缺省 / 非法值阻断
  - **反证**：摘轮末置 `True` ⇒ 误报中断锚红；摘轮首写 ⇒ 无检查点锚红

## 3. 实现（绿）

- [x] `src/core/loop/default.py`：`TurnCheckpoint = Callable[[str, str, str, bool], None]` 类型别名；
      `__init__` 新可选参 `turn_checkpoint=None`；轮首（`_load_pinned_notes` 后）写 `False`、
      轮末（`remember` 后）写 `True`（经私有 `_mark_turn`）
- [x] `src/core/runtime.py`：`_TURN_TASK_PREFIX = "turn."` / `_TURN_KIND = "turn"`；主 loop 传
      `turn_checkpoint=_turn_checkpoint`；闭包（**晚绑定** `checkpoints` / `retention_policy`，
      `try/except DurabilityError → warn`）；`_recover_incomplete` 分流跳过轮面；
      新 `_turn_incomplete(checkpoints)` + `Runtime.recover_turns()`；§11 红线：`exclude_source_prefixes`
      逐字不动
- [x] `src/core/entry.py`：`_surface_incomplete` 扩一段轮面呈现（**不**给 `task --resume`）
- [x] `src/core/configuration/manager.py`：`loop.turn_checkpoint`（bool 缺省 False）校验
      （`_loop_errors`，镜像 `block_plan` / `causal_links`）+ 访问器 `turn_checkpoint()`

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：见 §2 末
- [ ] `openspec validate 2026-10-11-0214-loop-turn-checkpoint`
- [ ] 手工归档（ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §127 + 基线 bump；台账 E151（`known-risk.md` §1）+
      §3 ADR-0204 行；`doc/02-modules/durability.md` / `loop.md` 增补；`doc/03-interfaces/durability-interface.md`
- [ ] 单次提交 `feat(durability): 主循环会话轮级检查点（change 0214 / ADR-0204 / 台账 E151）`
