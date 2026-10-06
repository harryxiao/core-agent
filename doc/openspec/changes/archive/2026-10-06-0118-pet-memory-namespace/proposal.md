# 提案 — 宠物记忆独立命名空间（change 0118 / phase-30 §8-A 遗留项）

## 背景

`coding-plan/phase-30.md` §8-A 登记的唯一**待裁决**项：宠物 loop（`runtime._pet_loop`）的 `DefaultLoop`
**不传 `source=`** ⇒ 宠物自治轨迹以**默认 `source="loop"`** 落库，与主 Agent 同命名空间。2026-10-06
用户裁决「**物接独立命名空间，先做**」（取向＝与 phase-26 神兽**同型**：标注 + 封存 + 自放行）。

| # | 一手事实 | 后果 |
|---|---|---|
| 1 | `loop/default.py:525` `source=self._source`，`_pet_loop`（`runtime.py:902-919`）未传 `source` ⇒ 取缺省 `"loop"` | 宠物轨迹与主 Agent 轨迹**同 source**，命名空间维度上不可区分；`source` 是 phase-26 立的 Agent 身份维度（主 `loop` / 神兽 `beast.<agent_id>`），宠物**无自身身份** |
| 2 | `memory/store.py:124-129` 会话过滤在 **`session_id` 非空**时生效；**空串 ⇒ 不过滤**（fail-open，change `0114` 语义） | **可达泄漏**：主 Agent 以**未带 `--session`** 方式运行（CLI 一次性 `run`、库层直调 `DefaultLoop()`）时，宠物自治轨迹（`session_id=宠物会话 id`）**不被会话面挡住**、且因 `source="loop"` 也不被来源面挡住 ⇒ **被主 Agent 读成自身事实**（system prompt 污染） |
| 3 | `_pet_loop` 的 planner **共用主装配器**（`runtime.py:907`；装配器 `:559-567` 一次性构造，排除面 `:566` = `("beast.",)`） | 与 phase-26 E54 同型：若要封存宠物命名空间，**同一份配置**会把宠物自己也挡掉 ⇒ 须**派生**装配器放行自身 |

**契约面现状（**非违约**）**：`pet-mode` spec 已明文 ①宠物轨迹按 `session_id` 归属（`:231-234`）、②主人偏好
`source=user` 保持全局层（`:239`），**未**规定宠物轨迹的 `source` 命名空间。与 phase-26 神兽**不可类比**
——`beast-mode` spec `:54` 早已明写「独立记忆命名空间」，那次断的只是接线；本次是**新增能力**，故
**规格先行**（非 `skip_specs`；先例 change `0028`：全新能力即新 Requirement）。

> 前情：change `0117` 的 Non-goals 已明写「不给宠物单独立命名空间（其 source 归属与 `session_id` 归组
> 不在本 change 面内）」—— 本 change 正是接续该条。

## 变更目标

**`pet-mode/spec.md` MODIFIED「Pet Session Runtime Wiring」**，新增命名空间条款：

1. 宠物经由专属 loop 产生的**执行轨迹** SHALL 落**独立记忆命名空间**（条目 `source=pet`），与主 Agent
   （`source=loop`）、神兽（`source=beast.<agent_id>`）三者互不混同。
2. 主 Agent（及神兽）的记忆检索面 SHALL **封存** `pet` 命名空间 —— 宠物自治所得 SHALL NOT 被吸收为
   前台 Agent 的自身事实。
3. 封存 SHALL NOT 使宠物读不到**自身**轨迹：宠物上下文装配 SHALL 在排除面内**放行自身**命名空间。
4. `session_id` 归属与 `source` 命名空间**同时成立、互不替代**：前者隔离**会话个体**，后者隔离
   **Agent 身份**。
5. 主人偏好（`source=user`）SHALL 不受命名空间封存影响（刻意知识，全局层，逐字不动）。

## Non-goals

