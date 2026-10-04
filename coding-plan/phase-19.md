# Phase 19 — 排期遗漏账本（Phase 18 收口后的未排期项）

> **定位**：Phase 0–18 已全部落地归档后，本文件是「**已记档、但从未排期**」项的单一账本，供后续按优先级重开。**本文件不含新能力设计**——每项只记「现象 / 根因 / 关闭动作 / 触发前提」，细则仍在各自的 spec / interface / ADR 原文。
> **基线**：`feat/phase0-base` @ `f898768`；669 tests 绿；`openspec validate --all` 29 specs 全绿、**无活跃变更**；最近四个 change `0044`–`0047` 均已归档。
> **走查来源（2026-10-04）**：对 `coding-plan/` 全部 31 份文档 + `doc/` 关键文档（requirements / retro / data-model / adr / 各 interface / specs）做了全量巡读，并对每条自陈「deferred / 未接 / 缺口」反向核对 `src/` 调用点与 `doc/openspec/changes/archive/` → 分三档落账：**明确未做**（E/B/C 类）、**疑似已做未勾**（G 类）、**无法判定**（F 类）。
> **与 `debug-gaps.md` 分工**：`debug-gaps.md` 是「开始真机调试前」的缺口快照（基线 `60d9724` @ 2026-10-01，其 §2.2 多数已修）；本文件收其后的**新增遗留** + 长期未排期项，C 类只引用不重列。
> **规则**：本 Phase 是**记账**不是**里程碑**；重开任一项须按其所属 capability 走常规 SDD 流程（spec delta → 测试 → 实现 → 四门 → 归档），并在此表标注「已关闭」。

---

## 0. 结论

- **无任何一项阻塞核心回路**：669 tests 覆盖的回路（记忆读写/压实/固化/遗忘、技能提炼/路由/迭代、进化四阶段 + HITL + 自动溶解）在生产路径上均已接通。
- **A3（skills 半边）已于 change `0050` 关闭**（技能库/反馈/SOP 样本/灰度态落盘，ADR-0053）；evolution 半边（观察窗口）随 A5。
- **A2+E2（会话维度）已于 change `0048` 关闭**（标识透传 + `compact` 接真 + 按会话读取）；**A1 已于 change `0049` 关闭**（收尾维护节拍 + `memory maintain`）。A 类剩 A3–A9。
- **唯一需要 ADR 裁决的重开项是 B 类（Phase 12 MCP）**；E 类中只有 **E1（constraints 中间件）** 与 **E2（per-session）** 有真实行为影响，其余为「接线缺失」。
- **共同的形态问题**：A/E 两类绝大多数是同一个根因——**运行时零件「进程内、无状态、无驱动」**，即 Phase 13/16 起反复出现的「抽象已落地、缺生产触达点」。A3/A4/A5、E2/E4/E5 全归此。
- **一条值得单独记的形态问题**：`cli-contract-baseline.md` 的**内置工具契约与实现已对不上账**（见 E7）——契约列的 5 个工具在代码里从未存在。

| 类别 | 项数 | 最高优先级 | 是否阻塞调试 |
|---|---|---|---|
| A Phase 18 收口遗留 | 9 | 中 | 否 |
| E 早期 Phase 未闭合项 | 12 | 中（E1/E2） | 否 |
| B Phase 12 MCP（DEFERRED） | 1 | **阻塞级（需 ADR）** | 否（可绕开） |
| C 真实外部后端未接 | ~20 处 | 低 | 否 |
| D 文档与仓库杂项 | 5（3 已关闭） | 无 | 否 |
| F 验收勾选状态 | ✅ 已清尾（6 组核实完毕） | 无 | 否 |
| G 已闭合但未销账 | 7 组 | 无（仅订正文档） | 否 |

---

## 1. 总览（可操作项）

