# 变更提案 — `reuse_count` 落盘持久化（change 0187）

## 为什么

**ADR-0168 局限④**：`read()` 命中条目时 `entry.reuse_count += 1`（`src/core/memory/store.py:250`），
注释自陈「复用即强化（**进程内强化，不落盘避免写放大**）」—— 即该计数**只在进程内**有效。
但复用信号**不止**用于当场排序：

- **遗忘曲线**据它延缓：`_decay_score`（`store.py:105-115`）用
  `freshness ** (1 / (1 + log1p(reuse_count)))` 调制；`memory` 规格明文「复用越多衰减越缓
  （检索命中反哺遗忘曲线）」（`doc/openspec/specs/memory/spec.md:363-367`）。
- 而 `FileBackend.search`（`backend.py:45-62`）返回的是**存储对象本身**（非副本）⇒ 进程内那次自增
  改的正是后端内存对象，**却从不 `_persist()`** ⇒ **磁盘 JSONL 里始终是旧值**。

后果：**跨会话（或进程重启后）复用强化全部丢失** —— 一条真正被反复召回的记忆，重启后 `reuse_count`
回到 0，衰减不加延缓，**最该留的东西反而先被归档**。这与「记忆即进化轨迹」的中心隐喻直接相悖。

## 改什么

| 面 | 变更 |
|---|---|
| `memory/store.py` | `read()` 命中项自增后**写回**（`_backend.put(entry)`）+ 每条记**可撤销效应**（trace `reuse.<id>`，undo 还原原值） |
| 规格 | `memory` **MODIFIED**「温度分层检索」（复用强化条款：进程内 → 持久化）+ 1 Scenario |
| 测试 | 命中后新 store 同 backend ⇒ `reuse_count` 保持 / 未命中不写（回归锚）/ 写回可回滚 / 只写选中条目（有界） |

## 影响

- **行为变更（有意）**：`read()` 命中条目由「仅进程内自增」变为「自增 + 落盘」。跨会话复用强化
  得以保持 ⇒ 遗忘曲线连续。
- **有界**：只写本次 `_truncate` **选中**的条目（其数目由预算决定）⇒ 写放大有界；非选中候选
  **不**被写（原语义，逐字不变）。
- **可逆（P2）**：每条写回记 `EffectTracker` 效应，`rollback(trace)` 把 `reuse_count` 还原为**原值**。
- **不受影响**：`summary_for` / `mid_summary_for`（**不同的**只读取数面，不经 `read()`）**逐字不变**；
  排序 / 预算 / 排除面的语义**逐字不变**（只是多了一次落盘）；`stats` / `audit` 口径不变。
- 无新增第三方依赖；无新配置键；无 import 方向变化。
