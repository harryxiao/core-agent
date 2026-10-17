# Design — memory：复用强化批量落盘 ＋ 空摘要守卫 ＋ 教训块预算

## 背景

review 的 M7/M9/M10 都是**成本与重复**问题：同一份数据被反复全量重写、同一批材料被反复抽取、
同一块注入没有自己的预算。三者互不耦合，但都落在 memory/组合根的「写回与渲染」边界上，故同
change 收口。

## D1 批量写回（`put_many`）

`FileBackend.put_many(entries)`：先一次性更新 `_entries` 与 `_index`（按 id 集合剔除旧索引项、
再追加新项），最后**只调一次** `_persist()`。`MemoryStore._reinforce`：

1. 取 `previous = [e.reuse_count ...]`，统一 +1；
2. `self._put_many(entries)` —— `getattr(self._backend, "put_many", None)` 可调用则批量，否则
   逐条 `put`（鸭子类型后端保持可用）；
3. 逐条记录 `memory.reuse` 可撤销效应（**语义不变**：每条仍可独立回滚到强化前的值）。

**取舍**：不给 `MemoryBackend` Protocol 加必选成员（会让既有鸭子类型后端在类型面不满足）；
`put_many` 是**可选能力**，契约写在接口文档 §5。批量落盘只减少重写次数，不改变「选中集才有
写回」的写放大上界。

## D2 `_hot` 有界

`_HOT_MAX = 512`。新增 `_hot_put(entry)`：先 `pop` 再插入（写入序即淘汰序），超界时淘汰最旧；
所有写入点（`_persist` / `migrate` / `_write_importance` / `_restore_entry`）改走该 helper。

**安全性**：`_hot` 只是**写入侧引用缓存**，后端 `_entries` 才是真源；`_all_entries()` 本就
union 冷区 + 热区，淘汰不影响读面或审计。撤销路径中 `_undo_reuse` / `_undo_migrate` 已回退
冷区；唯一缺口 `_restore_importance` 补上冷区回退（`search("")` 按 id 查找，仅撤销时 O(n)）。

选择**写入序淘汰**而非严格 LRU：读路径不写 `_hot`（既有设计），访问频率信息不在字典里；为
LRU 而在每次 `get` 上维护链表会把「零副作用读」变成有状态操作，收益不抵复杂度。

## D3 空摘要守卫

`_summarize_sessions` 中，当**注入了摘要器**且 `summary` 为 falsy：

- `warnings.warn`（只报会话键，不回显正文 —— 承密钥红线）；
- `continue` 跳过本会话的 `_commit_summary` / 提升交付 / 三类派生抽取。

未注入摘要器时**不**跳过（派生抽取与摘要提炼本来就是独立能力，既有行为逐字不变）。

**为什么不做「抽取已尝试」状态位**：状态位要新增条目字段并跨进程持久化，属于新数据模型；
「本轮跳过 + 下轮重试」已消除**同一轮内**的重复调用，且保留模型抖动后的自愈机会。留痕让运维
能看见「该会话本轮没产出」，不静默。

## D4 教训块预算

组合根把渲染抽为模块级纯函数 `_render_failure_lessons(entries)`（可单测，loop 不 import）：

- 条目数上界仍由 `failure_lessons(limit=5)` 决定；
- 每条先折叠空白为一行，再截到 `_FAILURE_LESSON_MAX_CHARS = 500`；
- 累计正文达到 `_FAILURE_LESSON_TOTAL_CHARS = 1500` 即停止（最后一条按剩余预算截断）。

**取舍**：截断而非分页/摘要化 —— 教训是**提示词**输入，保留最近条目的开头比多调用一次模型
更可预测；预算按**字符**而非 token 计（与 memory 既有预算口径一致）。

## 测试面

- 批量：计数后端断言一次检索只触发 1 次 `put_many`、0 次 `put`；无 `put_many` 的鸭子类型后端
  仍逐条 `put`。
- `_hot`：写入 522 条后 `len(_hot) ≤ 512` 且 `_all_entries()` 全量可见；被淘汰条目的
  `_restore_importance` 仍写回冷区。
- 空摘要：计数抽取器断言 0 调用、原条目层级不变、有 `RuntimeWarning`。
- 教训块：5 条超长条目 ⇒ 单条 ≤500、总正文 ≤1500。

## 局限

- `_hot` 淘汰后，写入路径的「同引用」假设对已淘汰条目不再成立（仍经后端写回，正确性不受影响，
  仅失去一次内存命中）。
- `put_many` 仍是**整体重写**（只减少次数，不改变 JSONL 全量序列化的复杂度）。
- 空摘要会话的抽取在下一轮仍会重试（模型持续返回空时仍会重复，但频率从「每轮 3 次」降为
  「每轮 1 次摘要调用」）。
- 教训块按字符截断可能截在句中；总额 1500 是静态预算，未按模型上下文动态调整。