| 编号 | 类别 | 项 | 现象（一句话） | 优先级 | 前置 |
|---|---|---|---|---|---|
| A1 | A | ~~`forget` 无调度器~~ | ✅ 已关闭（change `0049`）：loop 收尾维护节拍触发 `forget` + `core-agent memory maintain` 显式入口 | 中 | — |
| A2 | A | ~~生产 `session_id` 恒空串~~ | ✅ 已关闭（change `0048`）：标识透传至 `remember`，压实/固化/遗忘按会话归组 | 中 | — |
| A3 | A | 进程内无持久化 | 🔶 **skills 半边已闭**（change `0050`：技能库/反馈/SOP 样本/灰度态落盘）；evolution 半边（观察窗口）随 A5 | 中 | 观察窗口随 A5 一并落盘 |
| A4 | A | `EvolutionEngine.confirm` 无生产调用方 | 候选待办队列无驱动面，HITL 门在生产不触达 | 中 | 操作面（CLI/UI）驱动 pending 队列 |
| A5 | A | `observe` 无采样调度器 | 观察期窗口开了，但无人按节拍喂回归样本 | 中 | 采样来源（evaluator 或外部上报） |
| A6 | A | 观察窗口按 target 覆盖 | 重发布即重开窗口、丢旧样本 | 低 | 窗口历史留痕（可选） |
| A7 | A | 语义分未接历史成功率加权 | 排序只用语义分；候选未预筛，miss 轮逐条打分 | 低 | 数据源已就位（`SkillFeedback`） |
| A8 | A | memory「并发压实一致性」无实现 | 规格有此 Requirement，实现未做 | 低 | 出现并发调用方 |
| A9 | A | `context.stage` 语义化残留 | 装配阶段标注不参与事实选择 | 低 | B6 决策的后续 |
| E1 | E | constraints 中间件链从未注入 loop | `_apply_middlewares` 空转，生产零 `middlewares=` | **中高** | 写 constraints→loop 适配层 |
| E2 | E | ~~UI 无每会话 loop/memory~~ | ✅ 已关闭（change `0048`，会话维度部分）：标识透传 + 单店按会话归组 | 中（与 A2 同根） | — |
| E3 | E | 神通（beast）runtime 桥接缺失 | 20 神通从未进运行时 SkillLibrary；handoff 整段短路 | 中 | 先定夺 R4/R5 规格 deferred 是否解除 |
| E4 | E | pet 运行时注入整族缺失 | 跨进程存活 / DI / wake / 三入口四项全缺 | 中 | A3（存储选型） |
| E5 | E | 主 Agent 自动迭代内部模块 | Phase 17 单列后**从未排期** | 低 | 无（能力已前置） |
| E6 | E | 规格 deferred 未解除（context 判定升级等） | 见 §3 E6 | 低 | 规格裁决 |
| E7 | E | 内置工具契约与实现漂移 | 契约列 5 个工具全仓零出现 | 中（契约裁决） | 先定夺契约 |
| E8 | E | CLI 契约基线 §11 未决项 | flag 接线 / secret 校验 / extra 透传等 | 低 | 逐条定夺 |
| E9 | E | 文档层其他未闭合项 | data-model 待补实体、替换性测试锚点等 | 低 | 无 |
| E10 | E | 功能开关无运行时门控 | `build_runtime` 无条件构造全部模块，`is_enabled` 仅存语义 | 低 | 定夺哪些模块可关 |
| E11 | E | LLM 可靠性：连接复用缺失 + 无测试 | 重试/超时/降级/断流有代码无测试；连接复用未实现 | 低 | 无 |
| E12 | E | 崩溃恢复无真实 `kill -9` 用例 | 仅内存 store 模拟的 resume 幂等单测，无子进程重启端到端 | 低 | 无 |
| B1 | B | Phase 12 MCP 安装/传输/安全 | 唯一 DEFERRED Phase，`mcp *` CLI 未接 | **阻塞级** | **先 ADR 裁决 mcp SDK 依赖** |
| C1 | C | 真实外部后端 ~20 处「未接」 | 抽象 + fake 已落地，真后端待接 | 低 | 见 `debug-gaps.md` §2.3 |
| D1 | D | ~~README §2 状态行待核实~~ | ✅ 已关闭：Phase 18 行刷新为 ✅；`17.5` 行改为「🔶 部分完成（遗留见 E3/E4）」 | 无 | — |
| D2 | D | `coding-plan/phase-3-prompt.md` 未跟踪 | 一次性 prompt 残留 | 无 | 删除或 `git add` |
| D3 | D | ~~根目录 `config.yaml` 未跟踪~~ | ✅ 已关闭：`git check-ignore` 原为**零命中**（仅「没 add 过」）→ 已补 `.gitignore` 守卫 | 无 | — |
| D4 | D | `.claude/settings*.json`（部分关闭） | ✅ `settings_deepseek/glm.json` 已 ignore；⚠ `settings.json` **已跟踪且已修改**（非本项目改动）仍待确认归属 | 无 | 确认 settings.json 改动归属 |
| D5 | D | ~~本文件未入 README 索引~~ | ✅ 已关闭：已登记 `README` §1（清单 22 份）+ §2（第 19 行） | 无 | — |

---

## 2. A 类：Phase 18 收口遗留（本 Phase 新报）

### A1 `forget` 无调度器 — ✅ 已关闭（change `0049`）

- **现象**：遗忘（衰减归档）只在 loop 的压实收尾被顺带调用（`src/core/loop/default.py:285`，随 `compact()` @ :281 之后），**没有独立的定时/节拍驱动**；长闲置会话不会自动衰减。
- **根因**：`MemoryStore.forget(*, threshold=...)` 是纯函数式接口，无调度依赖；Phase 18 #5 明确把「定时衰减循环」排除在范围外（需调度器）。`adr.md:513` 同样记为「需调度依赖，另立变更」。
- **关闭动作**：✅ **已由 change `0049-memory-maintenance-cadence` 闭合**（采「节拍闸门 + CLI 显式入口」）：loop 收尾加**维护节拍**（`_MAINTENANCE_INTERVAL_S = 900s` 默认，距上次达间隔才触发一次 `MemoryStore.forget`，失败降级不中断本轮、走 `maintenance_failed` trace）；`forget` 补进 `MemoryStore` Protocol；CLI 新增 `core-agent memory maintain`（装配 runtime → `compact()` + `forget()`，打印归档条数）。**未**引入调度器/常驻后台任务（无真实常驻宿主：`HarnessHost` 在 `entry.py` 每条命令各起一份）。spec delta：`loop`/`memory`/`cli-ops` 三份（29 specs 全绿），测试 679 passed。
- **前置**：无（已完成）。

