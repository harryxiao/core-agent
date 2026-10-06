# tasks — 可逆效应账的清账与幂等（change 0128 / phase-34 E67）

## 1. 规格（先行）
- [x] 1.1 `specs/plugin-registry/spec.md`：**ADDED Requirement「可逆效应追踪（清账与幂等）」** ——
      账 / 回滚 / 清账三件套的 SHALL 口径（撤销成功即出账、不可逆随清账出账、失败留账隔离、
      `clear(trace_id=None)` 显式清账）
- [x] 1.2 同 delta：4 个 Scenario（出账 + 重复回滚幂等 / 回滚后账清空且 trace 隔离 /
      失败者留账隔离 / 显式清账不触发 undo）
- [x] 1.3 `openspec validate 0128-reversible-effect-ledger` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_plugin_registry.py`：**幂等** —— 同一 trace 连滚两次 ⇒ 首次 undo 逐条各一次、
      二次 `reverted` 与 `undo_failed` **均空**且 undo **不再被调用**（现状：二次仍撤销 ⇒ 红）
- [x] 2.2 同文件：**清账** —— 回滚后 `audit(trace)` 为 `[]`；全局回滚后账目回零（现状：仍在账 ⇒ 红）
- [x] 2.3 同文件：**trace 隔离** —— 回滚 `t1` 不影响 `t2` 的账目；不可逆效应随清账出账
- [x] 2.4 同文件：**失败隔离** —— undo 抛错者仍在账（`audit` 可见）且计入 `undo_failed`；
      其余正常出账、回滚不抛异常
- [x] 2.5 同文件：**显式清账** —— `clear("t1")` 移除该 trace 账目且**不调用** undo；
      `clear()` 清空全局
- [x] 2.6 既有 `test_effect_tracker_rollback_and_audit` 的保序断言**前置到回滚前**（语义变更后的对齐，
      非放宽）
- [x] 2.7 红：2.1 / 2.2 在实现前**必失败**

## 3. 实现
- [x] 3.1 `src/core/plugin_registry/effect_tracker.py:rollback`：撤销成功（与不可逆）即出账
      （`_effects.pop` + 清 `_by_trace[trace]`，空键删）；失败者留账
- [x] 3.2 同文件：新增 `clear(trace_id=None)` —— 只清账、不触发 undo
- [x] 3.3 同文件：类 / 方法 docstring 与模块 docstring 同步（清账语义 + 幂等）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1605 passed ⇒ 新增后按实累加）
- [x] 4.5 `openspec validate --all`（归档前后各一次，30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/plugin-registry/spec.md`（`### Requirement:`
      正文紧接、`#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0128-reversible-effect-ledger/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0121**（清账放 rollback 内 + 另给 clear / 失败留账但空键删 /
      不可逆随清账出账 / 已知局限：未回滚的 trace 仍留账；变更追踪表行）
- [x] 6.2 `doc/03-interfaces/plugin-registry-interface.md` §4：补 `clear` 与清账 / 幂等语义
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行
- [x] 6.4 `coding-plan/phase-34.md`：§1 真缺陷表 **E67** 行标「已落地（change `0128` / ADR-0121）」；
      §9 台账行同步；`coding-plan/README.md` 索引同步
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`fix(plugin-registry): 可逆效应账清账与幂等（change 0128）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（D4 不动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-32.md`、`src-tauri/Cargo.lock`、`node_modules/`、
      `frontend/dist/`
