# 任务 — `reuse_count` 落盘持久化（change 0187 / ADR-0178 / 台账 E124）

## 1. 规格（spec-first）

- [x] `specs/memory/spec.md` — MODIFIED「温度分层检索」（复用强化：进程内 → 持久化 + 有界 + 可逆）
      + 1 新 Scenario；既有 6 Scenario 逐字保留
- [x] `proposal.md` / `design.md`（含「为何必改」D1：后端 `search` 返回同引用 ⇒ 进程内改了、磁盘没改）
      / `tasks.md`

## 2. 红测试（先失败）

- [x] `tests/test_memory.py` 新增节「复用强化落盘」：
      跨会话保持（同 backend 新建 store）/ 未命中不写（回归锚）/ 写回可回滚（`rollback("reuse.<id>")`
      ⇒ 原值）/ 有界（只写 `_truncate` 选中条目）
- [x] 既有 `test_read_reinforces_reuse_count` 继续绿（回归锚）
- [x] 确认红

## 3. 实现

- [x] `src/core/memory/store.py`：`read()` 末尾裸循环 → 私有 `_reinforce(selected)`（自增 + `_backend.put`
      + 记效应 trace `reuse.<id>`）+ `_undo_reuse(id, layer, value)`（照 `_undo_migrate` 查表形状）
- [x] **不**把读条目插入 `_hot`（避免无界隐式缓存）

## 4. 四门禁（直连二进制）

- [x] `.venv/bin/ruff check src tests` → All passed
- [x] `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [x] `.venv/bin/pytest -q` → 基线 2196 → 2200（+4）

## 5. 归档（手工）

- [x] `openspec validate 2026-10-10-0187-reuse-count-persistence` → valid
- [x] 脚本化合并（MODIFIED 替换同名 Requirement 块；断言 0 标题丢失 / 未触碰块逐字不变）⇒ `mv` 至 archive
- [x] `openspec validate --all` 全绿

## 6. 文档 / 台账

- [x] `doc/01-architecture/adr.md`：ADR-0178 + 变更追踪行
- [x] `doc/02-modules/memory.md`；`doc/03-interfaces/memory-interface.md`
- [x] `doc/04-testing/test-cases.md` 新 TC 节（§100）+ 基线 bump
- [x] `coding-plan/known-risk.md` §1 E124 行 + §3 ADR-0178 局限行

## 7. 记忆 / 提交

- [x] `MEMORY.md` + `coding-plan-leftover-walkthrough.md`（`0187` 节 + 批次进度）
- [x] 单次提交 `feat(memory): …（change 0187 / ADR-0178 / 台账 E124）`