### A2 生产 `session_id` 恒空串（含 `UIAPILayer.compact` no-op）— ✅ 已关闭（change `0048`）

- **现象**：`MemoryEntry.session_id` 缺省空串（`src/core/memory/protocol.py:32`），而生产侧 `loop/runtime` **从不设置它**（grep 无引用）→ 压实/固化/遗忘全部按单一 `""` 组聚合，「按会话」维度的语义在实际运行中退化为「全局单组」。
- **次生**：`UIAPILayer.compact(session_id)` 仍是 no-op（`src/core/ui/api.py:119-121`，注释自陈「MemoryStore 无显式 compact」），ui spec 无该 Requirement，故未擅自接线。
- **关闭动作**：✅ **已由 change `0048-session-scoped-memory` 闭合**（与 E2 合并做）：loop 三入口收 `session_id` 并写入 L2 条目；`UIAPILayer.compact` 直调 `MemoryStore.compact`；`get_memory` 按会话归属过滤。spec delta：`loop`/`memory`/`ui` 三份（29 specs 全绿），测试 674 passed。
- **前置**：无（原「与 E2 同根，建议合并做」已按此执行）。

### A3 进程内无持久化 — 🔶 skills 半边已闭（change `0050`）

- **现象**（五处同源）：
  - `SkillLibrary` 注册表 —— SOP 提炼入库的技能随进程消失；
  - `SkillFeedback` 统计（`src/core/skills/feedback.py`，模块注释「仅进程内统计（不落盘、不写记忆）」）；
  - 观察期窗口（`src/core/evolution/observation.py:39`「窗口仅进程内（不持久化）」）；
  - SOP 样本累积（`SopExtractor` 组内计数）；
  - `VersionManager` 灰度 / A/B 状态。
- **根因**：Phase 18 有意把持久化排除（先跑通闭环逻辑，再补落盘）；与 Phase 13/16 的「进程内态」同类（E4 的 `PetManager` 同族）。
- **关闭动作**：定存储选型（复用 `FileBackend` 或新 backend）→ 逐类补 spec 持久化 Requirement → 与「依赖与重开顺序」第 3 步的 serve 常驻进程一并落地。
- **关闭进度**：🔶 **skills 半边已由 change `0050-persist-skills-state` 闭合**（存储选型 = 沿用既有 `path: Path | None` + `_load`/`_persist` 惯例，共用 `skills/persist.py` 两个纯函数、单文件 JSON 快照、零第三方依赖，决策见 **ADR-0053**）：`SkillLibrary` / `SkillFeedback` / `SopExtractor` / `VersionManager` 四类各加可选 `path`（缺省纯内存，向后兼容），`build_runtime` 注入 `$CORE_STATE_DIR/{skills,skill-feedback,sop-samples,skill-versions}.json`；spec 补「技能态持久化」Requirement（29 specs 全绿），测试 685 passed。
- **剩余部分**：evolution 侧**观察窗口 / 候选队列**仍进程内 —— 归 **A5**（采样来源落地时一并落盘；窗口不落盘则重启即丢，见 A5 前置）。
- **前置**：无（存储选型已定，ADR-0053）。

### A4 `EvolutionEngine.confirm` 无生产调用方

- **现象**：`confirm(candidate, *, approval=...)` 的三重门（present + `is_approved` + target 匹配）已在 `0046` 实现并被测试覆盖，但**生产侧无调用者**（grep 仅命中 permission gate 的同名方法）→ 维度 2 的 HITL 闸门在生产路径上尚不触达。
- **根因**：候选 `pending` 队列需要「操作面」驱动（谁来发起 confirm、审批单从哪来），Phase 18 #9 有意只做闸门本身。
- **关闭动作**：在操作面（CLI 命令 / UI 审批面板）接 pending 队列 → 构造 `ApprovalTicket` → 调 `confirm`。
- **前置**：审批单来源（`permission` 审批流的发起端）。

### A5 `observe` 无采样调度器

- **现象**：`EvolutionEngine.observe(target, score, *, now=...)` 是采样接缝，但**无生产调用方**（grep 无命中）→ 观察期窗口开而不采，自动溶解在生产侧不会被触发。
- **根因**：Phase 18 #10 明确不把调度器放进引擎（保持引擎纯粹、`now` 可注入以便测试）。
- **关闭动作**：定采样来源——① `Evaluator` 评测轮次回灌；② 外部（用户反馈 / 线上指标）上报。二者均需接线点。
- **前置**：A3（窗口持久化）宜先行，否则重启即丢窗口。

### A6 观察窗口按 target 覆盖

- **现象**：`ObservationRegistry.open` 对同一 target **覆盖旧窗口**（重发布即重开基线、丢旧样本，`observation.py:53-57` 有意为之）。多次发布/回滚循环的窗口历史无留痕。
- **关闭动作**：可选——窗口历史留痕（审计需要时）；否则维持现状并在接口文档标注为已知语义。
- **前置**：无。

### A7 语义分未接历史成功率加权 + 候选未预筛

