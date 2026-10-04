# Tasks: 架构级候选强制人工审批（evolution HITL confirm gate）

## 1. 规格先行

- [x] 1.1 `specs/evolution/spec.md` delta：ADDED「架构级候选强制人工审批（HITL confirm gate）」
      （判定 / 门禁 / 可追溯 / 拒绝不放行，5 个 Scenario）
- [x] 1.2 `openspec validate 0046-evolution-hitl-confirm` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/evolution-interface.md`：`GenerationCandidate.risk_level` 字段、
      `confirm(candidate, *, approval=None)` 签名与门禁口径、`CONFIRM_REQUIRED` 错误码
- [x] 2.2 `03-interfaces/permission-interface.md`：`is_approved(ticket)` 谓词
- [x] 2.3 `01-architecture/adr.md`：ADR-0051（风险域固化物 + permission 域判定谓词 +
      confirm 三重校验 + 不新增追溯字段）
- [x] 2.4 `02-modules/evolution.md`：confirm 收口一段同步（HITL 门禁）

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_permission.py`：`is_approved` 对 pending / approved / rejected / expired /
      timeout / superseded 的判定（含 `result` 缺失）
- [x] 3.2 `tests/test_evolution.py`：`Proposer(kind="plugin")` → `risk_level="high"`；
      `kind="skill"` → `"low"`
- [x] 3.3 `tests/test_evolution.py`：high 无审批单 → `CONFIRM_REQUIRED` + 候选仍 `pending` +
      `crystallize` 拒绝
- [x] 3.4 `tests/test_evolution.py`：high 带已批准且目标一致的审批单 → `confirmed` + 可 `crystallize`
- [x] 3.5 `tests/test_evolution.py`：high 带**被拒**审批单 → `CONFIRM_REQUIRED`；
      high 带**目标不符**的已批准审批单 → `CONFIRM_REQUIRED`
- [x] 3.6 `tests/test_evolution.py`：low（skill）不带审批单 `confirm` 成功；未 confirm 时
      `crystallize` 仍拒（回归）

## 4. 实现

- [x] 4.1 `src/core/permission/approval.py`：`is_approved(ticket)` + `__init__.py` 导出
- [x] 4.2 `src/core/evolution/models.py`：`GenerationCandidate.risk_level`（默认 `"low"`）
- [x] 4.3 `src/core/evolution/proposer.py`：按 `kind` 判定 `risk_level`
- [x] 4.4 `src/core/evolution/errors.py`：`CONFIRM_REQUIRED`
- [x] 4.5 `src/core/evolution/engine.py`：`confirm(candidate, *, approval=None)` 三重校验

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
