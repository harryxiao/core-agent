# 提案 — 未命中记录 id 唯一化 + 神兽可召回自身轨迹（change 0117 / phase-30 分支 A）

## 背景

`coding-plan/phase-30.md` 承接 Phase 28 收口后的三条剩余项（E48 / E44 / E45-隔离），2026-10-06 用户裁决
「全部按建议」⇒ 落地 = **§3 分支 A**：**E48-b + E54 同一 change**，另三条（E48-a / E44 / E45-隔离(i)）
**登记为有意行为**（无代码改动，随本 change 一并回填 ADR 与账本）。两条代码项均为**接线/派生副作用**，
非规格违约，故按 SDD 走**规格先行**（非 `skip_specs`）。

| # | 一手事实 | 后果 |
|---|---|---|
| E48-b | `skills/router.py:154` `id=f"skills.miss.{key}.{len(self.misses)}"` —— 序号取自**进程内** `self.misses`（`:65` 单一全局 list）。**跨进程重启计数器归零** ⇒ 重启后第一条未命中重新落 `...s1.1`，**upsert 覆盖**上一进程留下的同会话记录 | 未命中记录是**事件记录**（「路由未命中: <任务原话>」），被覆盖即真丢数据（技能沉淀的输入面缺料）；且 `misses` 随会话数**无上界**线性涨 |
| E54 | `memory/store.py:115` `entry.source.startswith(exclude_source_prefixes)` 是**前缀匹配**；主装配器（`runtime.py:566`）排除 `("beast.",)` 覆盖**所有** `beast.<agent_id>`，而 `_beast_loop` **共用同一个 assembler**（`runtime.py:713`，装配器 `:559-567` 一次性构造）⇒ **神兽自己也检索不到自己的轨迹** | 神兽实为「**无自身经验**」：跨次召唤不积累，只有本次会话内的新条目（`session_id` 过滤放行本会话）——`beast-mode` spec 的独立记忆命名空间在生产只写不读 |

**登记项（本 change 零代码改动，随 ADR 一并落账）**：

1. **E48-a** 压实产物 `compaction.fact.{key}.{i}` 同会话覆盖 —— 判为**刷新式派生**（facts 由**当前**记忆重派生，
   新批次取代旧批次；保留旧批次会把过时结论重新喂进检索）。
2. **E44** 压实 ≠ 压缩（`_compact` 不裁 `ctx.messages`）—— 登记为**有意行为**（预算三层可配 + 跨轮历史已由
   change `0115` 有界回灌 + 摘要替换违「不谎报（落盘模型原话）」+ 超预算 `TOKEN_BUDGET_EXCEEDED` 显式非静默）。
3. **E45-隔离(i)** 主与兽**同读全局层**（`session_id == ""`）—— 用户「严格隔离 + 保留全局层」裁决的**有意结果**。

## 变更目标

1. **未命中记录 id 由任务内容派生**（`skills/spec.md` MODIFIED「技能路由」）：id SHALL 由任务内容（含会话键）
   确定性派生 —— 跨进程重启后同一会话的不同任务**不得互相覆盖**；重复未命中同一任务 SHALL **幂等刷新同一条目**
   （未命中清单本就按任务去重，供技能沉淀）；内存中的未命中**诊断窗口 SHALL 有界**。
   *先例*：同包 `skills/sop.py:166-168` `_skill_id_for`（组键 → 确定性 skill_id，同组覆盖同一条、不增长）。
2. **记忆检索的排除面支持「例外面」**（`memory/spec.md` ADDED「来源前缀排除与放行」）：`allow_source_prefixes`
   SHALL 在**排除面命中项**中再放行指定前缀；缺省空 ⇒ 语义逐字不变；与排除同点（排名与预算之前）。
3. **神兽可召回自身命名空间**（`beast-mode/spec.md` MODIFIED「Independent Sub-Agent with Shared Capability」）：
   神兽装配面 SHALL 放行**自身** `source = beast.<agent_id>` 的轨迹，**他兽**命名空间 SHALL NOT 进入该兽检索面；
   主 Agent 侧封存（`source=beast.*` 不被主 loop read 命中）**逐字不动**。

## Non-goals

