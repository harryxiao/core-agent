# Phase 10 — 神兽召唤层（beast-mode / summon）

> 里程碑：**M7 神兽召唤**
> 位置：编排层扩展（前台重大任务，pet-mode 的对偶）+ 接入层（三入口）+ 能力层（神通 Skill）+ 数据层（BeastRegistry）
> 上游：Phase 8（pet 会话/激活器）+ Phase 9（入口层）+ orchestration（MultiAgentRouter）+ skills（SkillLibrary）

---

## 1. 范围与定位

本 Phase 在「宠物模式（后台重复简单任务，Phase 8）」之外，新增对偶能力「**神兽召唤（前台重大任务）**」：20 个预定义山海经神兽，各持**独有神通**，且**直接复用主 Agent 全技能**执行重大任务。交付 4 个能力：

| Capability | 职责一句话 | 分层 |
|---|---|---|
| `beast-registry` | 20 山海经神兽预定义（内置只读）+ 独有神通清单 | 数据层 |
| `beast-mode` | `BeastSession` 多实例生命周期 + 召唤/回归状态机 | 编排层/会话层 |
| `innate-skills` | 神通 = Skill（`beast.*` 命名空间），注册进全局 `SkillLibrary` | 能力层 |
| `summon-activator` | 三入口激活（`/summon` 斜杠 + `summon` CLI verb + WebUI 自然语言） | 接入层 |

**核心机制（三条铁律）**：

1. **召唤 = handoff**。神兽是内置预定义 `AgentProfile`，召唤即 `MultiAgentRouter.handoff(beast_id, TaskHandoff(...))`，复用编排层既有交接语义，不另造第二真源。
2. **独立子 Agent + 共享能力集**（D2 决策）。神兽 `AgentProfile.loop` 是独立 `LoopPlugin` 实例 → **独立记忆 namespace**（`MemoryEntry.source = f"beast.{agent_id}"`）+ **独立上下文**（`DynamicAssembler.build()` 按神兽任务阶段装配 `ContextPack`）；运行时能力分两层：**L1 工具**共享全局 `ToolProvider`（loop 原生消费，通用能力真实可用）+ **L3 技能**（神通 `beast.*`）注册进全局 `SkillLibrary`（注册/共享实例可验证，loop→skill 运行时调用 deferred）。→「复用主 Agent 通用能力」成立，「技能运行时调用」留待桥接。
3. **并发多兽**（A3 决策）。`BeastSession` 维护 `dict[agent_id, BeastSession]` 多实例，可同时显形多兽并行执行；同兽重复召唤先拒绝或先回归（兽间并行、兽内串行）。

**生命周期（D3 决策）**：`DORMANT → MANIFEST → ACTIVE → RECALLED`。召唤**异步并发执行**（`handoff` 经 `loop.arun` 非阻塞，多兽并行互不阻塞，契合「前台重大任务」）；任务完成自动回归（据 `LoopResult.failed` 判定成败，字段经本 Phase 0034 契约 delta 补齐）+ 手动复位（`/recall` / `recall` CLI / NL「召回」→ 按 beast_id 复位，异步执行下无「中断在岗兽」窗口）。

### 1.1 二十神兽名册（BeastRegistry 内置预定义，只读）

> `agent_id = beast.<拼音>`；独有神通 = `beast.<拼音>.<skill>` 注册进全局 `SkillLibrary`（3 段 id，中段=拼音；`_domain()` 约定解析 `skills.<domain>.<name>` 前缀，神兽神通走 `beast.*` 前缀不依赖其索引，`list_by_domain("beast")` 恒空；专属路由由 `BeastSession` 按 agent_id 前缀过滤候选；**运行时调用 deferred**）；
> `capabilities` 标签供 `MultiAgentRouter.match()` 关键词打分路由。

