# Beast Mode 接口（神兽模式，beast-mode）

> 编排层扩展（前台重大任务，pet-mode 的对偶）的接口文档。神兽（beast）是 20 个预定义
> 的山海经神兽，每个神兽有独有神通，用于前台重大任务；运行时能力分两层——L1 工具共享
> 全局 `ToolProvider`（真实可用）、L3 神通以 Skill 注册进全局 `SkillLibrary` 并由神兽 loop
> **域内真实路由**（0057 接线：`SkillRouter.match(domain=beast.agent_id)`）。
>
> 对应规格：`doc/openspec/specs/beast-mode/spec.md`（Beast Registry / Beast Session
> Lifecycle / Summon via Handoff / Independent Sub-Agent with Shared Capability /
> Innate Skills and Dedicated Routing / Async Concurrent Execution and Auto-Recall /
> Manual Recall / Three-Entry Activation）。

---

## §1 BeastSessionState —— 神兽会话状态（四态状态机）

模块：`src/core/beast/models.py`。枚举类型。

| 状态 | 值 | 语义 |
| --- | --- | --- |
| `DORMANT` | `"dormant"` | 未显形（休眠） |
| `MANIFEST` | `"manifest"` | 已显形（召唤就位） |
| `ACTIVE` | `"active"` | 执行中 |
| `RECALLED` | `"recalled"` | 已召回（记忆分区封存） |

状态转移：`DORMANT → MANIFEST → ACTIVE → RECALLED`，`RECALLED` 可再次
`manifest()` 回到 `MANIFEST`。不同于 pet 模式的 `IDLE/ACTIVE/BACKOFF/TERMINATED`。

---

## §2 Beast —— 内置只读神兽定义

模块：`src/core/beast/models.py`。`@dataclass(frozen=True)`，内置只读。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `agent_id` | `str` | 全局唯一，如 `"beast.qinglong"` |
| `title` | `str` | 称号，如 `"青龙"` |
| `domain` | `str` | 领域 / 重大任务职责 |
| `innate_skill` | `str` | 独有神通 `skill_id`，如 `"beast.qinglong.blueprint"` |
| `capabilities` | `tuple[str, ...]` | 能力标签，供 `MultiAgentRouter.match` 打分 |

内置只读：区别于 `pet.md` 用户自定义角色。注册表无写入口，运行期不可增改。

---

## §3 BeastRegistry —— 二十神兽名册（Beast Registry）

模块：`src/core/beast/registry.py`。20 个预定义山海经神兽，按 `agent_id` 索引，
只读。

| 方法 | 签名 | 说明 |
| --- | --- | --- |
| `lookup` | `lookup(agent_id: str) -> Beast \| None` | 按 `agent_id` 精确查找，未命中返回 `None` |
| `resolve` | `resolve(name: str) -> Beast \| None` | 按 `agent_id` / 称号 / 拼音别名解析，未命中返回 `None` |
| `all` | `all() -> tuple[Beast, ...]` | 全部内置神兽 |
| `agent_ids` | `agent_ids() -> tuple[str, ...]` | 全部 `agent_id` |

注册表无写入口，运行期不可增改。

---

## §4 BeastSession —— 神兽会话生命周期（Beast Session Lifecycle）

模块：`src/core/beast/session.py`。单只神兽的会话句柄，四态状态机收口；
独立 `LoopPlugin` 实例（独立上下文 + 独立记忆）。