- **现象**：Phase 18 #7 已记（`coding-plan/phase-18.md:222`）——语义分**只用于排序**，未按历史成功率加权；且 miss 轮对**全部** active/gray 技能逐条打分（K = 技能数），候选未预筛。同一缺口在 `adr.md:656`、`doc/02-modules/skills.md:55` 亦有记。
- **关闭动作**：加权（数据源 `SkillFeedback.success_rate` 现已就位，`0045` 落地）→ 排序分改为语义分 × 成功率因子；预筛可先粗排 Top-N 再语义打分。**与 E6 的「miss 只沉淀不复用」同族，建议合并。**
- **前置**：无（数据源已具备）。

### A8 memory「并发压实一致性」无实现

- **现象**：memory spec 有此 Requirement（`doc/openspec/specs/memory/spec.md:102-105`），实现未做（单线程事件循环、当前无并发调用方，加锁属投机代码）。`adr.md:454` 已记为「先于变更存在的已知缺口」。
- **关闭动作**：出现真实并发调用方时再实现（并补 spec 的并发场景用例）。
- **前置**：并发调用方出现。

### A9 `context.stage` 语义化残留

- **现象**：`ContextPack` 的 `stage` 字段是装配阶段标注，暂不参与事实选择（B6 关闭时的残留项，原并入 A3 清账）。
- **关闭动作**：需要「按阶段差异化选事实」时再语义化。
- **前置**：无。

---

## 3. E 类：早期 Phase 未闭合项（全量走查新增）

> 全部经「文档自陈 + `src/` 调用点 / 归档反向核对」判定为**明确未做**。已闭合但文档未销账的旧记见 §8（G 类）。

### E1 constraints 中间件链从未注入 loop（Phase 13 遗留）

- **现象**：`DefaultLoop` 有完整的中间件链（`loop/default.py:31` `Middleware = Callable[[LoopContext, Action], Action|None]`、`:445 _apply_middlewares`），但**生产侧零注入**——`grep -rn "middlewares=" src/` 仅命中 `tests/test_loop.py:61` → schema 校验 / 熔断 / 压缩三类中间件在生产路径上是**空转能力**。
- **根因**：`constraints.Middleware` 的形状是 `ExecRequest/ExecResponse`，与 loop 的 `(LoopContext, Action) → Action|None` 不同，需适配层；`phase-13.md:91` 标注「随 Phase 14」，但 Phase 14 的 checklist 已全 `[x]` 且**未包含此项** → 掉档。
- **关闭动作**：写 constraints→loop 适配层并在 `build_runtime` 注入；补 `CIRCUIT_OPEN` 短路用例（`phase-2.md:121` 的验收框同属此项）。
- **前置**：无。

### E2 UI 无「每会话独立 loop / memory / tools」（Phase 13 遗留）— ✅ 已关闭（会话维度部分，change `0048`）

- **现象**：`UIAPILayer` 只持**一个共享** `self._loop` / `self._memory`（`ui/api.py:52-53`），`self._sessions` 仅存 mode 字符串（`:61`）→ 多会话共用同一 loop 与同一记忆命名空间。
- **根因**：`phase-13.md:93` 把「serve/repl 运行时装配 + 每会话独立 loop+memory+tools」标为 deferred。
- **关闭动作**：✅ **已按 A2 合并方案闭合（change `0048`）**——采「会话标识透传 + 单店按会话归组」（**不做**每会话独立 `(loop, memory)` 实例：单实例并发服务多会话时标识随调用走、天然不串号，组合根与生命周期不动；见 change `0048` design 决策 1/2）。据此 `run_loop` 透传标识、`get_memory` 按会话过滤、`compact` 接真。
- **前置**：无。

### E3 神通（beast）runtime 桥接缺失（Phase 10 + 17.5 同源）

- **现象**（四项同源）：
  - `register_innate_skills`（`beast/skills.py:35`）**零生产调用者**（仅 `tests/test_beast.py:82`）→ 20 个 `beast.*` 神通从未进过运行时 `SkillLibrary`，`skill_router` 自然永不命中（prompt 的「可用技能」块里不会出现神通）。
  - `BeastManager` 的 handoff 段被**整段跳过**：`entry.py:834` 构造 `BeastActivator()` **未传 router** → `beast/manager.py:52` `router is None` 短路，召唤不走真实交接。
  - `BeastSession` 未注入 loop/memory → `source=beast.<agent_id>` 命名空间隔离失效，`remember` 直接抛 `BEAST_MEMORY_WRITE_FAILED`。
  - `SkillRouter.match` 无 domain 参数（`phase-10.md:86`）→ 专属路由（他兽不可路由）只有语义、无 runtime scoping。
- **规格面**：beast-mode spec 的 `CORE-BEAST-R4/R5`（`doc/openspec/specs/beast-mode/spec.md:54,69,72,82`）**正文显式写着 runtime 调用 deferred** → 这是**规格已知缺口**，不是实现走样（`requirements.md:300-301`、`beast-mode-interface.md:6,144`、`adr.md:338` 一致）。
- **关闭动作**：`build_runtime` 侧注册神通 + 注入 router/loop/memory；随之销掉 C 类里 beast 那几行「未接」。
- **前置**：需先定夺「R4/R5 的 deferred 是否解除」——若解除，改 spec 正文；若维持，本项只做注册不接 runtime。