| # | 神兽 | agent_id | 领域 / 重大任务职责 | 独有神通 skill_id |
|---|---|---|---|---|
| 1 | 白泽 | `beast.baize` | 知识通晓 / 跨域检索与信息整合 | `beast.baize.omniscience` |
| 2 | 青龙 | `beast.qinglong` | 架构设计 / 蓝图与骨架生成 | `beast.qinglong.blueprint` |
| 3 | 白虎 | `beast.baihu` | 性能攻坚 / 剖析与瓶颈定位 | `beast.baihu.profile` |
| 4 | 朱雀 | `beast.zhuque` | 重构 / 涅槃式重写 | `beast.zhuque.rebirth` |
| 5 | 玄武 | `beast.xuanwu` | 安全防御 / 审计与加固 | `beast.xuanwu.audit` |
| 6 | 麒麟 | `beast.qilin` | 质量保障 / 测试生成 | `beast.qilin.testgen` |
| 7 | 应龙 | `beast.yinglong` | 部署运维 / 发布与 CI/CD | `beast.yinglong.deploy` |
| 8 | 烛龙 | `beast.zhulong` | 调度 / 定时与长期驻留任务 | `beast.zhulong.schedule` |
| 9 | 九尾狐 | `beast.jiuweihu` | 前端交互 / UI 生成与体验 | `beast.jiuweihu.uigen` |
| 10 | 精卫 | `beast.jingwei` | 长任务 / 执着重试直至完成 | `beast.jingwei.persist` |
| 11 | 刑天 | `beast.xingtian` | 故障恢复 / 无畏式故障自愈 | `beast.xingtian.fearless` |
| 12 | 饕餮 | `beast.taotie` | 大数据 / 批量吞吐与吞噬式处理 | `beast.taotie.bulk` |
| 13 | 穷奇 | `beast.qiongqi` | 代码评审 / 善恶判别（好坏代码区分） | `beast.qiongqi.review` |
| 14 | 梼杌 | `beast.taowu` | 混沌工程 / 破坏性注入测试 | `beast.taowu.chaos` |
| 15 | 混沌 | `beast.hundun` | 模糊测试 / 随机输入探索 | `beast.hundun.fuzz` |
| 16 | 英招 | `beast.yingzhao` | 项目管理 / 任务编排与统筹 | `beast.yingzhao.orchestrate` |
| 17 | 陆吾 | `beast.luwu` | 多模块协调 / 网关与集成 | `beast.luwu.gateway` |
| 18 | 天狗 | `beast.tiangou` | 依赖迁移 / 版本升级与兼容 | `beast.tiangou.migrate` |
| 19 | 九凤 | `beast.jiufeng` | 并发 / 并行执行加速 | `beast.jiufeng.parallel` |
| 20 | 貔貅 | `beast.pixiu` | 资源优化 / 清理与回收 | `beast.pixiu.reclaim` |

> 20 神通均为「领域专用」Skill，是神兽独有；通用能力（文件/网络/搜索等）走全局 `ToolProvider`（L1 工具），神兽不重复实现。

---

## 2. 契约红线（实证现状 vs 契约）

### 2.1 已实现契约（直接复用，禁止重复实现）

| 契约 | 实证落点 | 复用方式 |
|---|---|---|
| `AgentProfile`（agent_id / capabilities / loop） | `src/core/orchestration/models.py:73` | 神兽 = `AgentProfile` 实例 |
| `TaskHandoff`（task / context_pack / acceptance / deadline / priority） | `src/core/orchestration/models.py:62` | 召唤任务交接载荷 |
| `MultiAgentRouter`（register / match / handoff） | `src/core/orchestration/router.py:16` | 召唤/回归走 `handoff`；`match` 按 capabilities 关键词打分 |
| `SkillLibrary` / `SkillRouter` | `src/core/skills/library.py:23` / `router.py:17` | 神通注册进全局库（真实）；`SkillRouter` 无运行时消费方，loop→skill 调用 deferred |
| `PetSession` / `PetActivator`（三入口范式） | `src/core/pet/core/session.py:25` / `activator.py:32` | `BeastActivator` 平移 `activate_from_slash/cli/nl` 三入口结构 |
| `ContextPack` / `DynamicAssembler` | `doc/03-interfaces/context-interface.md` | 神兽独立上下文装配 |
| `MemoryEntry.source` | `doc/03-interfaces/memory-interface.md` §2 | 记忆分区标记 `beast.<agent_id>` |

**关键现状约束**：`MultiAgentRouter.handoff()` 现为**同步执行**（`profile.loop.run(handoff.task)` 后返回 `trace_id`，router.py:50-51），且 `LoopResult` 仅 `reply + trace_id` 无成败状态、`handoff` 丢弃完整结果——**自动回归缺信号、同步执行无「中断在岗兽」窗口**。故本 Phase 须小改 loop/orchestration 契约（`LoopResult` 补 `failed` 字段 + `handoff` 返回完整 `LoopResult` + `loop.run`→`loop.arun` 异步化，参照 scheduler.py 真并发范式），「手动召回」按 beast_id 精确复位落地（多兽并行、兽间互不阻塞）。

### 2.2 契约缺口（须走 OpenSpec 变更补齐）

