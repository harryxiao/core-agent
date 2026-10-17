# Tasks 0254 — 记忆写回脱敏与压实硬伤

## 1. 规格

- [x] 1.1 `notes` delta：ADDED「逐轮写回正文脱敏」+ 2 Scenario。
- [x] 1.2 `context` delta：ADDED「压实产物的脱敏、有界与陈旧清理」+ 3 Scenario。
- [x] 1.3 `skills` delta：ADDED「路由未命中记录的脱敏与有界」+ ADDED「SOP 提炼正文脱敏」。
- [x] 1.4 `memory` delta：ADDED「关键事实空值拒收」+ 2 Scenario。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_memory_write_hygiene.py`：
      - notes 正文含密钥形态 ⇒ `<redacted>`，工具名/路径仍在
      - 压实产物含密钥 ⇒ 落库脱敏；超长 ⇒ 单条 ≤400
      - 同会话第二次压实条目更少 ⇒ 旧序号条目被删除
      - 路由未命中原文含密钥 ⇒ 落库脱敏且有界
      - SOP 文本含密钥 ⇒ 入库 instructions 脱敏
      - 关键事实空 value ⇒ 丢弃（不落库、不覆盖）

## 3. 实现

- [x] 3.1 `notes/store.py`：写回正文逐行 `redact_secrets`。
- [x] 3.2 `context/compactor.py`：`_sanitize` + `_MAX_PRODUCT_CHARS` + `_prune_stale`；
      `memory/store.py` 新增 `discard`。
- [x] 3.3 `skills/router.py`：miss content 脱敏 + `_MAX_MISS_CHARS`。
- [x] 3.4 `skills/sop.py`：提炼文本入口脱敏。
- [x] 3.5 `memory/extract.py`：`scrub_key_fact` 空 entity/value 丢弃。

## 4. 验证

- [x] 4.1 探针：逐点摘除 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate 2026-10-17-0254-memory-write-hygiene --strict` → 归档。

## 5. 文档与收口

- [x] 5.1 ADR-0245；`coding-plan/known-risk.md` E191 + §3 ADR-0245 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §167；相关模块/接口文档补写回约束。
- [x] 5.3 单次提交 `fix(memory): ... change 0254 / ADR-0245 / 台账 E191`；更新记忆。