### E4 pet 运行时注入整族缺失（Phase 17.5 §3.2）

- **现象**（四项同根：`src/core/runtime.py` 零 pet 引用）：
  - **跨进程存活**：`entry.py:768` 每次调用**新建** `PetManager()`，进程退出即丢 → `pet gather` 后新进程 `pet list` 看不见、`pet stop` 失效。
  - **依赖注入**：`entry.py:769` `PetActivator(manager=manager)` **未注入** loop/memory/explorer/safety/notifier → `observe()/prefer()` 偏好落不到 L2。
  - **wake 无触发**：即便唤醒，`PetSession` 默认是 echo 的 `DefaultLoop`（非真实 loop）。
  - **三入口**：`ui/api.py` 零 pet 引用 → WebUI 自然语言激活（`activate_from_nl`）未接。
- **关闭动作**：`build_runtime` 构造 pet 依赖并按需注入 + `PetManager` 落盘。
- **前置**：A3（存储选型）。

### E5 主 Agent 自动迭代内部模块（Phase 17 遗留，从未排期）

- **现象**：`phase-17.md:76` 把「自动化迭代闭环本身（主 Agent 自动迭代内部其余模块）」单列为后续 Phase，**此后无任何 Phase 承接** → 从未排期。
- **关系**：即 Phase 18 §1.3-D 点名的「Voyager 式自动课程（P2 可选，不实现）」。
- **关闭动作**：需要时单独立项（前置能力——技能迭代闭环——已由 `0045` 就位）。
- **前置**：无。

### E6 规格层 deferred 未解除项

| 项 | 出处 | 说明 |
|---|---|---|
| context「上下文自动压实」判定仍是启发式关键词，未升级为 LLM 判定 | `doc/openspec/specs/context/spec.md:45-49`；archive `0041` 已知缺口「判定升级留待 #4」 | 归档记「留待后续」但**从未排期** |
| M3 遗留：技能 miss 只沉淀、不复用 | `adr.md:525` | miss 数据未回流到路由；与 **A7** 同族 |
| memory 并发压实一致性（规格有实现无） | `doc/openspec/specs/memory/spec.md:102-105` | = **A8**，此处仅备案出处 |

### E7 内置工具契约与实现漂移

- **现象**：`cli-contract-baseline.md:260` 的「内置工具 tools.* 9 个」把 `code_run / web_scan / web_execute_js / ask_user / process / memory` 全列为**未实现**。2026-10-04 实测：
  - `tools.code_run` **已实现**（`tools/builtin.py:187`）→ 文档过时；
  - `web_scan` / `web_execute_js` / `ask_user` / `tools.process` / `tools.memory` 在全仓**零出现** → 不是「未实现」，而是「**从未存在**」；
  - 实际实现集：`file_read` / `file_write` / `file_patch` / `code_run` / `web_fetch`（`builtin.py`）+ `install` / `uninstall` / `list`（`install_tools.py`）→ 与契约基线的**名字与集合都已对不上账**。
- **关闭动作**：**先定夺契约**——若这 5 个仍是承诺项，须补规格 + 实现；否则订正 `cli-contract-baseline.md`（及其来源 spec）对账。
- **前置**：契约裁决（可能牵动 spec）。

### E8 CLI 契约基线 §11 未决项（契约层待定夺）

来源 `cli-contract-baseline.md` §11（其中「config set 写回 + revalidate」已闭环）：

- `--llm-*` / `--im-*` flag 是否接线（当时三模入口未实现，大概率仅设计态）→ 现状需复核（`--llm.embedding-model` 等已在 `0040` 落地，说明 flag 面已部分接通）。
- `permission-mode` 枚举成员未定（与 **E1** 的权限中间件相关）。
- **secret 校验不对称**：`secret_ref` 不强制非空/可解析 → 「空 secret 也能过校验」。
- `features` 无固定清单 → `--feature` 的补全/帮助无法静态枚举。
- `extra` 透传无校验 → 拼错的配置段名被静默吞进 `extra`，不报「未知配置键」。
- `streamable-http` transport 是否支持（= **B1** 子项）。
- **关闭动作**：逐条定夺后或改契约、或补实现。

### E9 其他文档层的未闭合项

| 项 | 出处 | 处置 |
|---|---|---|
| `data-model.md` 待补实体 `Session` / `ExecContext` / `ExecRequest` / `ExecResponse`（「字段以编码阶段落地为准」） | `doc/01-architecture/data-model.md:130-138` | 反过来说明**从未回填** → 文档缺口，编码阶段已过，须补 |
| rag / mcp / git 的「替换 X→零改动」测试锚点待补 | `adr.md:329` | ADT 可替换性**无守护测试** |
| 远程制品仓库与凭证 / market-registry 远端服务 | `adr.md:293,302` | 真后端类 → 归 **C** |
| `doc/00-product/retrospective.md:86-90`「实现落地（src=0 是唯一短板）」 | retrospective | **已过时**（当时 `src/` 为空骨架）→ 属 D 类文档订正 |

### E10 功能开关无运行时门控（Phase 0 验收未达成）

