# Change 0251 — L2 活跃层软上限的组合根接线

## 为什么

只读盘点（记忆框架对比审查 P0）确认一处**生产不可达**的规格承诺：

1. **软上限能力存在但从未启用**：change `0230` 按规格「L2 活跃层软上限」实现了
   `MemoryStore(l2_soft_max_entries=...)`（`store.py:273`）与 `_enforce_l2_cap()`（`store.py:709`），
   但组合根 `build_runtime`（`runtime.py:607-636`）**没有传这个形参**，且 `memory` 段
   **没有对应 ConfigSpec** ⇒ 生产环境下该能力**永远关闭**，L2 只有写入、没有收口。
2. **无界增长的代价是真实的**：`FileBackend._load()` 把整份 JSONL 读入内存、`search()` 线性扫描
   （`backend.py`），L2 长期只增不减 ⇒ 常驻内存与每轮检索成本随运行时长单调上升。用户无法
   通过任何配置面启用已实现的软上限。
3. **文档口径偏差**：`doc/02-modules/memory.md` 的 L1 描述为「指向 L2/L3 的最小索引（what→where）」，
   而实现是后端维护的 `id → layer` 映射（`backend.list_index()`）—— 对照审查把它当作「索引未被
   使用」的证据，属文档误导，需订正为事实口径。

## 改什么

- **配置键 `memory.l2_soft_max_entries`**（新 ConfigSpec，`exposure=ADVANCED`，`default=None`）：
  CLI flag `--memory-l2-soft-max-entries` / env `CORE_MEMORY_L2_SOFT_MAX_ENTRIES` / `memory:` 段
  三面一一对应；`ConfigManager.l2_soft_max_entries() -> int | None` 读取并归一一处。
- **组合根注入**：`build_runtime` 以 `l2_soft_max_entries=config.l2_soft_max_entries()` 构造
  `MemoryStore` ⇒ 配置即生效；未配置 ⇒ `None`，行为与引入本变更前**逐字一致**。
- **文档订正**：`memory.md` 增补软上限配置/装配说明与「未启用即无界」的风险提示；L1 行改为
  实现事实（后端 `id → layer` 索引，非检索索引）。
- **known-risk 订正**：ADR-0237 的局限 ③ 由「缺省关闭」订正为「**当时未接线、生产不可达**」，
  并登记由本变更关闭。

## 影响面

- 规格：`configuration` 新增 Requirement「记忆容量配置」；`memory` MODIFIED「L2 活跃层软上限」
  （补组合根装配条款 + 1 个 Scenario，既有 Scenario 逐字保留）。
- 代码：`src/core/configuration/manager.py`（ConfigSpec + 访问器）、`src/core/runtime.py`（接线）。
- 测试：新增 `tests/test_memory_soft_cap_config.py`（三面/归一/接线/端到端收口）。
- 缺省行为：不配置 ⇒ `None` ⇒ 不触发任何上限检查（与变更前逐字一致）。

## 不做

- 不改变 `FileBackend` 的加载/检索实现（流式加载、倒排索引属独立课题）。
- 不启用缺省值（`None` 保持现状；是否设默认上限是运维决策，不由本变更代替）。
- 不新增 `config set` 白名单（`memory` 段不在其列，维持既有 CLI 边界）。
- 不涉及 L4 归档容量（L4 只增不减是「不物理删除」规格的必然结果，另行登记）。