| 成员 | 签名 | 说明 |
| --- | --- | --- |
| `__init__` | `__init__(beast, *, loop=None, memory=None)` | 初始化，初始态 `DORMANT` |
| `manifest` | `manifest() -> None` | 显形：`DORMANT/RECALLED → MANIFEST`；已在岗抛 `BEAST_ALREADY_MANIFEST` |
| `activate` | `activate() -> None` | 开始执行：`MANIFEST → ACTIVE`；未显形抛 `BEAST_NOT_MANIFEST` |
| `summon` | `summon() -> None` | 召唤 = 显形 + 激活：`DORMANT/RECALLED → ACTIVE` |
| `recall` | `recall() -> None` | 召回：`MANIFEST/ACTIVE → RECALLED`；无在岗抛 `BEAST_NOT_MANIFEST` |
| `remember` | `remember(content: str, trace_id: str = "") -> MemoryEntry` | 神兽产物以 `source=beast.<agent_id>` 落 L2 facts 层，与主记忆隔离 |
| `result_summary` | `result_summary() -> dict` | **结果可见性**（change `0113`／ADR-0106，账本 E46）：最近一次交接结果的**只读**摘要 `agent_id` / `has_result` / `reply` / `failed`。**只读取用**会话持有的 `last_result` —— 不落 L2、不写记忆（`summon` CLI 据此呈现结果正文） |

属性：`beast`、`state`、`loop`（`LoopPlugin`）、`last_trace_id`、`last_result`。

**结果可见性走查询面**（change `0113`）：`entry._summon` 在状态行后呈现结果（`结果（成功/失败）：…`），
无结果时**不打印**该行（不编造）。**不落 L2 的理由**：主 loop 装配 `exclude_source_prefixes=("beast.",)`
（beast spec `:89` 记忆分区封存）⇒ 以 `source=beast.*` 落库的正文主 Agent **检索不到**，写了等于没写。

独立记忆：`MemoryEntry.source = beast.<agent_id>`（区别于主 Agent 的 `source=loop`），
落 L2 facts 层隔离。**生产接线（change `0110`／ADR-0103）**：
① 神兽 loop 由组合根注入 `source=beast.<agent_id>`（`DefaultLoop(source=…)`），故会话轨迹由**真实 loop**
写入"`source=beast.<agent_id>` + `session_id=beast.<agent_id>`"的条目（此前 `remember` 硬编码 `source="loop"`，
神兽产物混入主记忆）；② `BeastManager.summon` 经 `TaskHandoff(session_id=beast.agent_id)` 把会话归属转交子 loop
（否则条目 `session_id` 空串，压实按会话聚合时与主线未归组条目同组）；③ **封存**（spec「记忆分区封存」）
由读取侧落地：主 loop 的 `DynamicAssembler` 传 `exclude_source_prefixes=("beast.",)` ⇒ 神兽分区不再被主 loop
read 命中；`session.recall()`（自动回归）为封存的召回面。
**④ 自身轨迹可召回（change `0117`／ADR-0110）**：`_beast_loop` 的装配器经
`assembler.with_allow_source_prefixes(beast.agent_id)` **派生** —— 排除面逐字继承（`("beast.",)`），
放行面加 `beast.<agent_id>` ⇒ 神兽可召回**自己**的过往轨迹，**他兽仍被排除**，主侧可见面逐字不变。
派生而非原地改（主 loop 与神兽共用一份配置，原地改会波及主 loop）。
`BeastSession.remember` 为会话级 API（库层直接调用面），生产轨迹由 loop 写入，二者同口径不互相代笔。

---

## §5 错误码（BeastError / BeastErrorCode）

模块：`src/core/beast/errors.py`。

| 错误码 | 语义 |
| --- | --- |
| `BEAST_ALREADY_MANIFEST` | 神兽已在岗，重复召唤被拒 |
| `BEAST_NOT_MANIFEST` | 未显形无法激活 / 无在岗召回无效 |
| `BEAST_MEMORY_WRITE_FAILED` | 神兽记忆写入 L2 facts 层失败 |

未知神兽（`resolve` 未命中）复用编排层 `orchestration` 的 `NO_AGENT_MATCH`，不在本模块定义。

---

## §6 BeastManager —— 多神兽管理（Summon via Handoff）

模块：`src/core/beast/manager.py`。维护 `dict[agent_id, BeastSession]` 多实例；
复用编排层 `MultiAgentRouter.handoff` 交接语义（神兽即内置 `AgentProfile`），
不另造第二真源。

