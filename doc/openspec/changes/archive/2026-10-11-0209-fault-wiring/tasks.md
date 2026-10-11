# Tasks 0209 — 容错件接线

## 1. 规格（spec-first）

- [x] `specs/constraints/spec.md`：**MODIFIED**「容错中间件」（全量替换；narrative 补「重试生产接线
      语义 + 库能力边界 + 回滚单一路径」段 + **ADD** Scenario ×5；既有 7 Scenario 逐字保留）
- [x] ADR-0199 +「变更追踪」表行
- [x] 其余 `constraints` Requirement **逐字保留**

## 2. 测试先行（红）

- [x] 新 `tests/test_fault_wiring.py`：可逆超时第 2 次成功（只记 1 效应）/ 不可逆不重试 /
      策略拒绝不重试 / 耗尽原样返回不降级 / `retry_attempts=0` 缺省逐字不变 / 三面解析 + 非法阻断
- [x] `tests/test_constraints.py` 增补：`Fallback.on_failure` 产响应 / `Pipeline` 洋葱序 +
      逆序 `on_failure` 短路（走出零测试）
- [x] **反证**：摘重试循环 ⇒ flaky 用例红；摘可逆门 ⇒ 不可逆重试用例红

## 3. 实现（绿）

- [x] 新 `src/core/loop/fault_adapter.py`：`FaultChain.wrap`（白名单 + 仅可逆 + 耗尽原样返回）
- [x] `loop/default.py`：新参 `act_wrapper`，`self._act`，`:437` 改 `self._act`
- [x] `configuration/manager.py`：ConfigSpec `constraints.retry_attempts` + 访问器 `retry_attempts()`
      + `_retry_errors` 校验
- [x] `runtime.py`：`retry_attempts > 0` 时构造 `FaultChain` 注入主 / 子 / 神兽三 loop（宠物不接）

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] **反证**：见 §2 末
- [x] `openspec validate 2026-10-11-0209-fault-wiring`
- [x] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` §122 + 基线 bump；台账 E146（`known-risk.md` §1）+
      §3 ADR-0199 行；`doc/02-modules/constraints.md` / `loop.md` 增补
- [x] 单次提交 `feat(constraints): 容错件接线（change 0209 / ADR-0199 / 台账 E146）`
