# 设计 — `reuse_count` 落盘持久化（change 0187 / ADR-0178 / 台账 E124）

## D1 为什么必须改：进程内自增「看起来持久」，其实不是

`FileBackend.search`（`backend.py:45-62`）返回 `self._entries.values()` 的**同一批对象引用**（非
`copy`）⇒ 旧代码 `entry.reuse_count += 1` **就地改了后端的内存对象**，只是**没有** `_persist()`。
⇒ 同一进程内 `audit()`（走 `_backend.search("")`）**能**看到新值（所以既有测试 `test_read_reinforces_reuse_count`
绿），但**磁盘 JSONL 仍是旧值** ⇒ 进程结束即丢。这是「测试绿、语义错」的典型：判据选在了
**进程内可见性**上，而契约要的是**跨会话持久性**。

## D2 落盘只加一处 `put`，不碰 `_hot`

新增私有 `_reinforce(selected)` 取代 `read()` 末尾的裸循环：

- 对**选中**条目：`previous = entry.reuse_count; entry.reuse_count = previous + 1; self._backend.put(entry)`；
- **不**把条目插入 `self._hot` —— `_hot` 是**写入侧**的热字典（`_persist` 等五处写入），若在读路径也
  填充，`_hot` 会随**每个被读到的条目**增长（无界）⇒ 把「读」变成「隐式缓存」，超出本 change 的意图。

**对象同一性说明**：因后端 `search` 返回同引用，`put(entry)` 只是「同一对象 + 触发 `_persist()`」，
无序列化往返；故 `_hot` 中若有同一 id 的对象，也是**同一对象**，不存在两处状态分叉。

## D3 可逆：每条记效应，undo **还原原值**（非自减）

`EffectTracker.record(Effect(op="memory.reuse", target=entry.id, undo=…, trace_id=f"reuse.{entry.id}"))`。
undo 取**还原为捕获的 `previous`**（而非 `-= 1`）：若同一 trace 已被回滚、或并发下有多次强化，
「还原原值」是幂等的、不会把计数打成负数。undo 查表的顺序照 `_undo_migrate` 的形状：
`_hot.get(id)` → `_backend.get(layer, id)` → 都没有则**静默返回**（条目已被删除 ⇒ 无事可做）。
闭包用**默认参数**绑定 `entry_id` / `layer` / `previous`（避免 ruff `B023` 循环变量晚绑定陷阱）。

## D4 有界批量：只写 `_truncate` 选中的条目

`read()` 末尾的循环本就只遍历 `selected`（非选中候选**从不**自增）⇒ 本 change **不扩大**写入面，
只是把「已自增」这件事持久化。写放大上界 = 每次读取的选中条目数（由 `budget` 决定）。

## D5 规格落点 `memory`（**是** `memory`，与 0185/0186 不同）

0185/0186 改的是**装配面的注入步骤**（故落 `context`）；本 change 改的是 **`MemoryStore.read` 自身**
的语义（「复用强化」由进程内变持久）⇒ 规格该写在 `memory`「温度分层检索」—— 这正是**行为发生变化**
的能力。`context` 侧**零改动**。

## 不做（显式）

- **不加节流/批合并配置键**：写放大已被 D4 限定在选中集内，加配置是**投机性可配置性**（违反「最小」）；
  若将来实测到热点，再以独立 change 引入（并附度量证据）。
- **不改 `_hot` 语义**（见 D2）。
- **不改 `summary_for` / `mid_summary_for`**：它们是**不同的**只读取数面（不经 `read()`），
  其「零写入 / 零效应」契约**逐字不动**（既有测试继续守护）。

## 不变量

| 编号 | 不变量 |
|---|---|
| I1 | 排序 / 预算 / 排除面 / 会话过滤语义**逐字不变**（只在末尾多一次落盘） |
| I2 | 非选中候选**不**被写、**不**被强化（原语义） |
| I3 | `summary_for` / `mid_summary_for` 零写入零效应**逐字不变** |
| I4 | 每条写回记**可撤销**效应；`rollback("reuse.<id>")` 后 `reuse_count` 回到**原值** |
| I5 | 无新配置键、无新第三方依赖、无 import 方向变化 |
| I6 | `_hot` 不被读路径填充（不引入隐式缓存） |

## 测试设计

| 用例 | 断言 |
|---|---|
| 跨会话保持 | 同一 `backend` 上新建 `MemoryStore`（模拟重启）⇒ `read()` 后 `reuse_count` 仍为强化值 |
| 未命中不写（回归锚） | 查询无命中 ⇒ 无效应、无 `put`（用 spy backend 计数） |
| 可回滚 | `rollback("reuse.<id>")` ⇒ backend 中 `reuse_count` 回到原值 |
| 有界（只写选中） | 预算只容一条、两条候选 ⇒ 仅一条被写、另一条 `reuse_count` 不变 |
| 既有强化语义（回归锚） | `test_read_reinforces_reuse_count` 与 `test_read_does_not_write`（若在）继续绿 |
