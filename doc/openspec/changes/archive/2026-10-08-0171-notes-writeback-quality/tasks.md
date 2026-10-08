# 任务：notes 写回质量（change `0171` / ADR-0162 / 台账 E108）

## 0. 规格与设计
- [x] `specs/notes/spec.md` delta（MODIFIED「Consult → Build → Update 循环纪律」+ 2 Scenario）
- [x] `proposal.md` / `design.md`

## 1. 测试先行（红 → 绿）
- [x] `tests/test_action_steps.py`（新）：`_action_steps` 可读渲染 / 有界 / 无 JSON dump / 纯回复轮为空
- [x] `tests/test_notes.py`：有意义闸门 —— `observe_turn(task, [], ok=True) is None`（不落盘）
- [x] `tests/test_notes_loop.py`：既有写回断言改可读形态 + 断言正文不含 `{"tool_id"`
- [x] 红态取证（stash 实现 ⇒ 新用例全红）

## 2. 实现
- [x] `src/core/loop/default.py`：重写 `_action_steps` + `_decode_action` / `_summarize_args` /
      `_summarize_value` / `_summarize_result` + 常量 `_MAX_STEP_VALUE` / `_MAX_STEP_LINE`
- [x] `src/core/notes/store.py`：`observe_turn` 增有意义闸门（`not steps ⇒ None`）+ docstring

## 3. 文档 / 台账
- [x] `doc/01-architecture/adr.md`：ADR-0162 + 变更追踪行
- [x] `doc/03-interfaces/loop-interface.md` §3 收尾钩子：`steps` 渲染契约
- [x] `doc/03-interfaces/notes-interface.md` §3：`observe_turn` 可读正文 + 有意义闸门
- [x] `doc/02-modules/loop.md` §3.4：行动序列人类可读（一句）
- [x] `doc/04-testing/test-cases.md`：`## 84.`（TC-NOTES-WRITEBACK）
- [x] `coding-plan/known-risk.md` §1 新行 **E108** + §3 ADR-0162 局限行

## 4. 门禁（直连二进制，**禁** `uv run`）
- [x] `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] `/home/harry/.praisonai/venv/bin/pyright` ⇒ **0 / 0 / 0**
- [x] `.venv/bin/pytest -q` ⇒ 全绿（基线 **1962**，本 change 实跑 **1973 passed**，+11）

## 5. 归档（手工 —— `openspec archive` 在本仓恒失败）
- [x] delta 合进 canonical `doc/openspec/specs/notes/spec.md`
- [x] `mv` 到 `doc/openspec/changes/archive/2026-10-08-0171-notes-writeback-quality/`
- [x] `openspec validate --all` ⇒ **31 / 0**

## 6. 收口
- [x] 台账 + 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）
- [x] **单次提交**（`fix(loop): notes 逐轮写回改人类可读 + 有意义闸门（change 0171 / ADR-0162 / 台账 E108）`）

## 端到端目视（用户）
- [ ] 跑一轮含工具调用的会话后，查看 `$CORE_STATE_DIR/notes/*.md`：`## 解决过程` 应为可读行、
      不含 `{"tool_id"` / `{"data"`；发一句纯文字（如「你好」）应**不**新增 / 不改写任何笔记。
