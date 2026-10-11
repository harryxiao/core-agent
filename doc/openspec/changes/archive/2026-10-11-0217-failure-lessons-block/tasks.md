# Tasks 0217 — 「既往失败教训」注入块（`memory` ＋ `loop`）

## 1. 规格（先行）
- [x] 1.1 `specs/memory/spec.md`：`## MODIFIED Requirements` 「情景链（时序相邻标注）」—— 首段「两件事」→「三件事」、
      (e) 条件化、新增 (h) 只读失败教训读面；既有 7 Scenario 逐字保留 + ADD Scenario ×3。
- [x] 1.2 `specs/loop/spec.md`：`## MODIFIED Requirements` 「执行循环」—— 追加块句（教训载入 + 独立块注入 +
      降级留痕）；既有 41 Scenario 逐字保留 + ADD Scenario ×2。

## 2. 实现（test-first：先写测试，再实现）
- [x] 2.1 `memory/store.py`：`failure_lessons(session_id="", *, limit=5) -> list[MemoryEntry]`（紧随 `session_chain`；
      走 `_all_entries()`，只收 `tags` 含 `failure`、`ts` 降序、有界；**零效应**）。
- [x] 2.2 `loop/protocol.py`：`LoopContext.failure_lessons: str = ""`（独立字段）。
- [x] 2.3 `loop/planner.py`：`_system_prompt` 非空该字段 ⇒ 独立块「既往失败教训：」（紧随「相关笔记」）。
- [x] 2.4 `loop/default.py`：`FailureLessonsConsult = Callable[[str], str]`、新可选参 `failure_lessons_consult`、
      存 `self._failure_lessons_consult`、`_load_failure_lessons`（异常降级留痕）、`astream` 在 `_load_pinned_notes` 后调用。
- [x] 2.5 `configuration/manager.py`：ConfigSpec `loop.failure_lessons`（`--loop.failure-lessons` /
      `CORE_LOOP_FAILURE_LESSONS` / 缺省 False / ADVANCED）、访问器 `failure_lessons()`、
      `_loop_errors` 加 bool 校验。
- [x] 2.6 `runtime.py`：闭包 `_failure_lessons(session_id)`；`DefaultLoop(failure_lessons_consult=… if config.failure_lessons() else None)`；
      `exclude_fact_tags` **条件化**（`{"steps","failure"}` if on else `{"steps"}`）。
- [x] 2.7 `tests/test_failure_lessons.py`（新，+16）。

## 3. 反证（逐条记录红数）
- [x] 3.1 (A) 摘 `planner.py` 的教训块 ⇒ 预期 2 红。
- [x] 3.2 (B) 读面改回 `read()`（走强化路径）⇒ 零效应锚红。
- [x] 3.3 (C) 摘 `runtime.py` 的 `"failure"` 条件项 ⇒ 事实面条件化锚红。
- [x] 3.4 复原后四文件 md5 与改前**逐字节相同**。

## 4. 门禁与归档
- [x] 4.1 四门禁（直连二进制）：ruff check / ruff format --check / pyright 0-0-0 / pytest -q。
- [x] 4.2 `openspec validate --all` 全绿。
- [x] 4.3 手工归档 `python3 /tmp/openspec_archive.py 2026-10-11-0217-failure-lessons-block`
      （断言 0 Requirement-header / 0 Scenario-title 丢失）。
- [x] 4.4 ADR-0207 落 `doc/01-architecture/adr.md`（含变更追踪表行）。
- [x] 4.5 台账 E154（`coding-plan/known-risk.md` §1 ＋ §3 局限行）。
- [x] 4.6 `doc/04-testing/test-cases.md` §130。
- [x] 4.7 单次提交（`feat(memory): …（change 0217 / ADR-0207 / 台账 E154）`）。
