# Design 0254 — 记忆写回脱敏与压实硬伤

## D1 脱敏位置：写边界，而非消息边界

四处的共同点是「文本进入持久化面」。脱敏统一放在**落盘前**、**截断前**：

| 面 | 位置 | 顺序 |
|---|---|---|
| notes | `observe_turn` 拼正文前逐行 | redact → join → update |
| context | `Compactor._sanitize` | redact → 单条截断 |
| skills miss | `_record_miss` 构造 content | redact → 截断 |
| SOP | `observe` 拿到 writer 文本后 | redact → 空判定 → gate → register |

不在消息进入 `ctx.messages` 时脱敏：ReAct 观察是模型推理的输入，脱敏会改变模型可见信息；
本变更只约束**记忆/知识层**的持久化面（与既有 `loop` 轨迹条目脱敏同向）。

关键词分类与效应/有意义闸门仍用**原始文本**：分类是读取面判断，脱敏只改变落库形态。
截断在脱敏后执行，保证截断不会把命中密钥的后半段留在明文里。

## D2 压实产物的有界与陈旧清理

- 单条上界 `_MAX_PRODUCT_CHARS = 400`，与 `loop._MAX_ACTION_EXCERPT` 同量级；超长取头部
  （结论/决策通常前置），这是**确定性**取舍，不引入摘要调用。
- 产物 id 形态固定为 `compaction.fact.<key>.<i>` / `compaction.open.<key>.<i>`：
  - 本轮写完后按前缀扫描**索引**（`MemoryStore.index()`），解析末尾序号；
  - 序号 ≥ 本轮该类条数 ⇒ `MemoryStore.discard(id)`（新增公开方法，内部复用
    `_delete_entry` ⇒ 记 `memory.delete` 可逆效应）；
  - 解析失败的 id 不处理（不猜测）。
- 清理按类分别执行（fact 与 open 互不影响）；`keep=0` 时删除该前缀全部旧条目。
- `_guard` 仍只看**脱敏后**三类是否全空（脱敏不改变关键词文本的非空性）。

## D3 空关键事实

`scrub_key_fact` 是「抽取器不构成信任边界」的落地点：`entity` 与 `value` strip 后为空 ⇒ 返回
`None`（丢弃）。即便 `ref` 可用也丢弃——`content` 会是 `实体: `，无可复用信息，且空值覆盖会
抹掉同实体既有正确取值。既有合法事实的截断/脱敏路径逐字不变。

## D4 兼容性

- `MemoryStore.discard` 是新增方法；`MemoryStore` Protocol 与后端协议不改（鸭子类型）。
- 未命中 id 仍由原始任务 digest 派生 ⇒ 幂等、跨进程不覆盖、诊断窗口等既有场景逐字不变。
- SOP 文本无密钥时 `redact_secrets` 恒等 ⇒ 入库文本不变（除超长由 P1 处理）。
- 无旧序号的会话不产生删除效应。

## 验证

- 六例红测试覆盖：notes / compactor 脱敏 / compactor 上界 / compactor 陈旧清理 / router / SOP /
  keyfact 空值。
- 反证：逐点摘除对应语句，断言对应用例红；复原 md5 一致。
