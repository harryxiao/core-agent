# Tasks 0194 — 摘要注入与历史回放解耦

## 1. 规格（spec-first）

- [x] `specs/loop/spec.md`：MODIFIED「执行循环」（+两层摘要注入与历史回放开关**解耦**条款
      + 1 Scenario「关闭历史回放仍注入摘要」），既有 Scenario 标题零丢失
- [x] ADR-0184（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_loop.py`：`history_turns=0` 且会话已有摘要 ⇒ 摘要块**仍注入** system prompt
      （红：变更前 `_load_summaries` 返回 `("","")`）
- [x] `test_loop.py`：`history_turns=0` ⇒ 历史带**确为空**（无原文回灌；摘要与历史两通道各自独立）
- [x] `test_loop.py`：`history_turns>0` 回归 —— 摘要注入与历史回灌**逐字不变**
- [x] `test_loop.py`：诚实化 —— `_load_summaries.__doc__` 不含「完全同形」、含「解耦」/「连坐」

## 3. 实现（绿）

- [x] `loop/default.py`：`_load_summaries` 门控删 `self._history_turns <= 0` + docstring 诚实化

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
      （**2229 passed** = 2227 + 3 新增 − 1 参数拆分）
- [x] `openspec validate 2026-10-11-0194-summary-injection-decoupling`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E131（`known-risk.md` §1）+
      `doc/02-modules/loop.md` / `doc/03-interfaces/loop-interface.md` 对应面
- [x] 单次提交 `feat(loop): …`