- **现象**：`phase-0.md:32` 要求「功能开关缺省关闭：未启用的模块**完全不初始化**（不 import 副作用、不注册）」。实测：`ConfigManager.is_enabled` 的缺省 off 语义已实现并测试（`tests/test_configuration.py:85`），但 `runtime.py` 的 `build_runtime` **无条件构造全部模块**——无 `is_enabled` 门控、无「未启用则不构造/不注册」的证据。
- **根因**：Phase 0 只交付了配置侧开关语义，运行时侧门控从未接线（Phase 13 组合根建立时也未补）。
- **关闭动作**：`build_runtime` 按 `is_enabled` 门控各模块构造；补「关闭时不构造」断言用例。
- **前置**：需先定夺「哪些模块允许关闭」（部分模块是核心回路必需，强行可关会破环）。

### E11 LLM 可靠性：连接复用缺失 + 重试/超时/降级/断流无测试（Phase 1 验收未达成）

- **现象**：`phase-1.md:30` 要求「失败自动重试、超时控制、服务降级、**连接复用**、流式断流处理」。实测：`stdlib_provider.py:81-122` 已有重试/退避/超时/降级/断流**代码**，但**无任何对应测试**；且「连接复用」**未实现**——`urllib` 每请求新建连接，无 keepalive / 连接池。
- **根因**：核心零三方依赖红线下的 stdlib 手写 provider，可靠性面只做到"能跑"，未做连接复用（需 `http.client` 长连接或自建池）。
- **关闭动作**：① 补可靠性用例（重试次数/退避、超时、降级、断流半包）；② 连接复用单独立项（涉及自建池，属实现变更，须 spec delta）。
- **前置**：无（① 可随时做；② 需定夺是否值得为 stdlib provider 自建连接池）。

---

### E12 崩溃恢复无真实 `kill -9` 用例（Phase 2 验收部分未达成）

- **现象**：`phase-2.md:122` 要求「崩溃恢复测试：`kill -9` 后重启，`resume()` 恢复且无重复副作用」。现有覆盖是**内存 store 模拟**的 resume 幂等单测（`tests/test_durability.py:55,67`），**无真实进程 `kill -9` + 子进程重启**的端到端用例。
- **根因**：durability 用例跑在进程内（快而稳），真实崩溃语义（半写日志、store 未 flush、锁残留）从未被验证。
- **关闭动作**：补 subprocess 用例——子进程写一半被 `SIGKILL` → 重启 → `resume()` 恢复且副作用不重复。
- **前置**：无（低成本，可顺手在 E1 之前做）。

---

## 4. B 类：Phase 12 MCP（DEFERRED，唯一阻塞级重开项）

- **范围**：transport 生产实现（stdio/http）、client 安装分流、消费侧安全接线（本地 stdio 过 `SandboxManager`、远端 http 走出站白名单、不可逆工具走确认门）。
- **阻塞原因**：mcp SDK 离线不可装 + 「核心零第三方运行时依赖红线」须 ADR 裁决。
- **现状（已核到行）**：`build_transport` 仍占位抛 `MCP_CONNECT_FAILED`（`src/core/mcp/transport.py:117`）；`MCPClient.add` 硬编码 http（`src/core/mcp/client.py:138`）；CLI `mcp serve/list/add/remove` 未接（落 stub）；`mcp remove` 的资源释放随传输实现一并做。
- **关闭动作**：**先 ADR**（评估 mcp SDK 依赖定位）→ 落 `0033` ADDED delta → 接线。
- **参考**：`coding-plan/phase-12.md`（`:79-86` 为待办清单）；归档 `doc/openspec/changes/archive/2026-09-29-0033-mcp-install-security-DEFERRED/`。

---

## 5. C 类：真实外部后端未接（低，不挡核心回路调试）

抽象 + 可注入 fake 已落地，真后端待接（约 20 处「未接」标记）。**明细见 `coding-plan/debug-gaps.md` §2.3**，涉及模块：`git` / `im` / `mcp transport` / `ui`（TTS、Tauri 桌面壳）/ `observability`（OTel）/ `ci_cd` / `plugin_registry` / `skillhub` / `pet`·`beast`。

本轮走查**新增的具名条目**（原先只记「约 20 处」，现落到行）：

| 模块 | 具名项 | 出处 |
|---|---|---|
| ui | 流式 TTS 播报后端（barge-in 语音输出仅有抽象） | `phase-7.md:34-35`、`ui-interface.md:19`、`ui/api.py:106` |
| ui | 桌面入口 Tauri 壳 + sidecar（`desktop_bridge.py:34` 直接 raise） | `phase-9.md:21` |
| ui | Web 前端独立托管（`web_bridge.py` 仅设计、无前端实现） | `phase-7.md:105` |
| im | 真实平台 SDK（Telegram / 钉钉 / 企微）+ 退避重连 | `phase-7.md:96,106`、`im/provider.py:4` |
| git | 真实 git 后端 + 断线重试/连接释放 | `phase-7.md:107`、`git/backend.py:51` |
| pet | 探索工具真实执行（R11） | `phase-8.md:84`、`pet/explore/explorer.py:30` |
| pet | 真实通知通道（R12/R13，越界暂停后通知主人） | `phase-8.md:85-86`、`pet/notify/notifier.py:4` |
| pet | 微任务 git 写回（R14） | `phase-8.md:87`、`pet/microtask/microtask.py:4` |
| cli | `skill search` 恒空（`SkillHubClient` 存在但未接线到 CLI） | `debug-gaps.md:51`、`entry.py:426-427,539-550` |
| ci_cd | 门禁执行器 + 真实制品仓库 | `adr.md:293`、`debug-gaps.md:49` |
| plugin_registry | market-registry 远端服务 + 多源 resolver + git 版本锁定 | `adr.md:302` |