| 缺口 | 现状 | 补法 |
|---|---|---|
| 无 beast 规格 | `openspec/specs/` 27 个 spec 无 beast/summon | 新增 `openspec/specs/beast-mode/spec.md` + `openspec/changes/0034-beast-mode/` |
| CLI 无 summon/recall 动词 | baseline 30 动词（phase-9 §2 权威口径）无 summon/recall | cli-ops `CommandGroup` 扩展 `summon <beast> [task]`、`recall`、`beast list` |
| 斜杠无 /summon /recall | `UIAPILayer.list_tools()` 无对应 tool_id | 新增 `beast.summon`、`beast.recall` 斜杠候选（参照 pet `_SLASH_TOOLS` 映射，不进内核接口） |
| 神通未注册 | `SkillLibrary` 无 `beast.*` | 20 神通以 Skill 注册，命名空间 `beast.<pinyin>` |
| `LoopResult` 无成败信号 | `loop/protocol.py` 仅 `reply + trace_id`；`handoff` 只返回 `trace_id` | 补 `LoopResult.failed` + `handoff` 异步执行（`loop.run`→`loop.arun`）并返回完整 `LoopResult`（loop/orchestration 契约 delta，随 0034 同提） |
| 神通运行时调用缺桥接 | loop coeffect 仅 `tools:provider`（`ToolProvider`），`SkillRouter` 零消费方 | skills→loop 运行时调用 **deferred**（本 Phase 只做注册 + 专属路由语义） |
| 神通专属路由缺 scoping | `SkillRouter.match()` 全局打分无作用域 | `BeastSession` 侧过滤候选 / `SkillRouter` 补 domain 参数（本 Phase 定语义，runtime deferred） |

---

## 3. 验收口径（M7 神兽召唤）

- **召唤**：`/summon 青龙 架构一个订单系统` → `BeastSession` 显形 `beast.qinglong`，`MultiAgentRouter.handoff` 异步返回完整 `LoopResult`（含 `trace_id`），神兽 loop 走完整编排执行；多兽可同时显形并行。
- **独有神通**：`SkillLibrary` 含 20 个 `beast.*` 技能（注册可验证）；专属路由（他兽不可路由）为路由层语义，本 Phase 定语义 + 单测断言，runtime 调用 deferred。
- **复用主 Agent 能力**：神兽 loop 的 `ToolProvider` 与主 Agent 同源（L1 工具运行时真实共享）；`SkillLibrary` 注册层共享（L3 技能，运行时调用 deferred）。
- **独立记忆**：神兽执行产生的 `MemoryEntry.source` 均为 `beast.<agent_id>`，与主 Agent（`source=loop`）隔离，不污染主记忆。
- **并发多兽**：多兽可同时显形并行执行（兽间并行、互不阻塞）；同兽重复召唤返回明确拒绝（或先回归），不存在同兽双实例（兽内串行）。
- **自动回归**：神兽 loop 完成后据 `LoopResult.failed` 判定，`BeastSession` 迁至 `RECALLED`，记忆分区封存。
- **手动复位**：`/recall <beast>` 或 `recall <beast>` CLI 按 beast_id 复位 → `RECALLED`，可再次召唤该兽（异步执行下无中断窗口，仅复位目标兽）。

---

## 4. 首步任务（开工前）

1. **走 OpenSpec 变更**（openspec_sop）：`beast-mode` 新增能力 → `openspec/changes/0034-beast-mode/`（proposal + design + spec delta），产出 `openspec/specs/beast-mode/spec.md`；**含 loop/orchestration 契约 delta**（`LoopResult.failed` + `handoff` 异步执行（`loop.run`→`loop.arun`）并返回完整结果），`validate --all` 通过。
2. **对齐 command 面权威口径**：读 `cli-contract-baseline.md` §2（30 动词 + 14 flag）确认 summon/recall 动词的 flag 归属（如 `--beast`、`--force`），不凭空造参数。
3. **确认 skills 的 Skill 注册契约**：读 `doc/03-interfaces/skills-interface.md`（Skill 字段：skill_id / description / task_types / preconditions / param_schema / instructions / version / status），神通 Skill 严格按此契约落地，禁造新 Skill 结构；**runtime 调用 deferred**（loop 只消费 `ToolProvider`，不接 SkillLibrary）。
4. **复用 pet 六模块骨架**：以 `src/core/pet/` 为模板平移出 `src/core/beast/`（models / session / activator / manager / registry / skills），保持与 pet 相同的分层粒度。

---

## 5. 依赖与顺序

