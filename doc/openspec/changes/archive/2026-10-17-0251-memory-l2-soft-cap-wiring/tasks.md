# Tasks 0251 — L2 活跃层软上限的组合根接线

## 1. 规格

- [ ] 1.1 `configuration` spec delta：ADDED「记忆容量配置」（三面 + 优先级链 + 取值归一 +
      组合根注入 + 3 Scenario）。
- [ ] 1.2 `memory` spec delta：MODIFIED「L2 活跃层软上限」，补组合根装配条款与
      「配置启用后写入即收口」Scenario，既有 Scenario 逐字保留。

## 2. 红测试（先写）

- [ ] 2.1 `tests/test_memory_soft_cap_config.py`：
      - ConfigSpec 三面元组与 `default=None`、`map_to="memory.l2_soft_max_entries"`
      - 缺省 ⇒ `None`
      - yaml 整数 ⇒ 该整数
      - env 字符串（`"7"`）覆盖 yaml
      - 非法取值（`0` / 负数 / 布尔 / 小数 / 非数值）⇒ `None`（能力关闭，不阻断启动）
      - `memory:` 段不触发「未知配置段」告警
      - `build_runtime` 缺省 `_l2_soft_max_entries is None`；配置后为同一整数
      - 端到端：配置上限后写入超限 ⇒ L2 条目数回到上限内（走可逆迁移）

## 3. 实现

- [ ] 3.1 `_CONFIG_SPECS` 增 `memory.l2_soft_max_entries`。
- [ ] 3.2 `ConfigManager.l2_soft_max_entries() -> int | None`（`extra["memory"]` + `_parse_int`；
      `< 1` 归一为 `None`）。
- [ ] 3.3 `build_runtime` 的 `MemoryStore(...)` 传 `l2_soft_max_entries=config.l2_soft_max_entries()`。

## 4. 验证

- [ ] 4.1 探针：摘掉组合根接线 ⇒ 接线/端到端用例红；摘掉访问器 ⇒ 三面用例红；复原 md5 一致。
- [ ] 4.2 四门禁：`.venv/bin/ruff check src tests`、`.venv/bin/ruff format --check src tests`、
      `/home/harry/.praisonai/venv/bin/pyright`、`.venv/bin/pytest -q`。
- [ ] 4.3 `openspec validate 2026-10-17-0251-memory-l2-soft-cap-wiring --strict` → 归档。

## 5. 文档与收口

- [ ] 5.1 ADR-0241；`coding-plan/known-risk.md` E187 + §3 ADR-0241 行 + 订正 ADR-0237 局限 ③。
- [ ] 5.2 `doc/04-testing/test-cases.md` §163；`doc/02-modules/memory.md`（软上限装配 + L1 订正）；
      `doc/03-interfaces/configuration-interface.md` §2.12。
- [ ] 5.3 单次提交 `feat(memory): ... change 0251 / ADR-0241 / 台账 E187`；更新记忆。
