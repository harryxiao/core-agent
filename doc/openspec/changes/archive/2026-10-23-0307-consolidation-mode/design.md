# Design — 0307 巩固的可关闭性与水位语义

## D1 `off` 的语义与位置

```python
class MemoryStore:
    def __init__(..., consolidation_enabled: bool = True): ...
    def compact(...):
        if not self._consolidation_enabled:
            return None
        if not self._compact_lock.acquire(blocking=False): ...
```

- 早返回放在**取锁之前**：off 是静态配置，不需要 single-flight 协调，也不该产生
  「compaction already running」告警。
- `None` 与既有「未注入摘要器/并发跳过」同形；现有调用方（`_maintain` / `_compact_bounded` /
  `memory maintain` / Web API）**都不消费返回值语义**，只依赖副作用 ⇒ 无调用方改动。
- **被拒**：在组合根把四个钩子全部置 `None`（`commentary`：摘要器与三抽取器独立接线，四路
  统一关闭需要四改，任何一条路径直接构造 `MemoryStore` —— 测试、嵌入式宿主、基准 —— 都能
  绕过；且「关闭」会退化成「没接线」，无法区分配置关闭与装配遗漏）；在 `_episodic_groups`
  过滤（评分、摘要、抽取共用材料源，但迁移与摘要写入已发生一半，不是全停）。

## D2 配置口径

- key：`memory.consolidation_mode`。SDD 写的是嵌套 `memory.consolidation.mode`；本仓配置段是
  **扁平 + 点号 key**（`memory.l2_soft_max_entries` 同形），故以 `memory.consolidation_mode`
  落地，语义一一对应。
- 取值：`active`（缺省）/ `off`；大小写与首尾空白归一。`memory` 段**非结构化**（与
  `relation_extract` 等一致，非法取值不阻断启动）⇒ 集合外取值归一为 **`active`** ——
  方向恒为「变更前行为」，拼写错误不静默停用固化。
- 三面：CLI `--memory-consolidation-mode`、env `CORE_MEMORY_CONSOLIDATION_MODE`、
  yaml `memory.consolidation_mode`（ConfigSpec 单一真源）。
- 组合根：`consolidation_enabled=config.consolidation_mode() != "off"`；缺省 `ConfigManager`
  （`self._config is None`）同样返回 `active`。

## D3 队列 / 水位：用既有机制兑现，不造第二权威

| SDD 要求 | 本仓承载 |
|---|---|
| `consolidation.jsonl` 持久任务队列（至少一次、幂等） | **L2 未迁移的 episodic 条目**：`memory.jsonl` 单一权威、原子替换 + 跨进程合并（0301） |
| 读取 `fromSeq` 之后的情景记录 | `_episodic_groups(session_id)` 只取**仍在 L2** 的 `kind="episodic"` 条目（`_PRESERVE_TAGS` 排除） |
| 记录 watermark，任务完成 | 单会话成功提交后 `_commit_summary` 把该批条目**迁 L4** ⇒ 下轮不再是材料 |
| 超时保留水位，下次继续 | `deadline` 越界不提交摘要、不迁移（0296）⇒ 条目仍在 L2 |
| 失败只告警并保留任务 | 低于价值门 / 空摘要 / 摘要器异常 ⇒ 条目不迁移，下个节拍重试 |
| 重复执行不得产生重复知识 | 产物 id 稳定（`compaction.summary.<key>` / `keyfact.<slug>` / `episodic.<key>` / `relation.<三>.`）＋ 同载荷重放零副作用（0306） |

**被拒**：新增 `consolidation.jsonl`（第二权威；SDD 自身规定传输/队列不得作为权威存储，
且本仓无独立队列消费者）；给条目加单调 `seq`（`memory.jsonl` 无序号域，旧行迁移面大，且
`id + ts` 已足以表达「哪批被处理」）；把水位写进记忆条目（污染检索面、参与衰减与遗忘）。

## D4 局限

- `off` 只停**知识固化**；`forget()`（自然衰减归档）与会话滑窗中期摘要（`summarize_slice`，
  服务上下文分层而非长期知识）不受影响，文档明示。
- 低价值会话在每个维护节拍（缺省 15 分钟）会被**重新评分**：没有失败退避 / 负缓存。
  触发再评估的条件：实测到评分模型成本显著，或出现长期驻留的低价值会话。
- 不记录 `extractorVersion`：prompt/规则变化后无法解释历史产物；四路 prompt 各自演进，建版本
  域需独立设计。
- 队列可见性就是 L2 层本身；本仓不提供「待巩固任务列表」视图（`memory maintain` 一次性处理）。

## 测试与反证计划

`tests/test_memory_consolidation_mode.py`：

1. `off` 时 `compact()` 返回 `None`：评分器 / 摘要器 / 三个抽取器**零调用**，无新条目、
   无迁移、该 trace 无效应，原条目仍在 L2；
2. 缺省 `active`：同一素材正常产出摘要并迁移（与变更前一致）；
3. `off` 不影响 `forget()`（低分条目仍归档）；
4. 配置三面：spec 声明、缺省 `active`、yaml `off`、env 覆盖、非法值归一 `active`；
5. 组合根：缺省注入 `True`，`off` 注入 `False`（私有属性断言）；
6. 水位/队列：摘要器抛错 ⇒ 条目不迁移（水位不前进），换好摘要器后同一 store 重试成功；
7. 跨重启：`FileBackend(tmp_path)` 写入未处理条目，新建 store（模拟重启）仍能压实 ⇒
   队列在 L2、非进程内存。

反证（`cp` + `md5sum`）：删 `compact` 早返回 ⇒ 1 红；`off` 也跳过 `forget` ⇒ 3 红；
`consolidation_mode` 非法值归一为 `off` ⇒ 4 红；组合根恒 `True` ⇒ 5 红；失败时误迁移 ⇒ 6 红。