```
Phase 8(pet 生命周期范式) ─┐
Phase 9(入口层/command 面) ─┼─► 契约补齐(0034 change + spec) ─► 数据层 BeastRegistry + 20 神通
orchestration(MultiAgentRouter) ─┘                              ─► 会话层 BeastSession + BeastActivator
skills(SkillLibrary 全局) ──────────────────────────────────────► 编排层 handoff 接线 + 回归闭环
```

- **硬依赖**：orchestration / skills / pet / context / memory 均已落地（Phase 3/4/8）；本 Phase 仅**小改** loop/orchestration 契约（`LoopResult.failed` + `handoff` 返回结果），不重建编排层。
- **顺序**：契约（0034 change）→ 数据层（registry + 神通 Skill）→ 会话层（session/activator）→ 编排接线（handoff + 回归）→ 入口层（slash + CLI + NL）。
- **并行**：20 神兽神通 Skill 的定义与 BeastRegistry 数据可并行推进，互不阻塞。

---

## 6. 里程碑验收清单

- [x] `openspec/changes/0034-beast-mode/` 归档完成，`openspec/specs/beast-mode/spec.md` 存在且 `validate --all` 通过；loop/orchestration 契约 delta（`LoopResult.failed` + `handoff` 异步执行（`loop.run`→`loop.arun`）并返回结果）并入
- [x] `BeastRegistry` 内置 20 神兽（agent_id + 称号 + 领域 + 独有神通），只读不可改（区别于 pet.md 用户自定义）
- [x] 20 个 `beast.*` 神通 Skill 注册进全局 `SkillLibrary`，专属路由语义（他兽不可用，runtime 调用 deferred）
- [x] `BeastSession` 四态状态机（DORMANT/MANIFEST/ACTIVE/RECALLED）+ 多实例并发（`dict[agent_id, BeastSession]`，兽间并行）
- [x] 召唤 = `MultiAgentRouter.handoff`（返回完整 `LoopResult`）；神兽 loop 独立记忆（`source=beast.*`）+ 共享全局 `ToolProvider`（运行时）+ `SkillLibrary`（注册）
- [x] 自动回归（据 `LoopResult.failed`）+ 手动复位（`/recall` + `recall` CLI + NL）
- [x] `BeastActivator` 三入口：`/summon` 斜杠 + `summon <beast> [task]` CLI + WebUI NL「召唤 X 兽做 Y」
- [x] 契约基线更新：cli-contract-baseline 增补 summon/recall 动词（30 → 32）+ 对应 flag；README.md §2 总览表增 Phase 10 行
- [x] 门禁四件套全绿：ruff check ✓ · ruff format --check ✓ · pyright 0 errors · pytest 全通过（含本 Phase 新增用例）

---

## 7. 测试要点

- [x] 并发多兽：多兽同时显形并行执行（断言兽间并行、互不阻塞）；同兽重复召唤 → 拒绝/先回归（断言兽内串行、无同兽双实例）
- [x] 召唤-回归闭环：召唤 → handoff 返回完整 `LoopResult` → `failed=False` → 自动迁 RECALLED → 记忆封存（`source=beast.*` 不再被主 loop read 命中）
- [x] 手动复位：`/recall <beast>` → 按 beast_id 复位 → RECALLED → 可再次召唤该兽（他兽不受影响）
- [x] 神通路由：神兽 A 的独有神通仅 A 可路由（专属路由语义，runtime deferred）；主 Agent 与神兽共享同一 `ToolProvider` 实例 + 同一 `SkillLibrary` 实例（单测引用同一对象断言）
- [x] 独立记忆：神兽执行产生的 MemoryEntry 全为 `source=beast.<agent_id>`，主记忆（`source=loop`）零污染
- [x] 三入口等价：slash / CLI / NL 三入口最终都落到同一 `BeastSession` 生命周期（参照 pet 三入口断言）
- [x] 错误码：`NO_AGENT_MATCH`（召唤不存在的兽）、同兽重复召唤冲突、回归时无在岗兽等异常路径全覆盖（权威码枚举进 beast-mode interface 错误码节，参照 pet §5）

---

## 8. 提交规范

- **一个 Phase 一个 commit**：beast-registry + beast-mode + innate-skills + summon-activator 四模块 + 契约变更（0034 change + baseline 动词）+ 门禁全绿后单次提交。
- commit message 形如：`feat(phase10): 神兽召唤层 beast-mode/summon（M7）`
- 提交后更新 `README.md` §2 总览表 Phase 10 行状态列为「完成」。
- 契约变更走 openspec 归档（changes/0034），与代码同 commit 或紧邻提交。
