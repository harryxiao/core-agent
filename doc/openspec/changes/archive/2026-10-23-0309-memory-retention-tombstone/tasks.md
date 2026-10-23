# Tasks — 情景保留期与删除墓碑（0309）

## 1. 规格与红灯

- [x] 1.1 写 `specs/memory/spec.md`、`specs/configuration/spec.md` delta（本目录）
- [x] 1.2 新增 `tests/test_memory_retention.py`：保留期判据、`forget` 合并返回、
      配置三面与归一、运行时接线、墓碑不进压实材料
- [x] 1.3 新增 `tests/test_memory_tombstone.py`：`retract` 清正文/状态/迁 L4、审计、
      可逆、持久、未知 id、read/recall/failure_lessons 排除、export 可见
- [x] 1.4 改写 `tests/test_entry.py` 删除用例（物理删除 → 墓碑）与会话审计断言
- [x] 1.5 跑新用例确认全红（`MemoryStatus` / `retract` / `episodic_retention_days` 缺失）

## 2. 实现

- [x] 2.1 `src/core/memory/protocol.py`：`MemoryStatus` 增 `retracted`
- [x] 2.2 `src/core/memory/store.py`：
      - 构造参 `episodic_retention_days: int | None = None`
      - `retract(entry_id, *, reason="tombstone") -> bool`（迁 L4 + 清正文 + 状态 + 效应 + 审计）
      - `forget()` 前置保留期墓碑阶段（复用 `retract`）
      - `_episodic_groups` / `_material_for_session` / `forget` / `_enforce_l2_cap` 活性过滤
- [x] 2.3 `ConfigManager`：ConfigSpec `memory.episodic_retention_days`（缺省 90，三面）+
      `episodic_retention_days()`（非法/负数归一 90，`0` 关闭）
- [x] 2.4 `runtime.py`：注入 `episodic_retention_days=config.episodic_retention_days()`
- [x] 2.5 `entry.py`：`memory delete` 改 `retract`、输出文案、帮助串
- [x] 2.6 新用例转绿；全量 `uv run pytest`

## 3. 门禁与反证

- [x] 3.1 `uv run ruff check`、`uv run ruff format --check`、`uv run pyright`（0 errors）
- [x] 3.2 反证（`cp` 到 `/tmp` + `md5sum` 复原），逐条至少一红：
      - 去掉保留期前置阶段 ⇒ 到期用例红；
      - `retract` 不清正文 ⇒ 墓碑正文用例红；
      - `retract` 不置 `retracted` ⇒ 检索排除用例红；
      - `_episodic_groups` 去掉活性过滤 ⇒ 压实材料用例红；
      - 配置非法值归一改为 0 ⇒ 归一组红
- [x] 3.3 `openspec validate 2026-10-23-0309-memory-retention-tombstone` 通过；
      `openspec validate --all`

## 4. 文档

- [x] 4.1 `doc/02-modules/memory.md`：§3.23 保留期与墓碑 + `forget` 流程更新
- [x] 4.2 `doc/03-interfaces/memory-interface.md`：构造参、`retract`、状态矩阵
- [x] 4.3 `doc/03-interfaces/configuration-interface.md`：§2.23 `memory.episodic_retention_days`
- [x] 4.4 `doc/01-architecture/adr.md`：ADR-0299（含被拒备选与局限）+ 追踪行
- [x] 4.5 `coding-plan/known-risk.md`：E245
- [x] 4.6 `doc/04-testing/test-cases.md`：§222
- [x] 4.7 `doc/03-interfaces/prompts.md` ⑭ 落点行号同步（若 `entry.py` 行号漂移）
- [x] 4.8 更新台账与 `MEMORY.md` 索引（归档提交后）

## 5. 收口（需用户显式确认）

- [x] 5.1 归档 change（归档后 `validate --all` 31/0）
- [x] 5.2 提交、推送；提交信息
      `feat(memory): 情景保留期与删除墓碑（change 0309 / ADR-0299 / 台账 E245）`