> **立场不变**：抽象不锁选型，待有真实选型需求时逐项接线。注意其中 **pet·beast 三行**同时是运行时的**接线**缺口（E3/E4），不只是后端缺口。

---

## 6. D 类：文档与仓库杂项（无阻塞）

- **D1** ✅ 已关闭：README §2 Phase 18 行刷新为 ✅ 完成；`17.5` 行改为「🔶 部分完成（遗留见 `phase-19.md` E3/E4）」（memory 召回注入已由 `0038` 闭，pet/beast 运行时注入未做）。
- **D2** `coding-plan/phase-3-prompt.md` 未跟踪（一次性 prompt 残留）→ 删除或明确 `git add`。
- **D3** ✅ 已关闭：核查发现 `git check-ignore` 对 `config.yaml` **零命中**（未被忽略，只是没 `git add`）→ 一次 `git add -A` 即会入库真实端点载体。已在 `.gitignore` 补 `/config.yaml` 守卫（密钥红线）。
- **D4** 🔶 部分关闭：`settings_deepseek.json` / `settings_glm.json` 已加入 `.gitignore`；**`settings.json` 例外**——它**已被跟踪**且有未提交改动（非本项目代码改动），gitignore 对已跟踪文件无效 → 归属仍需人工确认（保留此项）。
- **D5** ✅ 已关闭：本文件已登记进 README §1（文档清单 22 份）与 §2（Phase 总览第 19 行）。

---

## 7. F 类：验收勾选核实结果（✅ 已清尾）

> **本类已关闭**：6 组陈旧清单逐框对照 `tests/`（行号级）与 `doc/openspec/changes/archive/` 核实，**有证据才勾**；确未做的框**不勾**，转 A/E/B 类并在原文档就地标注去向。

| 文件 | 规模 | 核实结果（原文档已按此改） | 未做项去向 |
|---|---|---|---|
| `phase-0.md` | 14 框 | **13 已勾**：`:28-31`、`:33-36` 验收项与 `:127-131` 架构/压测/脱敏/降级均有 `tests/` 覆盖（`test_architecture.py:233`、`test_observability`/`test_configuration`/`test_permission` 等） | `:32` 功能开关门控 → **E10** |
| `phase-1.md` | 14 框 | **12 已勾**（`test_llm_provider` / `test_memory` / `test_tool_use` / `test_plugin_registry.py:69,83` 等） | `:30` LLM 可靠性 → **E11**；`:35` 并发压实一致 → **A8** |
| `phase-2.md` | 10 框 | **7 已勾**：durability `test_durability.py:37,105`、permission `test_permission.py:50,195,232`、架构 `test_architecture.py:268`、熔断 `test_constraints.py:75`、MCP 隔离 `test_mcp.py:117,160`、时间旅行与沙箱同族用例 | `:28` constraints 中间件 → **E1**；`:31` mcp → **B1**；`:122` 真机崩溃恢复 → **E12** |
| `phase-2.5.md` | 6 框 | **6 全勾**（`test_installable.py:49`、`test_cli_ops.py:67`、`test_mcp.py:220`、`test_permission.py:252`；归档 `2026-09-27-0028/0029`） | — |
| `phase-17.5.md` | 8 框 | **3 已勾**（memory 召回注入等，由 change `0038` 闭合） | 其余 5 框 → **E3/E4** |
| `cli-contract-baseline.md` §11 | 6 条（非复选框） | 逐条定性（1 条已在代码中闭环） | → **E8** |

**合计**：52 个复选框 → **41 已勾销**、11 项转出（归入 E1/E3/E4/E8/E10/E11/E12/A8/B1 各一节）。**F 类无剩余待办。**

---

## 8. G 类：已闭合但文档未销账（仅需订正，无实现工作）

> 走查中确认「后来已被后续 Phase/change 闭合，但原文档仍是 deferred 措辞」——**无需实现工作**，只需订正原文档（勾选 / 删注 / 改状态）。

