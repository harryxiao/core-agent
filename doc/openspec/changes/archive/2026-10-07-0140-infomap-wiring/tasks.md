# Tasks · 0140 信息地图装配接线（skip_specs）

## 1. 规格（先行）

- [x] 1.1 **无 delta**（`context/spec.md`「信息地图」+ 三 Scenario 早已是硬 SHALL，实现侧纯背离
      ⇒ conformance）：写 `.openspec.yaml`（`schema: spec-driven` + `skip_specs: true`）
- [x] 1.2 `openspec validate 0140-infomap-wiring` 通过

## 2. 测试（先行 · 红）

- [x] 2.1 `tests/test_context.py`：`register`（仅原文）⇒ `lookup` 走**线性扫描**逐段命中
- [x] 2.2 `tests/test_context.py`：线性扫描**受控** —— 段数上界 `_MAX_SCAN_SEGMENTS`
- [x] 2.3 `tests/test_context.py`：`documents()` 枚举已登记文档（含仅原文者）
- [x] 2.4 `tests/test_context.py`：`build()` 注入目录层 `pointers`（含指针串 `doc#section`）
- [x] 2.5 `tests/test_context.py`：地图为空 ⇒ `pointers == []`（零回归）
- [x] 2.6 `tests/test_infomap_wiring.py`：`tools.context_read` 在主工具面可达
- [x] 2.7 `tests/test_infomap_wiring.py`：Core.md 项目信息建索引 ⇒ 目录层进装配包**并**渲染进 system prompt
- [x] 2.8 `tests/test_infomap_wiring.py`：工具取详情闭环（命中返片段 / 未命中返空串**不报错**）
- [x] 2.9 **验绿**：实现后全绿（红因 `register` / `pointers` / 工具不存在而红）

## 3. 实现

- [x] 3.1 `src/core/context/models.py`：`ContextPack.pointers`（目录层，缺省空）
- [x] 3.2 `src/core/context/info_map.py`：`register()`（仅原文）+ `documents()`；
      `_linear_scan` 段数上界 `_MAX_SCAN_SEGMENTS = 20`（「受控」落为常量）
- [x] 3.3 `src/core/context/assembler.py`：`build()` 读地图 ⇒ `_gather_pointers()`
      （每文档上界 `_MAX_POINTERS_PER_DOC = 8`）；`fetch_detail` 注释补消费面口径
- [x] 3.4 `src/core/loop/planner.py`：`_system_prompt` 渲染「文档目录」块
- [x] 3.5 `src/core/tools/builtin.py` + `__init__.py`：`context_read(*, fetch_detail)` 只读工具
      （取数器**注入**，工具层不依赖 context 层）
- [x] 3.6 `src/core/runtime.py`：建 `InfoMap` 并索引 Core.md 项目信息段（`core-profile`）注入装配器；
      `tools.register(context_read(...))`（**装配器注入时同样接线**）

## 4. 文档

- [x] 4.1 `doc/03-interfaces/context-interface.md`：§1 `ContextPack.pointers`、§2 `build` 读地图、
      §3 `InfoMap.register` / `documents` / 受控上界
- [x] 4.2 `doc/03-interfaces/tool-use-interface.md`：工具清单补 `tools.context_read`
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0133 + `## 变更追踪` 行
- [x] 4.4 `doc/04-testing/test-cases.md`：§56（TC-INFOMAP，change 0140 / ADR-0133，账本 E77）

## 5. 门禁（直连二进制，禁 `uv run`）

- [x] 5.1 `.venv/bin/ruff check src tests` —— 绿
- [x] 5.2 `.venv/bin/ruff format --check src tests` —— 绿
- [x] 5.3 `/home/harry/.praisonai/venv/bin/pyright` —— 0 / 0 / 0
- [x] 5.4 `.venv/bin/pytest -q` —— **1674 passed**（基线 1665 + 9）
- [x] 5.5 `openspec validate --all` —— **31 passed / 0 failed**（归档后回落 30 / 0）

## 6. 收口

- [x] 6.1 手工归档至 `archive/2026-10-07-0140-infomap-wiring/`
- [x] 6.2 台账回填：`coding-plan/phase-34.md`（E77 行 + §9 表）；`coding-plan/README.md` 3 处索引行
- [x] 6.3 记忆更新：`MEMORY.md` + `coding-plan-leftover-walkthrough.md`
- [x] 6.4 单次提交（`fix(context): 信息地图装配接线（change 0140）`）