| 方法 | 签名 | 说明 |
| --- | --- | --- |
| `__init__` | `__init__(*, registry=None, router=None, loop_factory=None, memory=None)` | `loop_factory` 按兽造独立 loop，`memory` 为共享记忆（缺省不注入 = 库层零行为变化） |
| `summon` | `async summon(agent_id: str, task: str = "") -> BeastSession` | 召唤 = 显形激活 + 异步 `handoff` 交接，完成后自动回归 `RECALLED`；未知神兽复用 `NO_AGENT_MATCH` |
| `recall` | `recall(agent_id: str) -> BeastSession` | 召回神兽 |
| `get` | `get(agent_id: str) -> BeastSession \| None` | 按 `agent_id` 取会话 |
| `active` | `active() -> list[BeastSession]` | 在岗（`MANIFEST`/`ACTIVE`）会话 |
| `all` | `all() -> list[BeastSession]` | 全部在册会话 |

并发语义：兽间并行（可同时显形多兽）、兽内串行（同兽重复召唤拒绝、无同兽双实例）。

---

## §7 BeastActivator —— 三入口激活（Three-Entry Activation）

模块：`src/core/beast/activator.py`。三入口（Slash / CLI / WebUI 自然语言）
统一收敛到 `BeastManager.summon` / `recall`。

| 方法 | 签名 | 说明 |
| --- | --- | --- |
| `activate_from_slash` | `async activate_from_slash(target: str, task: str = "") -> BeastSession` | Slash 命令召唤 |
| `activate_from_cli` | `async activate_from_cli(beast: str, rest: list[str]) -> BeastSession` | CLI argv 召唤 |
| `activate_from_nl` | `async activate_from_nl(user_input: str) -> BeastSession` | WebUI 自然语言召唤 |
| `recall_from_slash` | `recall_from_slash(target: str) -> BeastSession` | Slash 命令召回 |
| `recall_from_cli` | `recall_from_cli(beast: str) -> BeastSession` | CLI argv 召回 |
| `recall_from_nl` | `recall_from_nl(user_input: str) -> BeastSession` | WebUI 自然语言召回 |

辅助：`_resolve_nl(user_input: str) -> str`（自然语言解析出目标兽名）。

### §7.1 三入口生产落点（change `0137` / 账本 E74）

契约方法此前**齐备但生产只有 CLI 一条通**；本表钉住三入口各自的**生产落点**（同一 `Runtime.beast_activator`
实例，无第二真源）：

| 入口 | 生产落点 | 落点方法 |
| --- | --- | --- |
| Slash（TUI `/summon` `/recall`） | `ui/repl.py` 分发 → `UIAPILayer.beast_command` | `activate_from_slash` / `recall_from_slash` |
| CLI（`core-agent summon` / `recall`） | `entry._summon` / `entry._recall` | `activate_from_cli` / `recall_from_cli` |
| WebUI 自然语言（「召唤 X 兽做 Y」） | `UIAPILayer.activate_beast`（**消息驱动，无 HTTP 端点**） | `activate_from_nl` |

三入口与 pet 同型：门控关闭时 `Runtime.beast_activator is None` ⇒ `UI_BEAST_UNSET` / CLI 报
「beast 模块已关闭」（fail-explicit）。

---

## §8 神通注册（Innate Skills）

模块：`src/core/beast/skills.py`。20 神通注册进全局 `SkillLibrary`。

| 方法 | 签名 | 说明 |
| --- | --- | --- |
| `build_innate_skills` | `build_innate_skills(registry: BeastRegistry) -> list[Skill]` | 构建 20 神兽独有神通列表 |
| `register_innate_skills` | `register_innate_skills(library: SkillLibrary, registry: BeastRegistry) -> int` | 注册进全局 `SkillLibrary`，返回条数 |