| 原记 | 已由何闭合 | 证据 |
|---|---|---|
| judgment 三决策点 DI（loop choice / memory score / permission noul） | Phase 13 | `runtime.py:182-241` 构造并注入 `DecisionRouter`/`Compactor`/`Guardrail`/`SkillMatcher`；`phase-13.md:21` 自陈「拆掉 Phase 11 的 deferred 标记」 |
| `VersionManager` 已存在但未接 runtime | change `0045` | `skills/iteration.py` 的 `SkillIterator` 现即其生产调用方（灰度 + A/B） |
| FastAPI HTTP/SSE 真实传输未接 | Phase 9 | `phase-9.md:103` + `src/core/ui/fastapi_serve.py` |
| serve / REPL 落地「实现 deferred」 | Phase 9 内 | `phase-9.md:74` 注记 vs `:103-104` 实际落地 |
| 端到端「真实模型调用待联调」 | Phase 13 | runtime 组合根 `loop.reason` 接 LLM provider |
| 架构审计三层缺口 M1（InstallableAsset）/M3（install 工具）/M4（cli-ops）/M5（CLI 覆盖层）/M6（permission-mode） | 后续 Phases | `plugin_registry/installable.py`、`tools/install_tools.py`、`entry.py` 子命令、`runtime.py` config.permission_mode；**除 mcp 传输外均已补齐** |
| phase-17.5 memory 召回注入（:69/:70/:123）+ 兽间并行/串行/拒绝（:93） | change `0038` / 既有实现 | 归档 `2026-10-04-0038-task-keyed-memory-recall`；`beast/manager.py` + `tests/test_beast.py` |

**销账（2026-10-04）**：上表 7 组**均已订正原文档**——`phase-11.md:84/95`（勾选 + 注明由 Phase 13 闭合，证据 `runtime.py:182-241`、`tests/test_phase13.py:83,500,508,515`）、`adr.md:554`（`VersionManager` → 0045 闭合）、`phase-7.md:95`（FastAPI/SSE → Phase 9）、`phase-9.md:74`（serve/REPL → 已落地）、`phase-3.md:35`（真实模型调用 → Phase 13）、`phase-17.5.md:69/70/93/123/126`（0038 闭合 + 已测）、`architecture-adjustment-plan.md` 与 `architecture-audit.md`（头部加销账注记，M1/M3/M4/M5/M6 已补齐、仅 M2 的 mcp 随 B1）。

**另有一条属于「真机动作」而非缺口**：`debug-gaps.md` §3 记「活 LLM 端点冒烟从未做过」。走查结论：真端点**实际被打到过**（`9db8b3a` 2026-10-01 修嵌套事件循环冒烟失败、`4c8b869` 2026-10-02 修端点 400 拒绝），但**仍无一次成功走完活 LLM 全回路的书面记录**（`5cd3552` 是记忆 embedding 检索冒烟，非 loop）。→ 建议作为**待执行动作**而非缺口对待。

---

## 9. 依赖与建议重开顺序

1. **D + F + G 清尾**（无依赖、低成本）：G 类订正 deferred 措辞 + F 类逐项勾销/定性 + README 同步 —— 使账本自身可达且不误导。 ✅ **已完成**（G 类 7 组订正；D1/D3/D5 关闭、D4 部分；F 类 6 组核实：41 框勾销 / 11 项转出 E·A·B；README 已同步）。
2. **A2 + E2 合并做**（同一根因）：会话标识透传 + 每会话独立 loop/memory + `UIAPILayer.compact` 接真。 ✅ **已完成**（change `0048-session-scoped-memory`：标识透传 + `compact` 接真 + `get_memory` 按会话过滤；**未采**每会话独立实例，理由见该 change design 决策 1/2）。
3. **A1**（记忆驱动侧）：遗忘节拍。宜在 A2 之后（会话维度不生效时，衰减分组也是错的）。 ✅ **已完成**（change `0049-memory-maintenance-cadence`：loop 收尾维护节拍 + `memory maintain` CLI）。
4. **A3 → A5 → A4 / E4**（进程内态 → 持久化 → 驱动面）：持久化先行，观察窗口 / pending 队列 / `PetManager` 才有意义；建议与「serve 常驻进程」一并做（`debug-gaps.md` §4 已提）。 🔶 **A3 skills 半边已完成**（change `0050`：技能库/反馈/SOP 样本/灰度态落盘 + ADR-0053）；**下一步 A3 evolution 半边 + A5**（观察窗口落盘 + 采样来源）。
5. **B1**（独立轨）：随时可先写重开 ADR（不需代码），是唯一可并行推进的阻塞级项。
6. **E1 + E7 + E8**（契约与中间件）：E1 有真实行为影响（熔断/校验空转），建议提前；E7/E8 需先定夺契约再动。
7. **E3 / E6**（规格裁决）：先定夺 beast R4/R5 与 context 判定升级是否解除 deferred，再决定是否接 runtime。
8. **A7 + E6（miss 复用）**（低优先，同族）：数据源已就位，可一并做。
9. **A6 / A8 / A9 / E5 / E9 / C 类**：随需。
10. **真机动作**：活 LLM 全回路冒烟（§8 末）。

---

## 10. 关闭判据

任一项标「已关闭」须同时满足：

1. 按所属 capability 走完 SDD：spec delta（或明确「规格中性」的判据）→ 测试先行 → 实现 → 四门全绿（ruff check / ruff format / pyright / pytest）；
2. `openspec validate --all` 全绿，change 已归档（本仓库 `openspec archive` 失败，须手动合并 delta + `mv`，见归档惯例）；
3. 本文件对应行更新为「✅ 已关闭（change id / commit）」；
4. 若改变了对外语义，同步 `doc/03-interfaces/*-interface.md` 及相应 ADR。
