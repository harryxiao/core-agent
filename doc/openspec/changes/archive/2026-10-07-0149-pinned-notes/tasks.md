# 0149 · 任务清单（常驻笔记 / 账本 E93）

> 规格先行 ⇒ 测试先行（红）⇒ 实现 ⇒ 四门禁 ⇒ 手工归档 ⇒ 台账回填 ⇒ 单次提交。
> delta：`notes` **ADDED** Requirement「常驻（pinned）笔记（任务级硬约束锚）」。

## 1. 规格与 ADR（先行）

- [x] 1.1 `specs/notes/spec.md`（delta，ADDED）：新 Requirement「常驻（pinned）笔记（任务级硬约束锚）」+ 6 Scenario（含消歧条文）
- [x] 1.2 `openspec validate 0149-pinned-notes` ⇒ valid；`validate --all` ⇒ 31 passed / 0 failed（归档后 30/0）
- [x] 1.3 ADR-0141（`doc/01-architecture/adr.md`，置于 `## 变更追踪` 之前）＋ 变更追踪行

## 2. 测试先行（红）

- [x] 2.1 `tests/test_notes.py`：B1 omit-when-false 逐字护栏 / B2 pinned 往返 / B3 真值拼写 / B4 set_pinned 持久化+幂等 / B5 未知 id 抛 `NOTE_NOT_FOUND` / B6 pinned_digest 全正文 / B7 空正文与无 pin ⇒ 空串 / B8 确定性+上界 / **B9 observe_turn 保留 pinned（回归护栏）**
- [x] 2.2 `tests/test_notes_loop.py`：B10 零参钩子填 `ctx.pinned_notes` / B11 无钩子留空 / B12 planner 独立块先于「相关笔记」/ B13 空则无块 / B14 失败降级留痕
- [x] 2.3 `tests/test_session_isolation.py`：`test_notes_api_has_no_session_dimension` 参数表加 `pinned`/`pinned_digest`/`set_pinned`
- [x] 2.4 `tests/test_entry.py`：B15 pin/unpin 跨进程往返 / B16 缺失 id 非零退出 / B17 幂等 / B18 list 追加列 + usage
- [x] 2.5 红态确认：新增用例实现前**失败**（`pinned` AttributeError / 缺标签），既有 23 条 notes 用例全程绿

## 3. 实现

- [x] 3.1 `src/core/notes/models.py`：`NoteEntry.pinned`（末位）＋ `_TRUTHY`/`_to_bool` ＋ `render_note` 条件行（False 省略）＋ `parse_note` 读回
- [x] 3.2 `src/core/notes/store.py`：`_MAX_PINNED_CHARS = 4000` ＋ `pinned()`（note_id 升序）＋ `pinned_digest()`（全正文、空正文跳过、有界）＋ `set_pinned()`（幂等、走 `update()`）＋ **`observe_turn` 携带既有 `pinned`**
- [x] 3.3 `src/core/loop/protocol.py`：`LoopContext.pinned_notes: str = ""`
- [x] 3.4 `src/core/loop/default.py`：`PinnedNotesConsult = Callable[[], str]` ＋ `pinned_notes_consult` 形参 ＋ `_load_pinned_notes`（降级留痕 `pinned_notes_consult_failed`）＋ `astream` 调用点
- [x] 3.5 `src/core/loop/planner.py`：`_system_prompt` 显式化装配顺序 ＋「常驻笔记」块（紧随宪法规则、先于相关事实）
- [x] 3.6 `src/core/runtime.py`：`_pinned_notes` 闭包 ＋ 三处注入（主 / 子 / 神兽 loop）
- [x] 3.7 `src/core/entry.py`：`notes pin|unpin` 子命令 ＋ 处理器 ＋ 分发表 ＋ `_NOTES_USAGE` ＋ `notes list` 追加列 `[pinned]`（非常驻行逐字不变）

## 4. 文档同步

- [x] 4.1 `doc/03-interfaces/notes-interface.md`：§1（字段＋格式示例＋False 省略）、§3（三方法）、§5（loop 接线）、§6（CLI 两行）
- [x] 4.2 `doc/03-interfaces/loop-interface.md`：`LoopContext` 字段块 ＋ 注入面清单加 `pinned_notes_consult`
- [x] 4.3 `doc/02-modules/notes.md`：§3 新增「常驻（pinned）笔记」小节；§5 错误表；§6 关联
- [x] 4.4 `doc/04-testing/test-cases.md`：新增 `## 65.`（TC-PINNED，change 0149／ADR-0141／账本 E93）；就地订正 §27 TC-NOTE-18 陈旧锚点
- [x] 4.5 `coding-plan/known-risk.md`：§1 `E93` → 已修；§3 加 ADR-0141 局限（`E94` 保持未修）

## 5. 门禁与归档

- [x] 5.1 `.venv/bin/ruff check src tests` ⇒ All checks passed
- [x] 5.2 `.venv/bin/ruff format --check src tests` ⇒ already formatted
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` ⇒ 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` ⇒ 基线 + 本 change 新增 ⇒ 全绿
- [x] 5.5 `openspec validate --all` ⇒ 归档前 31/0 ⇒ 归档后 **30/0**
- [x] 5.6 手工归档：delta 合进 canonical ⇒ `shutil.move` 至 `archive/2026-10-07-0149-pinned-notes/`

## 6. 台账与提交

- [x] 6.1 `coding-plan/known-risk.md`（E93 → 已修）；ADR 变更追踪行
- [x] 6.2 记忆更新（`MEMORY.md` ＋ `coding-plan-leftover-walkthrough.md`）
- [x] 6.3 单次提交：`feat(notes): 常驻（pinned）笔记：任务级硬约束锚（change 0149）`