- **不动主人偏好通道**：`PetSession.observe` 的 `source="user"`（`pet/core/session.py:200`）**逐字不动**
  （spec `:233/:239` 刻意知识 + 全局层）。
- **不放宽神兽封存**：主装配器既有 `exclude_source_prefixes` 中的 `"beast."` **逐字不动**
  （phase-26 E37/E38/E39 隔离红线）。
- **不为每只宠物建独立 `(loop, memory)` 实例**（change `0048` 已裁否决）；**不改** `session_id` 归属语义
  （change `0114`）；**不改** `DefaultLoop.remember` 的 `id=f"loop.{trace_id}"` 硬编码（phase-26 有意保留，
  与神兽同型：神兽条目亦为 `id=loop.<trace_id>` + `source=beast.*`）。
- **不给宠物 loop 接技能路由 / constraints 熔断链**（E25 既有形态，与命名空间无关）。
- **不动 `PetSession` / `PetControl` / 探索器 / 微任务**任何行为面。

## 判据与取舍

- **命名空间取常量 `"pet"` 而非 `pet.<个体 id>`**：宠物 loop 是**单实例共享**（`runtime.py:922-935`
  一只 `pet_loop` 被 `PetManager` 的 factory 复用于所有宠物会话，多宠物靠 `session_id` 区分）——
  `source` 在 loop 构造期固定，无法承载个体 id。故 **`source` = 子系统身份（pet）**、
  **`session_id` = 个体身份（哪只宠物）**。与神兽不同（神兽**每兽一个 loop 实例** ⇒ `source=beast.<agent_id>`
  天然带个体），但两者语义闭合：`source` 划 Agent 身份，个体粒度由 `session_id` 承载。
- **排除前缀用 `"pet"`（裸根）而非 `"pet."`**：命名空间字符串就是 `"pet"`，`startswith("pet.")` **不命中**
  自身。全仓 `source` 字面量全集 = `loop` / `beast.<id>` / `user` / `core-profile` / `evolution` /
  `skills` / `context` / `notes.turn` —— **无一以 `pet` 开头** ⇒ 裸前缀无语义误伤（已在 ADR 记已知局限）。
- **派生装配器而非原地改**：`DynamicAssembler.with_allow_source_prefixes("pet")` 返回**新**实例
  （change `0117` 新增的机制）—— 主 loop、神兽、子 Agent 共用一份配置，原地改会波及全体。派生保证
  「同一配置 + 换放行面」。
- **神兽装配面**由同一配置派生 ⇒ 亦不命中 `pet`：**语义一致**（后台自治体之间亦不混同），且今日**无实际
  行为变化**（神兽读取恒带 `session_id=beast.<agent_id>`，宠物条目本就被会话过滤挡下）。
- **主 Agent 封存的实际影响面**：会话化运行（带 `--session`）**逐字不变**（会话过滤已覆盖）；仅
  **未带会话**的运行不再看到宠物自治所得 —— 这正是本 change 要闭合的泄漏。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 封存把宠物**自己**的轨迹也挡掉（E54 原样重演） | 宠物 planner 用**派生**装配器 `with_allow_source_prefixes("pet")`；测试以「宠物自身条目出现」做**正向守门** |
| 顺带放宽神兽/主线封存（破 phase-26 红线） | `"beast."` 排除项逐字不动；测试断言主装配器排除面仍含 `"beast."` 且仍不含任何 `beast.*` 条目 |
| 误伤主线/全局层知识（人格、`notes`） | 排除面只加 `"pet"`，不触碰 `loop`/`user`/`core-profile`/`context`/`skills`/`notes.turn`；测试以「主线条目仍出现 + `source=user` 偏好仍出现」做**反例守门** |
| `source="pet"` 与既有个体粒度混淆 | 全仓 `source` 字面量已穷举（无 `pet` 前缀冲突）；规格明写 `source`/`session_id` 双维度分工 |
