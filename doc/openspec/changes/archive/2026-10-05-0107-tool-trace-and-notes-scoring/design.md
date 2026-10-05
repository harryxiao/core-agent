# design — 工具级 trace 接线 + notes 加权 + E31 裁决（change 0107）

## D1 E30：生产者放在哪、经什么产出

**放 loop**，理由：`astream` 是**唯一**同时持有「动作 + 执行结果 + 耗时」的位置；工具层（`ToolProvider`）
只知工具不知轮次归因，装配层不知成败。判据与既有 `action_completed` **完全同点**（非终止动作分支内），
保证「事件流」与「遥测流」一一对应、不产生第二套判据。

**经 `TraceLogger.log_tool_call` 产出**，而非直接 `self._trace(...)`：`log_tool_call` 本是
`tool_call` 事件的**唯一生产者 API**，E30 的病根正是「供给侧无人产」；绕过它会让「生产者 API 零调用」
的账目**继续挂着**（且载荷形状会在两处漂移）。loop 在 ctor 由注入的 `tracer` 构造 `TraceLogger`
（`tracer` 缺省为 `None` ⇒ logger 为 `None` ⇒ 不产出，与「未注入 tracer 行为不变」一致）。

**载荷逐字对齐既有消费侧**（`_to_traces`）：`tool` = 工具 id（消费侧作为 `plugin_id`）、`args` =
参数（进入 `Trace.action`）、`result` = `{"ok": bool, "output": 节选}`（消费侧读 `ok` 定成败）、
`latency_ms`。参数与输出**复用既有节选函数**（`_args_excerpt` / `_output_excerpt`，≤400 字符）⇒
事件面**有界**，与 `action_completed` 的载荷同源同界。

**不动的**：`_to_traces` 消费口径逐字不变；`LoopEvent` 外发路径、事件序不变（新增的只是 trace 流里
一条事件）；`kind` 词表不扩。

## D2 E32：加权口径

字段权重（模块常量，便于测试与后续调参）：`title ×3`、`tags ×2`、`search_queries ×2`、
`note_id ×1`、`content ×1`。命中判据仍是「词是否出现在该字段文本中」的**纯词法包含**（CJK 仍走
2-gram 切词，不变），打分 = `Σ(字段权重 × 该字段命中词数) / 词数`。

**打分不再 ≤ 1**：`search` 只用它做 `> 0` 过滤与降序排序，不外露分数（返回 `MemoryEntry` 列表）
⇒ 语义安全。**不采纳**把权重做成可配置项：无消费者、徒增一面配置（同 CLAUDE.md「不要没被要求的
可配置性」）。

**不采纳**「按字段命中率归一」：会让「长正文命中 1 词」与「标题命中 1 词」重新等权，正是本 change
要修的病。

## D3 E31：裁决而非接线

**裁决：不纳入 `PluginRegistry`。** 三条依据（一手核实）：

1. **零消费者**：`PluginRegistry` 全仓只在 `PluginInstaller` 内部默认构造（`installable.py:93`），
   组合根没有 `registry` 变量 ⇒ 注册进去无任何代码路径读取，`state()` 只会给出对内部模块**不成立**
   的 `loaded/active`（它们根本不走装卸）。
2. **形态即空转**：14 个模块里仅 8 个有 Plugin 六件套，其 `load/unload` 全 `return None`；`check()`
   8 个里 7 个 `return True`（真检查仅 `evolution.engine` / `composition.resolver`）⇒ 补全后仍是
   无信号、无行为的形态。ADR-0094 决策①已明确否决（其「限制」节写死了重开条件）。
3. **前置条件未满足且更远**：重开条件 = 「真的会产出新一代 `Plugin` 对象」（模型生成 / 人工提交补丁），
   届时 `promote(plugin: Plugin)` 才有语义；而 change 0102 刚把架构级结晶裁决为 `accepted`
   （**待人工实施**）= 系统自己承认短期内没有该生产者。

**口径落点（本 change 做的事）**：把 `plugin_id` 在内部模块上的语义写进**规格**（evolution
「经验采集」）：**归因对象身份**，不蕴含注册表成员身份；失败证据经 `module_id` 通道承载。同步
`plugin_ids.py` docstring（「欠账」→「裁决 + 重开条件」）与账本（`phase-19.md` §5 / `phase-21.md` §1.4）。

**不采纳**「登记式最小实现 + 诚实标注」：诚实标注在**有消费者、只是输入不足**的位置成立（如 0102
`accepted`、0103 落盘 JSONL 为真源）；此处**零消费者**，标注只把「documented gap」换成
「documented no-op」，并给后来者留下「这些算法类有生命周期语义」的错误暗示。

## D4 规格影响面

| 规格 | 动作 | 内容 |
|---|---|---|
| loop「异步流式执行」 | MODIFIED | 非终止动作另产 `tool_call` 遥测（载荷有界、不改事件流语义、未注入 tracer 不产）+3 场景 |
| evolution「经验采集」 | MODIFIED | 工具通道**须有生产方**；`plugin_id` = 归因对象身份（不蕴含注册表成员身份）+2 场景 |
| notes「canonical Markdown 真相层与可插拔后端」 | MODIFIED | `search` 纯词法 + **字段加权**口径（只影响排序）+1 场景 |

**不新增 capability、不改 `plugin_registry` 契约、不改 `MemoryBackend` Protocol。**