- **不放宽「主不读兽」**：主装配器的 `exclude_source_prefixes=("beast.",)`（`runtime.py:566`）**逐字不动**
  （phase-26 E37/E38/E39 的隔离语义，红线）。
- **不改 E48-a**（压实产物覆盖）：只登记，不引入有界淘汰（相位 30 §4 裁决①销账）。
- **不真做压缩续聊**（E44）：`loop/default.py` 的 `_compact` / `planner._build_request` 一行不改。
- **不动全局层共享**（E45-隔离(i)）：不为神兽追加对全局层的排除。
- 不为每兽建独立 `(loop, memory)` 实例（change `0048` 已裁否决）；不改 `TaskHandoff` / 交接语义；
  不给宠物流单独立命名空间（其 source 归属与 `session_id` 归组不在本 change 面内）。

## 判据与取舍

- **id 用 `blake2b(digest_size=8)` 而非 `hash()`**：`hash()` 对 `str` 有**逐进程随机盐**（`PYTHONHASHSEED`）
  ⇒ 跨进程不稳定，重启后 id 仍会变，等于没修。`sop.py` 同包先例即 `blake2b`。
- **「同一会话重复未命中同一任务」采幂等**：内容派生 ⇒ 同任务同 id ⇒ upsert 刷新。这是**有意**的：
  miss 清单的消费者是技能沉淀（按任务去重本就是它的口径），且天然有界。
- **`misses` 保留 `list` 类型（不换 `deque`）**：`deque` 与 `list` **不相等**（`deque([...]) == [...]` 为 `False`），
  换型会静默打断 6 处既有断言（`tests/test_skills.py:148/318/335/342/349`、`tests/test_skill_ranking.py:140`、
  `tests/test_beast_wiring.py:93`）。改为**原地裁剪**（`del self.misses[:n]`），身份与类型都不变。
- **判据订正（相对 phase-30 §2.4 修法①的原文）**：原文写「排除集按兽裁剪 —— 排除 `loop` 与**他兽**前缀，
  放行 `beast.<自身>`」，勘察后**不纳入「排除 `loop`」**：① 它不解决 E54；② 只能摘掉主 loop 一个来源，
  主 Agent 的 L2 事实还来自 `context`（压实）/`skills`/`orchestration`/`pet` 等源，会造成**隔离面不一致**；
  ③ 与 `memory/spec.md`「按会话隔离的检索」明文（推理面**必须保留全局层**，否则人格与笔记进不了 prompt）相悖。
  ⇒ 只做**最小面**：放行自身、他兽仍排除、主侧可见面逐字不变。
- **派生而非原地改装配器**：`DynamicAssembler.with_allow_source_prefixes(...)` 返回**新**实例 —— 主 loop 与神兽
  共用装配器配置的唯一区别就是放行面，原地改会波及主 loop（红线）。派生也保证 `build_runtime(assembler=…)`
  注入路径下神兽拿到的是**同一配置**的变体，而非用 `profile` 重建的第二真源。
- **协议骨架同步**：`memory/protocol.py` 的 `read` 签名补 `session_id` —— change `0114` 只改了具体实现
  （`store.py`）未同步 Protocol（既有漂移，本次一并对齐，属同一方法签名面）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 放行面误把**他兽**轨迹放进该兽上下文 | 放行项是**精确的自身 agent_id**（`beast.qinglong`），配合排除 `("beast.",)` ⇒ 他兽仍被挡；测试用「他兽条目不得出现」做**反例守门** |
| 主 loop 封存被顺带放宽（破 phase-26 红线） | 主装配器构造与 `exclude_source_prefixes=("beast.",)` 逐字不动；测试断言主装配器仍不含任何 `beast.` 源 |
| 跨进程 id 仍不稳定 | 用 `blake2b`（非 `hash()`）；测试**显式**以「两个 Router 实例共享同一 memory」模拟重启 |
| `misses` 裁剪破坏既有断言 | 保持 `list` 类型 + 原地 `del`；既有 6 处断言在窗口内（≤1 条）逐字通过 |
| 有界窗口改变「全量未命中」语义 | 该 list 无任何生产消费方（全仓 grep：仅 `router.py:65/147/154` + 测试断言）⇒ 定为**诊断窗口**，沉淀判定不依赖它 |