> 专属路由语义（0057 起**路由期强制**）：`skill_id` 为三节 `beast.<域>.<技能>` 者是专属技能，
> 仅当 `SkillRouter.match(task, domain="beast.<域>")` 时进候选；他兽域与主 Agent（`domain=None`）
> 都**看不到**（作用域保证非本域专属神通不可达，非调用方自觉）。主 Agent 与通用子 Agent
> 传递缺省 `domain`，故专属神通不灌主 prompt。

---

## §10 组合根装配（0057）

模块：`src/core/runtime.py`。`build_runtime` 在技能面接线处注册神通，并在收尾构造神兽面：

| 产物 | 装配 |
| --- | --- |
| 注册 | `BeastRegistry()` → `register_innate_skills(skill_library, registry)`（名册每兽一枚） |
| 钩子 | `_loop_hooks(domain=None)`：主 loop 与通用子 Agent 用缺省；`_beast_loop(beast)` 传 `beast.agent_id` |
| `Runtime.beast_manager` | `BeastManager(registry=…, router=MultiAgentRouter([]), loop_factory=_beast_loop, memory=memory)` |
| `Runtime.beast_activator` | `BeastActivator(beast_manager)` —— CLI `summon`/`recall` 经 `build_runtime` 取此实例（`entry._summon/_recall`） |
| **门控**（change `0067`） | `features.beast: false` ⇒ 注册与上两行**都不发生**（`Runtime.beast_manager`/`beast_activator` 为空），`summon`/`recall` 报「beast 模块已关闭」 |
| **命名空间**（change `0110`） | `_beast_loop` 注入 `source=beast.<agent_id>`（轨迹落独立分区）；主 loop 装配器 `DynamicAssembler(exclude_source_prefixes=("beast.",))`（封存：主 loop read 不命中神兽分区） |
| **自身轨迹可召回**（change `0117`） | `_beast_loop` 用 `assembler.with_allow_source_prefixes(beast.agent_id)` **派生**装配器（排除面继承 + 放行自身）⇒ 兽读得到自己的轨迹；他兽仍排除、主侧可见面逐字不变（见 §4 ④） |

神兽 loop 与主 loop 同构（共享 `memory`/`tracer`/`guard`/`approver`/约束链），差异是
技能路由的域名作用域、工具面（子 loop 工具面不含 `tools.delegate`）与**记忆命名空间**
（`source=beast.<agent_id>`，见 §4）。

> **已知局限（change `0110` 明示）**：① ~~主 loop 与神兽 loop **共享同一** `DynamicAssembler` 实例
> ⇒ 神兽自身的上下文装配亦不命中 `beast.*`~~ —— **已由 change `0117` 部分闭合**：神兽改用**派生**
> 装配器（读得到**自身** `beast.<agent_id>`；**他兽**仍读不到，有意与封存同向）；主 loop 侧的装配器
> 与「共享一份配置」的事实不变；
> ② 压实摘要的 `source` 恒为 `"compaction"` ⇒ 神兽分区被压实后的**摘要**仍可被主 loop 读到 ——
> 按 source 命名空间隔离的残留缺口，登记待议（不在本 change 扩大改动面）。

---

## §9 关联

- 规格：`doc/openspec/specs/beast-mode/spec.md`
- 变更：`doc/openspec/changes/archive/2026-09-28-0034-beast-mode/`（已归档）、
  `2026-10-04-0057-beast-runtime-bridge/`（运行时桥接，ADR-0060）
- 复用接口：`orchestration-interface.md`（`MultiAgentRouter.handoff` / `AgentProfile` / `TaskHandoff` / `NO_AGENT_MATCH`）、`skills-interface.md`（`SkillLibrary` / `Skill`）、`memory-interface.md`（`MemoryEntry.source`）、`loop-interface.md`（`LoopPlugin` / `LoopResult` / `LoopResult.failed`）、`cli-ops-interface.md`（`CommandGroup`）
