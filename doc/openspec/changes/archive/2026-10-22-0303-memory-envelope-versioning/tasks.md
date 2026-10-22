# Tasks — 0303 记忆条目治理信封与关键事实版本链

## 1. 规格与测试先行

- [x] 1.1 `specs/memory/spec.md` ADDED ×1（记忆条目的治理信封）
- [x] 1.2 `specs/memory/spec.md` MODIFIED ×2（结构化实体抽取（关键事实）/ 关键事实的跨压实合并）
- [x] 1.3 新增 `tests/test_memory_version_chain.py`（10：旧行缺键默认 / 首版信封 / 变更生成 v2 /
      检索只见最新（紧预算）/ audit 见全链 / 同值幂等不升版 / 回滚恢复旧版 / content_hash 一致 /
      关系不升版 / 抹除值就地重写）
- [x] 1.4 改写 `tests/test_memory_key_facts.py` 两条「覆盖式更新」用例为版本链口径
- [x] 1.5 红/绿分布记录（实现前新用例红；`redacted` / 紧预算用例补强后各自有反证）

## 2. 实现

- [x] 2.1 `MemoryEntry` 增 `content_hash / status / version / parent_id / superseded_by`（全默认）
- [x] 2.2 `MemoryStore.write()`：`content_hash` 为空时自动计算（`sha256(content.strip())`）
- [x] 2.3 `MemoryStore.read()`：排名与预算前剔除 `status != "active"`；`failure_lessons()` 同步
- [x] 2.4 `_write_key_fact()`：同值幂等就地刷新；取值变化 ⇒ 版本条目 + 旧版 superseded；
      `_supersede()` 记可逆效应（同 trace）；`<redacted>` 旧值就地重写
- [x] 2.5 `_stale_key_facts()` 跳过非 active
- [x] 2.6 `protocol.py` 字段与 `read()` docstring 同步

## 3. 文档账

- [x] 3.1 `doc/02-modules/memory.md`：条目模型 / 版本链小节
- [x] 3.2 `doc/03-interfaces/memory-interface.md`：`MemoryEntry` 字段与 `read()` 过滤口径
- [x] 3.3 ADR-0293 + known-risk E239 + test-cases §216

## 4. 门禁与反证

- [x] 4.1 `uv run ruff check src tests` / `ruff format --check src tests` / `uv run pyright`
- [x] 4.2 `uv run pytest -q` 全量全绿（3425 passed）
- [x] 4.3 反证 4/4（`cp` + `md5sum`）：去 status 过滤 / 去 supersede / 去同值判断 / 过滤放到预算后
- [x] 4.4 `cd doc/openspec && openspec validate --all`（32/0）
- [ ] 4.5 归档 / 提交（用户确认后）
