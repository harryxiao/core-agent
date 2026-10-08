# 任务：notes 写回效应闸门（change `0176`）

## 0. 规格与设计
- [x] `specs/notes/spec.md` delta（MODIFIED「Consult → Build → Update 循环纪律」+ 3 Scenario）
- [x] `proposal.md` / `design.md`

## 1. 测试先行（红 → 绿）
- [x] `tests/test_notes.py`：效应闸门 ——
  - 纯读参数化（`web_fetch` / `file_read` / `context_read` / `list`）⇒ `observe_turn(...) is None`
  - 写效应参数化（`file_write` / `file_patch` / `code_run` / `gate_run` / `install` / `uninstall`）⇒ `is not None`
  - 写效应失败（行含 `错误：`）⇒ `is None`
  - 非工具行形态（散文 steps）⇒ `is None`（保守）
  - 读写混轮（含一个成功写效应）⇒ `is not None`
- [x] `tests/test_notes_loop.py`：真 loop + 只读替身工具 ⇒ 不写回
- [x] 连带调整既有用例 steps 口径（散文占位 / 只读替身 ⇒ 工具行形态写效应 steps，10 处）
- [x] 红态取证（实现前 ⇒ 7 failed / 79 passed）

## 2. 实现
- [x] `src/core/notes/store.py`：`observe_turn` 追加效应闸门 +
      `_WRITE_EFFECT_TOOLS` / `_TOOL_ID_PREFIX` / `_ERROR_MARKER` + `_tool_of_step` /
      `_has_write_effect` + docstring

## 3. 文档 / 台账
- [x] `doc/01-architecture/adr.md`：ADR-0167 + 变更追踪行
- [x] `doc/02-modules/notes.md` §3.5：效应闸门
- [x] `doc/03-interfaces/notes-interface.md` §3：`observe_turn` 效应闸门
- [x] `doc/04-testing/test-cases.md`：新增 TC（TC-NOTES-EFFECT-GATE）
- [x] `coding-plan/known-risk.md` 新行（E113）+ §3 ADR-0167 局限行

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] `.venv/bin/ruff check src tests`
- [x] `.venv/bin/ruff format --check src tests`
- [x] `pyright` ⇒ 0 error
- [x] `.venv/bin/pytest -q` ⇒ 全绿

## 5. 归档（手工）
- [x] delta 合进 canonical `doc/openspec/specs/notes/spec.md`
- [x] `mv` 到 `doc/openspec/changes/archive/2026-10-09-0176-notes-write-effect-gate/`
- [x] `openspec validate --all`

## 6. 收口
- [x] 台账 + 记忆
- [x] 单次提交（`fix(notes): 写回效应闸门——纯读轮不落盘（change 0176）`）
