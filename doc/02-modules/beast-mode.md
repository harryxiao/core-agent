# 模块设计：神兽召唤（Beast Mode）

> 对应规格：`doc/openspec/specs/beast-mode/spec.md` ｜ 接口：`doc/03-interfaces/beast-mode-interface.md`
> 定位：**前台重大任务执行层**（pet-mode 后台重复简单任务的对偶），20 个预定义山海经神兽，各持独有神通（L3 Skill），召唤复用编排层 `MultiAgentRouter.handoff` 交接语义，异步并发执行。

---

## 1. 模块定位

beast-mode 为 core-agent 提供前台重大任务执行能力（pet-mode 后台重复简单任务的对偶）：20 个预定义山海经神兽，各持独有神通（L3 Skill），召唤复用编排层 `MultiAgentRouter.handoff` 交接语义，异步并发执行并据 `LoopResult.failed` 自动回归，多实例并发（兽间并行、兽内串行），三入口激活——相当于"人类召唤神兽"，前台接管重大任务、独立记忆、共享主 Agent 通用能力。

本模块是编排层的**前台**重大任务扩展，与 pet-mode 的**后台**重复简单任务正交。

---

## 2. 内部组成

```
BeastMode（前台重大任务执行层）
├── BeastRegistry   只读注册表：20 神兽，agent_id = beast.<拼音>
├── BeastSession    会话句柄：DORMANT → MANIFEST → ACTIVE → RECALLED 四态
├── BeastManager    召唤管理：summon/recall，dict[agent_id, BeastSession] 多实例
├── 独有神通（L3 Skill）  以 Skill 注册进全局 SkillLibrary（神兽 loop **域内路由**，0057）
└── 共享能力（L1）        复用全局 ToolProvider（真实可用）
```

---

## 3. 关键设计

### 3.1 神兽注册表（只读）

- 内置 20 个山海经神兽作为只读注册表：每兽以 `agent_id = beast.<拼音>` 唯一标识，含称号、领域职责、独有神通（`skill_id`）与能力标签（`capabilities`，供 `MultiAgentRouter.match()` 关键词打分路由）。
- 注册表**只读**，区别于 pet.md 的用户自定义角色；运行时写入神兽定义被拒，维持内置 20 兽不变。

### 3.2 会话生命周期（四态）

- 以 `DORMANT → MANIFEST → ACTIVE → RECALLED` 四态管理神兽会话，维护 `dict[agent_id, BeastSession]` 多实例。
- `manifest()`：`DORMANT/RECALLED → MANIFEST`；`activate()`：`MANIFEST → ACTIVE`；`recall()`：`MANIFEST/ACTIVE → RECALLED`。

### 3.3 召唤与 handoff 交接

- 召唤复用编排层 `MultiAgentRouter.handoff` 交接语义，不另造交接机制；三入口统一落 `BeastManager.summon`。
- 同兽重复召唤被拒（`BEAST_ALREADY_MANIFEST`）或先回归该兽——兽内串行，无同兽双实例。

### 3.4 独立子 Agent + 共享能力

- 神兽作为独立子 Agent 运行，**独立记忆**（记忆写入 L2 facts 层），同时**复用主 Agent 通用能力**（L1 工具共享全局 `ToolProvider`）。
- 独有神通（L3 Skill）以 Skill 注册进全局 `SkillLibrary`，由神兽 loop **域内真实路由**（0057）：
  `skill_id` 三节 `beast.<域>.<技能>` 者为专属技能，仅 `domain == "beast.<域>"` 时进候选——他兽域与
  主 Agent 都看不到（路由期作用域强制），与共享能力分层不冲突、且不灌主 prompt。
- **组合根装配**（0057）：`build_runtime` 注册神通并以 `loop_factory` 按兽惰性装配独立 loop +
  注入共享 `MemoryStore`；CLI `summon`/`recall` 经 `build_runtime` 取 `Runtime.beast_activator`。
- **门控**（change `0067`，账本 E10）：`features.beast: false` 时 beast 完全不装配 —— 不建
  `BeastRegistry`、**连 20 神通的注册都不做**（注册即装配期副作用），`Runtime.beast_manager`/
  `beast_activator` 为空、`summon`/`recall` 入口拒绝；主 Agent 技能面与域作用域语义不受影响。

### 3.5 异步并发 + 自动回归

- 多实例并发：可同时显形多兽并行执行（兽间并行、互不阻塞）。
- 异步并发执行，据 `LoopResult.failed` **自动回归**；另有手动召回（Manual Recall）。

### 3.6 三入口激活

- 三入口统一落 `BeastManager.summon`：`/summon` 斜杠命令、`summon <beast> [task]` CLI argv、WebUI 自然语言。

---

## 4. 召唤闭环

```
三入口召唤 ──BeastManager.summon──► BeastSession（DORMANT → MANIFEST → ACTIVE）
执行 ──复用 MultiAgentRouter.handoff──► 前台重大任务（独有神通 L3 Skill + 共享 L1 工具）
任务完成 / 失败 ──LoopResult.failed──► 自动回归（ACTIVE → RECALLED）
手动召回 ──Manual Recall──► RECALLED
```

- 召唤复用编排层交接语义、神通复用 SkillLibrary、通用能力复用 ToolProvider，均回到既有能力闭环，beast 只做"前台重大任务扩展"，不另起炉灶。

---

## 5. 错误处理

| 错误码 | 含义 |
|---|---|
| `BEAST_ALREADY_MANIFEST` | 神兽已在岗，重复召唤被拒 |
| `BEAST_NOT_MANIFEST` | 未显形无法激活 / 无在岗召回无效 |
| `BEAST_MEMORY_WRITE_FAILED` | 神兽记忆写入 L2 facts 层失败 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/beast-mode-interface.md`
- 规格：`doc/openspec/specs/beast-mode/spec.md`
- 复用接口：`orchestration-interface.md`（`MultiAgentRouter.handoff` 交接语义）、`skills`/`skillhub`（`SkillLibrary` 注册神通 + `SkillRouter` 域作用域）、`memory-interface.md`（`MemoryEntry.source`）、`loop-interface.md`（独立 `LoopPlugin`）
- 对偶：`doc/02-modules/pet.md`（后台重复简单任务）
