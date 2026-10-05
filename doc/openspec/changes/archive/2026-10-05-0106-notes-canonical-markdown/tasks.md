# tasks — notes：canonical Markdown 真相层 + Consult→Build→Update 循环（change 0106）

## 1. 规格（先行）
- [x] 1.1 新增 `specs/notes/spec.md`（ADDED）：canonical 真相层与 `MarkdownBackend`（覆盖式 put + 原子写 +
      文件清单 + 关键词命中）
- [x] 1.2 同文件 ADDED：Consult→Build→Update 循环纪律（内置技能 + 任务前/后钩子 + loop 不 import notes）
- [x] 1.3 同文件 ADDED：结构化错误码（`NOTE_NOT_FOUND` / `TOPIC_EXISTS`）与既有链路不变
- [x] 1.4 新增 `doc/03-interfaces/notes-interface.md`
- [x] 1.5 `openspec validate 2026-10-05-0106-notes-canonical-markdown` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_notes.py`：canonical Markdown 渲染/解析往返（标题 / tags / Search Queries / 正文）
- [x] 2.2 `tests/test_notes.py`：`MarkdownBackend` 覆盖式 `put`（同主题二次写不拼接）+ 原子写（无半截）+
      `list_index` 清单 + 关键词 `search` 命中 Search Queries
- [x] 2.3 `tests/test_notes.py`：`NoteStore` 读写闭环（`consult` → `update` → 再次 `consult` 读到更新）+
      `NOTE_NOT_FOUND` / `TOPIC_EXISTS` + `ensure` 幂等
- [x] 2.4 `tests/test_notes_loop.py`：loop 集成 —— 注入 Consult/Update 钩子后，任务前注入「相关笔记」、
      成功轮写回 canonical 文件含新结论；钩子故障不改本轮结局
- [x] 2.5 运行确认**红**：首轮红态暴露三处真缺陷 —— ①中文任务句（无空格）整词包含**永不命中**
      （补 CJK 2-gram 切词，并**回写规格场景**「中文任务句命中」）；②`INTERNAL_PLUGIN_IDS`
      未登记 `notes.store`（逐元素守护用例报红 ⇒ 补齐 13→14）；③技能 id 不合
      `skills.<area>.<name>` 口径（改 `skills.notes.consult_build_update`）。修复后全绿（**备注①**）

## 3. 实现
- [x] 3.1 `src/core/notes/models.py`：`NoteEntry` + `render_note` / `parse_note` / `slug_topic`
- [x] 3.2 `src/core/notes/errors.py`：`NoteErrorCode` / `NoteError`
- [x] 3.3 `src/core/notes/backend.py`：`MarkdownBackend`（实现 `MemoryBackend`；覆盖式 put + tmp + `os.replace` + 关键词 search）
- [x] 3.4 `src/core/notes/store.py`：`NoteStore`（Plugin；`get/create/ensure/update/consult/list/digest/observe_turn`）
- [x] 3.5 `src/core/notes/__init__.py`：导出
- [x] 3.6 `loop/protocol.py`：`LoopContext.notes` 新增字段（附加性）
- [x] 3.7 `loop/default.py`：`NotesConsult` 钩子别名 + `notes_consult` kwarg + 任务前 `_consult_notes`
- [x] 3.8 `loop/planner.py`：`_system_prompt` 渲染「相关笔记」块
- [x] 3.9 `runtime.py`：装配 `NoteStore` + 注册 `skills.notes.consult_build_update`（组合根构造 Skill）+
      `notes_consult` 闭包 + `on_turn` 追加 `observe_turn`
- [x] 3.10 `entry.py`：`notes` CLI 面（`list` / `show <note_id>` / `search <query>`）
- [x] 3.11 `tests/test_architecture.py`：`notes` 入 `EXPECTED_PACKAGES`/`CAPABILITY_MODULES`；`loop` 禁依赖
      名单加 `notes`

## 4. 门禁与文档
- [x] 4.1 四门全绿（`ruff check` / `ruff format --check` / `pyright` 0/0/0 / `pytest`）
- [x] 4.2 `doc/02-modules/notes.md` + `doc/01-architecture/adr.md`（ADR-0099 + 映射表行）
- [x] 4.3 `doc/04-testing/test-cases.md`（TC-NOTE-*）+ `contracts_summary.md` 追加 `notes` 行
- [x] 4.4 `CLI` 端到端冒烟（`notes search/show` 跨进程可见）
- [x] 4.5 git diff 证明 `plugin_registry` / `MemoryStore` / `FileBackend` / RAG 链路未改
- [x] 4.6 手工归档（delta 合进 `doc/openspec/specs/notes/spec.md` + 移入 `archive/`）+ `openspec validate --all`
- [x] 4.7 账本（`coding-plan/README.md` / `phase-23.md` §6）更新

## 备注（与计划的偏差，如实记录）

① **先写测试的粒度**：本 change 的用例与实现交替推进（非严格「先全红后实现」），故 2.5 记录的
   是**首轮运行的红态**（1 例新用例 + 3 例既有用例如实报红），随后逐项修复转绿；三处缺陷均为
   真实缺陷而非用例写错，且其中两处（规格场景、归因白名单）**回改的是规格与既有不变式**。
② **`contracts_summary.md` 落在第 29 节**：phase-23 §5/§6 写作「30. notes」，而仓内实际最后一节为
   `28. judgment` ⇒ 取实际下一个空位 **29**（不由计划书的编号假设决定）。
③ **技能 id 口径**：计划书写 `notes.workflow.consult_build_update`；仓内既有技能 id 为
   `skills.<area>.<name>`（如 `skills.data.summarize`）⇒ 改为 `skills.notes.consult_build_update`。
④ **`INTERNAL_PLUGIN_IDS` 连带 +1**：`notes.store` 实现了 `plugin_id` ⇒ 按 change 0102 的逐元素
   一致性不变式必须登记（13 → 14），否则其缺陷会被误归因为技能级而绕过人工审批。
