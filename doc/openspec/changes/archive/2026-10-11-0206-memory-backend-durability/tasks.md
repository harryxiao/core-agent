# Tasks 0206 — 记忆后端落盘耐久

## 1. 规格（spec-first）

- [x] `specs/memory/spec.md`：**ADDED**「记忆后端落盘耐久（backend durability）」+ 4 Scenario
- [ ] ADR-0196（`doc/01-architecture/adr.md`，含「为什么缺省生效」论证）+「变更追踪」表行
- [ ] 其余 18 条 `memory` Requirement **逐字保留**

## 2. 测试先行（红）

- [ ] `tests/test_memory_backend_durability.py`：
      - 半写（截断＋OSError 注入）⇒ 目标文件既有条目完好、可重载（旧实现红：目标被截断）
      - 坏行（非法 JSON ＋ 结构不符 JSON）间杂完好行 ⇒ 构造不炸、完好行俱在、warn 只报计数
      - 完好文件重载 → 再持久化 ⇒ 字节逐字节不变（零回归锚）
      - 真子进程 SIGKILL 后另进程重载 ⇒ 条目全在、无告警
- [ ] **反证**：复原 `_load` 不容错 ⇒ 坏行用例红；复原 `_persist` 非原子 ⇒ 半写用例红

## 3. 实现（绿）

- [ ] `src/core/memory/backend.py`：`_persist` tmp＋`os.replace`；`_load` 逐行容错＋告警
      （`import os` / `import warnings`）

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：见 §2 末（两处）
- [ ] `openspec validate 2026-10-11-0206-memory-backend-durability`
- [ ] 手工归档（ADDED 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失；
      `memory` 15→16 / 111→115）
- [ ] `doc/04-testing/test-cases.md` §119 + 基线 bump；台账 E143（`known-risk.md` §1）+
      §3 ADR-0196 行；`doc/02-modules/memory.md` 增一节
- [ ] 单次提交 `feat(memory): 记忆后端原子写 + 逐行容错（change 0206 / ADR-0196 / 台账 E143）`
