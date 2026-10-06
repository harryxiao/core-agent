# 任务：Web 流式增量以专类型帧推送（change 0132 / E65）

## 1. 规格先行

- [x] `specs/ui/spec.md` delta：MODIFIED「Web 界面访问」（增量帧专类型 + 前端文本追加）+ 1 Scenario
- [x] `openspec validate --all` 通过（31/0 → 归档后 30/0）

## 2. ADR

- [x] ADR-0125 + `## 变更追踪` 行

## 3. 测试先行（红）

- [x] `test_ui.py`：`reply_delta` 映射为 `loop.delta`（类型 + 载荷 `{text}`）
- [x] `test_repl.py`：`_event_delta` / `_format_event` 判 `loop.delta`
- [x] `test_serve.py`：SSE 体含 `loop.delta` 与 `loop.result`

## 4. 实现

- [x] `api.py::_EVENT_MAP`：`reply_delta` ⇒ `loop.delta`
- [x] `repl.py::_event_delta` / `_format_event` 改判类型
- [x] `entry.py::_stream` 增量跳过判据改判 `loop.delta`
- [x] `frontend/src/views/Chat.svelte` 增量尾部追加

## 5. 门禁

- [x] `.venv/bin/ruff check src tests` / `.venv/bin/ruff format --check src tests`
- [x] `/home/harry/.praisonai/venv/bin/pyright` = 0/0/0
- [x] `.venv/bin/pytest -q`（1620 → 1622）

## 6. 文档与归档

- [x] `doc/03-interfaces/ui-interface.md` §1.1 表 + `doc/04-testing/test-cases.md`（含前端手工项）
- [x] 手工归档 `archive/2026-10-06-0132-web-reply-delta-streaming/`
- [x] `coding-plan/phase-34.md` §1 E65 + §9 行；`coding-plan/README.md` 索引
- [x] 记忆文件更新
- [x] 单次提交 `fix(ui): Web 增量帧以专类型推送（change 0132）`
