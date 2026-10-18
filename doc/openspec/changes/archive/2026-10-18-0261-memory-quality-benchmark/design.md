# Design 0261 — 记忆检索质量离线基准

## D1 固定合成语料

- 26 条条目，`ts=0`（新鲜度衰减恒 1.0，排除时间噪声）、`source="bench"`（陈旧项
  `"bench.stale"`）、`session_id` 覆盖 `s1` / `s2` / `s3` / `s9` 与全局空串。
- 层次覆盖：L2 事实（当前 / 陈旧 / 诱饵）、L3 技能、L4 归档。
- 12 条查询，每条 1 个 gold；5 条带配对的陈旧冲突（用于 stale_hits）。

## D2 指标与阈值

- **recall@5**：每条查询命中的 gold 数 / gold 总数，取均值。目标 ≥ 0.9（留 1 条查询的余量）。
- **MRR@5**：首个 gold 命中排名的倒数均值（未命中计 0）。目标 ≥ 0.7。
- **stale_hits**：对每条带陈旧冲突的查询，若任一 `bench.stale` 条目的排名**高于**对应当前
  gold，则计 1。目标 = 0。该口径比「stale 是否进 top5」更贴近危害：陈旧事实只要没压过当前
  事实，出现在相关结果里是无害的。
- 不设 precision@5：单 gold 查询下 precision@5 上限仅 0.2，不能作为主阈值（plan 已裁决）。

## D3 隔离与确定性

- 每次查询 **新建** `MemoryStore()` 并重新 `write()` 全部语料：`read()` 的 `_reinforce` 会
  改写 `reuse_count`，复用同一 store 会让查询顺序影响后续排名。
- `FileBackend()` 无 path ⇒ 纯内存，不读写 `$CORE_STATE_DIR`。
- 重放两次（各自新 store）断言 top-5 id 序列一致；无随机源、无时钟依赖（`ts=0`）。

## D4 陈旧排除机制

- 除排序断言外，另加 `read(query, exclude_source_prefixes=("bench.stale",))`：断言返回结果
  无 `bench.stale` 来源，验证排除发生在排名与预算之前（change 0131 的既有机制）。

## 反证

1. 把 `c-pytest` 内容改成与查询无重叠（模拟「当前事实丢失」）⇒ recall / stale_hits 用例红。
2. 摘除 `read()` 的 `exclude_source_prefixes` 过滤（临时）⇒ 排除用例红。
3. 让 `st-pytest` 完整复制当前事实词元并把 `c-pytest` 降为 L4 ⇒ stale_hits > 0 红。

## 已知局限

- 合成语料只覆盖词法可分的英文 token；不度量中文长句、语义改写、embedder 质量。
- 阈值是回归门而非质量上限；语料固定，过拟合风险存在（修改语料须显式重定基线）。
- 单 gold 查询无法度量「多相关条目」的排序质量（precision 不作主阈值）。
