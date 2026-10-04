# Phase 19 — 排期遗漏账本（Phase 18 收口后的未排期项）

> **定位**：Phase 0–18 已全部落地归档后，本文件是「**已记档、但从未排期**」项的单一账本，供后续按优先级重开。**本文件不含新能力设计**——每项只记「现象 / 根因 / 关闭动作 / 触发前提」，细则仍在各自的 spec / interface / ADR 原文。
> **基线**：`feat/phase0-base` @ `f898768`；669 tests 绿；`openspec validate --all` 29 specs 全绿、**无活跃变更**；最近四个 change `0044`–`0047` 均已归档。
> **走查来源（2026-10-04）**：对 `coding-plan/` 全部 31 份文档 + `doc/` 关键文档（requirements / retro / data-model / adr / 各 interface / specs）做了全量巡读，并对每条自陈「deferred / 未接 / 缺口」反向核对 `src/` 调用点与 `doc/openspec/changes/archive/` → 分三档落账：**明确未做**（E/B/C 类）、**疑似已做未勾**（G 类）、**无法判定**（F 类）。
> **与 `debug-gaps.md` 分工**：`debug-gaps.md` 是「开始真机调试前」的缺口快照（基线 `60d9724` @ 2026-10-01，其 §2.2 多数已修）；本文件收其后的**新增遗留** + 长期未排期项，C 类只引用不重列。
> **规则**：本 Phase 是**记账**不是**里程碑**；重开任一项须按其所属 capability 走常规 SDD 流程（spec delta → 测试 → 实现 → 四门 → 归档），并在此表标注「已关闭」。

---

## 0. 结论

- **无任何一项阻塞核心回路**：669 tests 覆盖的回路（记忆读写/压实/固化/遗忘、技能提炼/路由/迭代、进化四阶段 + HITL + 自动溶解）在生产路径上均已接通。
- **A3 全闭（skills 半边 change `0050`，evolution 半边 change `0051`）**；**A5 + 本次新增发现 A10 已于 change `0051` 关闭**（冷路径驱动面 = loop 节拍 + `evolve run`；观察窗口落盘 + 批次成功率采样；ADR-0054）。
- **A2+E2（会话维度）已于 change `0048` 关闭**（标识透传 + `compact` 接真 + 按会话读取）；**A1 已于 change `0049` 关闭**（收尾维护节拍 + `memory maintain`）。A 类剩 A8 / A9 / A11（**A6 已随 change `0063` 关闭**）。
- **唯一需要 ADR 裁决的重开项是 B 类（Phase 12 MCP）** —— **B1 的 client 侧（stdio 传输 + 安装分流 + 消费侧安全接线）已于 change `0054` 关闭**（ADR-0057），余 http 会话 / 服务端 stdio / CLI 接线 / 白名单配置 4 行后续；E 类中曾判定有真实行为影响的 **E1（constraints 熔断）** 与 **E2（per-session）** **均已关闭**（E2 → change `0048`；E1 → change `0052`），其余为「接线缺失」。
- **A4 已于 change `0055` 关闭**（候选 `candidate_id` 稳定身份 + 门禁/评测随候选落盘为一条记录 + `core-agent evolve pending|confirm|reject` 操作面；high 风险候选由操作面签发审批单；ADR-0058）。
- **E1 已于 change `0052` 关闭**（constraints 熔断按 `tool_id` 接入 loop：结果侧观察者 + 按工具熔断 + 只计执行失败；ADR-0055）；核销时一并**订正**了账本原「校验空转」的说法（校验实由工具层承担）。
- **E7（契约基线漂移）+ E8（配置校验三处缺口）已于 change `0056` 关闭**（密钥引用同口径 + `permission.mode` 枚举校验 + 基线文档订正；ADR-0059），E8 第 5 条转出为 **E18**。
- **A6（观察窗口覆盖语义）+ E13（`parse_output` 零调用方判定）+ E19（durability 过度承诺）已于 change `0063` 关闭**（纯文档、规格中性：已知语义登记 + 「有意不接线」判定 + 过度承诺订正）；E19 的裁决 = **订正文档承认现状**（该承诺规格里从来没有，静默降级会掩盖磁盘满）。
- **共同的形态问题**：A/E 两类绝大多数是同一个根因——**运行时零件「进程内、无状态、无驱动」**，即 Phase 13/16 起反复出现的「抽象已落地、缺生产触达点」。A3/A5、E2/E4/E5 全归此（A4 已随 change `0055` 关闭、E3 已随 change `0057` 关闭）。
- **一条值得单独记的形态问题**：`cli-contract-baseline.md` 的**内置工具契约与实现已对不上账**（见 E7）——契约列的 5 个工具在代码里从未存在。

| 类别 | 项数 | 最高优先级 | 是否阻塞调试 |
|---|---|---|---|
| A Phase 18 收口遗留 | 11 | 中 | 否 |
| E 早期 Phase 未闭合项 | 18 | 中 | 否 |
| B Phase 12 MCP（部分关闭） | 5 | 低（B1 client 侧已闭） | 否（可绕开） |
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
| A3 | A | ~~进程内无持久化~~ | ✅ 已关闭（change `0050` + `0051`）：技能库/反馈/SOP 样本/灰度态 + 观察窗口全落盘 | 中 | — |
| A4 | A | ~~`EvolutionEngine.confirm` 无生产调用方~~ | ✅ 已关闭（change `0055`）：候选稳定身份 + 门禁/评测随候选落盘 + `evolve pending\|confirm\|reject` 操作面签发审批单 | 中 | — |
| A5 | A | ~~`observe` 无采样调度器~~ | ✅ 已关闭（change `0051`）：冷路径批次成功率按 `plugin_id` 归因采样 | 中 | — |
| A6 | A | ~~观察窗口按 target 覆盖~~ | ✅ 已关闭（change `0063`）：覆盖是**有意语义**（窗口判「当前那次发布」是否回归，跨版本混池会使基线失义），已登记 `evolution-interface.md` §3.1；历史留痕待审计需求出现再开 | 低 | — |
| A7 | A | ~~语义分未接历史成功率加权~~ | ✅ 已关闭（change `0058`）：排序分 = 基础分 × 历史成功率因子（冷启动中性 + 下限 0.5，判定仍用基础分）；**候选预筛**转出为 **A11** | 低 | — |
| A8 | A | memory「并发压实一致性」无实现 | 规格有此 Requirement，实现未做 | 低 | 出现并发调用方 |
| A9 | A | `context.stage` 语义化残留 | 装配阶段标注不参与事实选择 | 低 | B6 决策的后续 |
| A10 | A | ~~进化冷路径无驱动面~~ | ✅ 已关闭（change `0051`）：loop 收尾节拍 + `core-agent evolve run` | 中高 | — |
| A11 | A | 语义兜底候选未预筛（成本随库规模线性） | `SkillMatcher.score` **逐候选一次决策调用** → miss 轮模型调用数 O(N)；预筛需**比词法更粗**的排序信号（字符 n-gram 等，另带 N/阈值两个常量） | 低 | 库规模/打分成本成事实约束，或先定夺「打分器改批量单调用」 |
| E1 | E | ~~constraints 中间件链从未注入 loop~~ | ✅ 已关闭（change `0052`）：按 `tool_id` 熔断接入 loop（动作前链 + 结果侧观察者）；**校验实由工具层承担**（原「校验空转」订正） | 中高 | — |
| E2 | E | ~~UI 无每会话 loop/memory~~ | ✅ 已关闭（change `0048`，会话维度部分）：标识透传 + 单店按会话归组 | 中（与 A2 同根） | — |
| E3 | E | ~~神通（beast）runtime 桥接缺失~~ | ✅ 已关闭（change `0057`）：20 神通注册进全局技能库 + 专属路由**作用域强制**（`SkillRouter.match(domain=)`）+ 按兽装配 loop/共享记忆注入 + CLI `summon/recall` 走组合根 | 中 | — |
| E4 | E | ~~pet 运行时注入整族缺失~~ | ✅ 已关闭（change `0053`）：pet 纳入组合根（真 loop/共享记忆注入）+ 注册表落盘 + WebUI NL 入口 | 中 | — |
| E5 | E | 主 Agent 自动迭代内部模块 | Phase 17 单列后**从未排期** | 低 | 无（能力已前置） |
| E6 | E | ~~规格 deferred 未解除（context 判定升级等）~~ | ✅ 已关闭：context 压实「留待后续」已由 change `0041` 规格订正（启发式为**有意降级路径**，LLM 提炼归 memory 通道）；余两项转 **A7 / A8** | 低 | — |
| E7 | E | ~~内置工具契约与实现漂移~~ | ✅ 已关闭（change `0056`）：裁决「规格为准」——契约列 5 个工具**从未存在**（非承诺项），订正 `cli-contract-baseline.md` §10 | 中（契约裁决） | — |
| E8 | E | ~~CLI 契约基线 §11 未决项~~ | ✅ 已关闭（change `0056`）：7 条逐条定性；`im.secret`/`judgment.api_key` 校验对称化 + `permission.mode` 枚举校验（余 `extra` 未知键 → **E18**） | 低 | — |
| E9 | E | ~~文档层其他未闭合项~~ | ✅ 已关闭（change `0061`）：`data-model.md` §4 四实体按**源码回填** + rag/mcp/git 三条替换性锚点登记为 `TC-RAG-10` / `TC-MCP-06` / `TC-GIT-11`（锚点测试本已存在，补的是追踪号）+ retrospective/ADR 日期补记；余两项（远程制品仓库、market-registry）归 **C 类**（§5 已具名） | 低 | — |
| E10 | E | 功能开关无运行时门控 | `build_runtime` 无条件构造全部模块，`is_enabled` 仅存语义 | 低 | 定夺哪些模块可关 |
| E11 | E | LLM 可靠性：连接复用缺失 + 无测试 | 🔶 **部分关闭（change `0060`）**：重试/超时/降级/断流**用例已补**（9 例，`src/` 零改动 —— 实现本就正确，缺的是验证）；**余**连接复用未实现（`urllib` 每请求新建连接）→ **E11②** | 低 | 无 |
| E12 | E | ~~崩溃恢复无真实 `kill -9` 用例~~ | ✅ 已关闭（change `0062`）：真子进程 `SIGKILL` 端到端 + **修持久化非原子写入缺陷**（`write_text` 先截断 → 半写即整体丢失 → 改 tmp + `os.replace` 原子提交 / 规格 delta） | 低 | — |
| E18 | E | `extra` 未知配置键无校验 | 拼错的段名静默吞进 `extra`，不报「未知配置键」（E8 第 5 条转出，change `0056` 裁决未收紧） | 低 | 定夺「仅告警」vs「硬拒」 |
| E19 | E | ~~durability 文档承诺的「持久化故障降级」未实现~~ | ✅ 已关闭（change `0063`）：**用户裁决订正文档承认现状**——该承诺**规格里从来没有**（只在模块文档），静默降级会掩盖磁盘满；`durability.md` §5 改写为「不静默降级，上层断点续跑承接」 | 低 | — |
| E13 | E | ~~`Validator.parse_output` 零生产调用方~~ | ✅ 已关闭（change `0063`）：规格「输出解析失败不执行」的生产实现是**动作感知**的 `LLMPlanner._parse`（失败 → 终止 Action：工具不执行 + 原因回灌下一轮）；`parse_output` **无动作语义、有意不接线**（非遗漏），补追踪号 `TC-CONS-05` | 低 | — |
| E14 | E | ~~校验码重复~~ | ✅ 已关闭（change `0059`）：`_matches_type` 双拷贝删除，工具层调用前校验**委托** `Validator.validate_input`（单一真源，行为中性 / ADR-0062） | 低 | — |
| E15 | E | 熔断阈值/冷却不可配 | 适配层用类默认（5 / 30s），`configuration/` 无 constraints 段 | 低 | E10 配置门控 |
| E16 | E | `AsyncNotifier` 无 channel | pet 通知仅入队，`flush()` 投递未接；IM 通道（`im`）为依赖 | 低 | IM 通知通道 |
| E17 | E | pet 无后台 daemon | 宠物仍显式 `wake()`，无自建调度线程 | 低 | 无（daemon 化属另一变更） |
| B1 | B | Phase 12 MCP 安装/传输/安全（client 侧） | 🔶 **部分关闭（change `0054`）**：stdio 传输 + `add` 分流 + 沙箱/白名单/确认门接线 + 组合根装配已落地（ADR-0057）；**余** http 会话 → B2、服务端 stdio → B3、CLI 接线 → B4、白名单配置 → B5 | 低 | 无 |
| B2 | B | 远端 http/streamable-http 会话 | `build_http_transport` 仅落地「白名单守卫 + SDK 缺失降级 + 会话待接入报错」；`Mcp-Session-Id`/SSE/headers 未实现 | 低 | mcp SDK（离线不可装） |
| B3 | B | `MCPServer.serve` stdio 事件循环 | 服务端方向（本机作 MCP server 暴露工具）未实现；client 方向 `0054` 已通 | 低 | 无 |
| B4 | B | `mcp` CLI 接线 + 端点注册表落盘 | CLI `mcp serve/list/add/remove` 仍 stub；`MCPClient.add`/`InstallDispatcher` 已通（`0054`），缺 CLI→installer 与端点持久化 | 低 | 无 |
| B5 | B | 出站白名单不可配 | `SandboxPolicy(host_allowlist)` 可注入且默认拒绝，但 `configuration/` 无 `permission.sandbox.host_allowlist` 段 | 低 | E10 配置门控 |
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

### A3 进程内无持久化 — ✅ 已关闭（change `0050` + `0051`）

- **现象**（五处同源）：
  - `SkillLibrary` 注册表 —— SOP 提炼入库的技能随进程消失；
  - `SkillFeedback` 统计（`src/core/skills/feedback.py`，模块注释「仅进程内统计（不落盘、不写记忆）」）；
  - 观察期窗口（`src/core/evolution/observation.py:39`「窗口仅进程内（不持久化）」）；
  - SOP 样本累积（`SopExtractor` 组内计数）；
  - `VersionManager` 灰度 / A/B 状态。
- **根因**：Phase 18 有意把持久化排除（先跑通闭环逻辑，再补落盘）；与 Phase 13/16 的「进程内态」同类（E4 的 `PetManager` 同族）。
- **关闭动作**：定存储选型（复用 `FileBackend` 或新 backend）→ 逐类补 spec 持久化 Requirement → 与「依赖与重开顺序」第 3 步的 serve 常驻进程一并落地。
- **关闭进度**：🔶 **skills 半边已由 change `0050-persist-skills-state` 闭合**（存储选型 = 沿用既有 `path: Path | None` + `_load`/`_persist` 惯例，共用 `skills/persist.py` 两个纯函数、单文件 JSON 快照、零第三方依赖，决策见 **ADR-0053**）：`SkillLibrary` / `SkillFeedback` / `SopExtractor` / `VersionManager` 四类各加可选 `path`（缺省纯内存，向后兼容），`build_runtime` 注入 `$CORE_STATE_DIR/{skills,skill-feedback,sop-samples,skill-versions}.json`；spec 补「技能态持久化」Requirement（29 specs 全绿），测试 685 passed。
- **evolution 半边闭合**：🔶 **已由 change `0051-evolution-cold-path` 闭合** —— `ObservationRegistry` 加可选
  `path`，落盘 `{target: {baseline, samples, frozen_until}}`（**冻结截止一并落盘**，否则重启即解冻、冷却期形同虚设），
  缺省纯内存；`build_runtime` 注入 `$CORE_STATE_DIR/observations.json`。两个纯函数 `read_state` / `write_state`
  同时从中立化提升到 `src/core/persistence.py`（技能态与进化态共用，决策见 **ADR-0054**）。
- **剩余**：候选 `pending` 队列曾仍进程内 —— 属 A4，已随 change `0055` 的「队列落盘 + 操作面」一并关闭（非本项缺口）。
- **前置**：无（存储选型已定，ADR-0053 / ADR-0054）。

### A4 `EvolutionEngine.confirm` 无生产调用方 — ✅ 已关闭（change `0055`）

- **现象**：`confirm(candidate, *, approval=...)` 的三重门（present + `is_approved` + target 匹配）已在 `0046` 实现并被测试覆盖，但**生产侧无调用者**（grep 仅命中 permission gate 的同名方法）→ 维度 2 的 HITL 闸门在生产路径上尚不触达。
- **根因**：候选 `pending` 队列需要「操作面」驱动（谁来发起 confirm、审批单从哪来），Phase 18 #9 有意只做闸门本身。
- **关闭动作（方案较原记扩围，缘由如下）**：原记「在操作面接 pending 队列 → 构造 `ApprovalTicket` → 调 `confirm`」在**每条命令各起一份装配**的 CLI 上不可行，且跨进程**根本不可能**——队列态与门禁/评测结论原以 `id(candidate)` 为键存于引擎私有字典，`Proposer._generation` 又是进程内自增（两次 `evolve run` 会产出同 `generation`/同 target 的两个候选）。故一并落地三件事：
  1. **稳定身份**：`GenerationCandidate.candidate_id`（UUID 前 12 位 hex，构造即固化），门禁/评测检索改按 `candidate_id`；
  2. **队列落盘**：`PendingQueue` 把「候选 + `GateReport` + `EvalReport`」作为**一条记录**整体落盘（`$CORE_STATE_DIR/evolution-pending.json`），缺省纯内存；`pending()` 只列 `status="pending"`，已确认/已拒绝的留痕不额外归档；
  3. **操作面**：`core-agent evolve pending|confirm <id>|reject <id> [--note]`；`confirm` = 确认 + 结晶发布一步；`risk_level="high"` 的候选由**操作面**（人）签发 `ApprovalTicket` 后交引擎判定（引擎语义一字不动）；未知 id → stderr + 退出码 1，不复活。
  **副产品**：`crystallize`（过门发布）由此获得**首个生产调用方**（此前为死路径）。决策见 **ADR-0058**。
- **前置**：审批单来源（`permission` 审批流的发起端）—— 已由 `core/im/gateway.py` 的同形先例 + 本变更在 CLI 侧签发满足。

### A5 `observe` 无采样调度器 — ✅ 已关闭（change `0051`）

- **现象**：`EvolutionEngine.observe(target, score, *, now=...)` 是采样接缝，但**无生产调用方**（grep 无命中）→ 观察期窗口开而不采，自动溶解在生产侧不会被触发。
- **根因**：Phase 18 #10 明确不把调度器放进引擎（保持引擎纯粹、`now` 可注入以便测试）。
- **关闭动作（已落地）**：采样来源取**已有数据的最近似口径** —— `EvolutionWorker._sample_observations` 在每轮
  `run_cycle` 后，对本批 trace 中**已开窗**目标按 `plugin_id` 归因算**批次成功率**并各上报一次（线上代理指标、
  零额外评测成本）；无归因 trace 的目标不采样。**已知口径张力（如实记录）**：批次成功率与留出评测分不是同一指标，
  绝对分差容差 `0.2` 只是近似可比 —— 宁漏报不误杀（溶解是不可逆方向的重动作）。**不采纳**「`Evaluator` 评测轮次
  回灌」（要再造一条无人驱动的评测）与「外部上报」（生产无上游）。
- **前置**：A3 进化半边（已随本次一并落盘）。

### A6 观察窗口按 target 覆盖 — ✅ 已关闭（change `0063`，维持现状 + 接口文档标注）

- **现象**：`ObservationRegistry.open` 对同一 target **覆盖旧窗口**（重发布即重开基线、丢旧样本，`observation.py:59-64`，注释即写「重新发布即重新起算基线」）。
- **关闭动作（已落地）**：**维持覆盖语义**并在 `doc/03-interfaces/evolution-interface.md` §3.1 登记为**已知语义**
  ——为什么要覆盖：该窗口的判据是**回归**（基线 = 该次发布的 `eval.held_out_score`），
  同一 target 二次发布若保留旧样本，样本池会混入两个版本的成绩 ⇒ 均分既不表示 v1 也不表示 v2，
  **回归判据失效**；覆盖即「重发布重新校准基线」。
- **不做**：窗口历史留痕（审计需求未出现，不预造存储）；需要时承载点已具名（`dissolve` 教训条目 L2 + 遥测流）。
- **前置**：无。

### A7 语义分未接历史成功率加权 — ✅ 已关闭（change `0058`，ADR-0061）

- **现象**：`SkillMatch.score` 注释自述「匹配度（语义 + 历史成功率 + 适用声明）」，实现只算词法命中率 / 语义分；`SkillFeedback`（`0045` 落地并已接生产）零消费方 → 迭代闭环算出的成功率**路由侧不用**。
- **关闭动作（已落地）**：`SkillRouter` 增可选 `feedback` 注入；`match` 返回前把每个候选的基础分乘**历史成功率因子**即得排序分。
  - 因子：**无样本 = 1.0**（冷启动中性——`success_rate` 无样本返回 0.0，直接相乘会把全部新技能归零）；有样本 = `0.5 + 0.5 × 成功率`（下限防「一次失败 → 不入选 → 无新样本 → 永久失败」的正反馈）；未注入 → 恒 1.0（零回归）。
  - **加权只改排序、不改命中**：词法命中筛选与语义阈值判定的都是**基础分**——否则「语义 0.9 + 历史全失败」会被加权到 0.45 < 阈值而丢弃，属语义漂移。
  - 组合根把 `skill_feedback` 构造**前移**并注入路由（与 `SkillIterator`/`VersionManager` 同一实例，单一真源）。
- **验证**：新增 `tests/test_skill_ranking.py`（8 例：冷启动 / 全成功 vs 全失败 / 50% 缩放 / 按版本取统计 / 语义命中不受阈值加权影响 / 冷启动保持原始语义分 / 共享实例注入 / 端到端排序随反馈变化）；四门全绿（776 passed）。
- **未纳入（转出）**：候选预筛 → **A11**（本次用户裁决 A：只做加权，见下）。

### A8 memory「并发压实一致性」无实现

- **现象**：memory spec 有此 Requirement（`doc/openspec/specs/memory/spec.md:102-105`），实现未做（单线程事件循环、当前无并发调用方，加锁属投机代码）。`adr.md:454` 已记为「先于变更存在的已知缺口」。
- **关闭动作**：出现真实并发调用方时再实现（并补 spec 的并发场景用例）。
- **前置**：并发调用方出现。

### A9 `context.stage` 语义化残留

- **现象**：`ContextPack` 的 `stage` 字段是装配阶段标注，暂不参与事实选择（B6 关闭时的残留项，原并入 A3 清账）。
- **关闭动作**：需要「按阶段差异化选事实」时再语义化。
- **前置**：无。

### A10 进化冷路径无驱动面 — ✅ 已关闭（change `0051`）

- **现象**（本次会话走查新增）：`EvolutionWorker.on_trace_complete` / `maybe_run` 全仓**仅 `runtime.py`（构造）与
  `tests/` 引用** —— CLI 无对应命令、loop 无节拍、无定时器 → L4 整条冷路径离线：`run_cycle`（诊断→提案）、
  `crystallize`（发布 + **开窗**）在生产都不会发生。**这是 A5 的上游**：`observe` 无调用方，但即便把采样接进
  worker，也仍然没人驱动 worker。
- **根因**：同一个形态问题 —— 零件「进程内、无状态、**无驱动**」。与 A1（`forget` 无调度器）同源，只是这一处漏在 L4。
- **关闭动作**：两个诚实答案（无真实常驻宿主：`HarnessHost` 每条 CLI 命令各起一份、serve 非长驻调度器）——
  ① **loop 收尾维护节拍**给出一次冷路径机会（组合根注入 `Callable[[], None]`，与记忆维护**共用节拍闸门**
    `maintenance_interval`；loop 不 import evolution，DI 红线不破）；② CLI **`core-agent evolve run`** 一次性入口
    （装配 runtime → `maybe_run(force=True)` → 打印结局）。**阈值门仍归 `EvolutionTrigger`**，驱动面只给「机会」。
- **前置**：无。

---

## 3. E 类：早期 Phase 未闭合项（全量走查新增）

> 全部经「文档自陈 + `src/` 调用点 / 归档反向核对」判定为**明确未做**。已闭合但文档未销账的旧记见 §8（G 类）。

### E1 constraints 中间件链从未注入 loop（Phase 13 遗留）— ✅ 已关闭（change `0052`）

- **现象**：`DefaultLoop` 有完整中间件链（`loop/default.py` 的 `Middleware` / `_apply_middlewares`），但**生产零注入**——`grep -rn "middlewares=" src/` 空 → 熔断在生产无任何等价物。
- **根因**：`constraints.Middleware` 形状（`ExecRequest/ExecResponse`）与 loop 的 `(LoopContext, Action) → Action|None` 不同，需适配层；`phase-13.md:91` 标「随 Phase 14」但掉档。
- **订正（本次一手核实）**：账本原写的「**校验空转**」**不成立**——校验生产已由工具层 `ToolProvider._validate_args` 承担（与 `Validator.validate_input` 逐行等价）；上下文压缩亦已接线（`compactor=`）。真实残留 = **熔断**。
- **关闭动作**：✅ **已按 change `0052-constraints-middleware-wiring` 闭合**（ADR-0055）——① loop 增**加法式结果侧接缝** `action_observers`（`Middleware` before-only 契约不变）；② 新增 `core/loop/constraints_adapter.py` 的 `ConstraintsChain`（**按 `tool_id` 隔离**熔断、**只计执行类失败**、策略性拒绝不计入）；③ 组合根注入主/子 loop（共享同一实例，熔断态 per-runtime）。**有意未接**：`Validator`（被工具层吸收）、`RetryPolicy`/`Fallback`（幂等风险 / 无生产 `fallback_fn`）。
- **前置**：无。

### E2 UI 无「每会话独立 loop / memory / tools」（Phase 13 遗留）— ✅ 已关闭（会话维度部分，change `0048`）

- **现象**：`UIAPILayer` 只持**一个共享** `self._loop` / `self._memory`（`ui/api.py:52-53`），`self._sessions` 仅存 mode 字符串（`:61`）→ 多会话共用同一 loop 与同一记忆命名空间。
- **根因**：`phase-13.md:93` 把「serve/repl 运行时装配 + 每会话独立 loop+memory+tools」标为 deferred。
- **关闭动作**：✅ **已按 A2 合并方案闭合（change `0048`）**——采「会话标识透传 + 单店按会话归组」（**不做**每会话独立 `(loop, memory)` 实例：单实例并发服务多会话时标识随调用走、天然不串号，组合根与生命周期不动；见 change `0048` design 决策 1/2）。据此 `run_loop` 透传标识、`get_memory` 按会话过滤、`compact` 接真。
- **前置**：无。

### E3 神通（beast）runtime 桥接缺失 — ✅ 已关闭（change `0057`，ADR-0060）

- **现象**（四项同源，2026-10-04 复核全部属实）：
  - `register_innate_skills`（`beast/skills.py`）**零生产调用者**（仅 `tests/test_beast.py`）→ 20 个 `beast.*` 神通从未进过运行时 `SkillLibrary`。
  - `BeastManager` 的 handoff 段被**整段跳过**：`entry._summon` 构造裸 `BeastActivator()`（未传 router）→ `manager.py` `router is None` 短路。
  - `BeastSession` 未注入 loop/memory → 命名空间隔离失效，`remember` 直接抛 `BEAST_MEMORY_WRITE_FAILED`。
  - `SkillRouter.match` 无 domain 参数 → 专属路由只有语义、无 runtime scoping。
- **裁决（用户 2026-10-04）**：**A 全做・解除 deferred**。理由：**「只注册不路由」不是中性半成品**——`SkillRouter.match` 的候选池是全局 `SkillLibrary`，注册后专属神通会进主 Agent 候选并灌进主 prompt，即把系统推入「违反自己规格 R5」的状态。故四项必须一次闭合。
- **关闭动作（已落地）**：
  ① **规格**：beast-mode MODIFIED R4/R5，删去「runtime 调用 deferred」，写明组合根装配义务与**路由期作用域强制**口径；
  ② **注册**：`build_runtime` 构造 `BeastRegistry` → `register_innate_skills(skill_library, registry)`；
  ③ **作用域**：`SkillRouter.match(task, *, domain=None)` —— 三节 `beast.<域>.<技能>` 为专属技能，仅 `domain == "beast.<域>"` 进候选（形状即约定，不另建注册表）；主 Agent / 通用子 Agent 传缺省 → **看不到任何专属神通**；
  ④ **注入**：`BeastManager(registry, router=MultiAgentRouter([]), loop_factory=_beast_loop, memory=memory)`，按兽惰性装配独立 loop（`_loop_hooks(beast.agent_id)` 域内路由）+ 共享 `MemoryStore`；`Runtime` 增 `beast_manager`/`beast_activator`；`entry._summon/_recall` 改走 `build_runtime`（与 `_pet` 同口径）。
- **验证**：新增 `tests/test_beast_wiring.py`（7 例：注册面 / 主 Agent 不可见 / 域内可见 / 通用技能不被误伤 / 组合根暴露面 / 注入生效 / 端到端 summon 跑真 loop + 记忆隔离）；四门全绿（768 passed）。
- **已知接受项**：① CLI 每进程无状态装配 → `recall <beast>` 在该进程内必 `BEAST_NOT_MANIFEST`（**既有性质**，多兽跨命令状态另属后续行）；② 词法路由噪声项（如领域串里的 `/`）可能让他兽技能命中，属打分口径而非作用域（作用域只保证非本域**专属**神通不可达）。
- **未纳入本变更**：多兽并行调度与 `TaskScheduler` 的配合、神兽专用权限策略、`/summon` 斜杠与 WebUI 自然语言入口的真实 UI 接线。

### E4 pet 运行时注入整族缺失（Phase 17.5 §3.2）— ✅ 已关闭（change `0053`）

- **现象**（四项同根：`src/core/runtime.py` 零 pet 引用）：
  - **跨进程存活**：`entry.py:818` 每次调用**新建** `PetManager()`，进程退出即丢 → `pet gather` 后新进程 `pet list` 看不见、`pet stop` 失效。
  - **依赖注入**：`entry.py:819` `PetActivator(manager=manager)` **未注入** loop/memory/explorer/safety/notifier → `observe()/prefer()` 偏好落不到 L2。
  - **wake 无触发**：即便唤醒，`PetSession` 默认是 echo 的 `DefaultLoop`（非真实 loop）。
  - **三入口**：`ui/api.py` 零 pet 引用 → WebUI 自然语言激活（`activate_from_nl`）未接。
- **关闭动作（已落地）**：`build_runtime` 组装 `Explorer`/`SafetyBounds`/`AsyncNotifier` +
  `PetManager`（落盘 `$CORE_STATE_DIR/pets.json`）+ `PetActivator`（注入 runtime 的 loop/memory），
  `Runtime` 增 `pet_manager`/`pet_activator`；`entry._pet`（CLI）与 `UIAPILayer.activate_pet`（WebUI NL）共用之；
  `PetSession.snapshot()/restore()` 支撑注册表快照恢复（`factory` 使加载记录恢复为活会话）。ADR-0056。
- **前置**：A3（存储选型）已闭。
- **未纳入本变更（记后续）**：① `AsyncNotifier` 无 channel → `flush()` 投递未接（记 **E16**）；
  ② 无后台 daemon（pet 仍显式 `wake`，记 **E17**）。
- **已知接受项**：`DefaultLoop` ↔ `LoopPlugin` 协议签名错位（`astream`/`act` 的 async 方向相反）沿用全仓既有
  `cast` 桥接，**非本次引入**。

### E5 主 Agent 自动迭代内部模块（Phase 17 遗留，从未排期）

- **现象**：`phase-17.md:76` 把「自动化迭代闭环本身（主 Agent 自动迭代内部其余模块）」单列为后续 Phase，**此后无任何 Phase 承接** → 从未排期。
- **关系**：即 Phase 18 §1.3-D 点名的「Voyager 式自动课程（P2 可选，不实现）」。
- **关闭动作**：需要时单独立项（前置能力——技能迭代闭环——已由 `0045` 就位）。
- **前置**：无。

### E6 规格层 deferred 未解除项 — ✅ 已关闭（规格订正 + 两项转出）

| 项 | 结论 |
|---|---|
| context「上下文自动压实」判定仍是启发式关键词，未升级为 LLM 判定 | ✅ **规格已订正**（change `0041`，commit `cb61ef3`）：`context/spec.md` 正文已写明本压实器为**启发式降级路径**（关键词识别结论/决策/未决事项），「LLM 提炼统一由记忆压实通道承担，此处不新增模型调用」——即「启发式」是**规格认定的有意行为**，非未兑现的承诺，deferred 不复存在（memory 侧 LLM 摘要通道已由 `cb61ef3` 实现并接线）。**无代码动作**。 |
| M3 遗留：技能 miss 只沉淀、不复用 | → **A7**（§2 A 类），此处仅备案。 |
| memory 并发压实一致性（规格有实现无） | → **A8**，此处仅备案。 |

### E7 内置工具契约与实现漂移 — ✅ 已关闭（change `0056`，纯文档订正）

- **现象**：`cli-contract-baseline.md:260` 的「内置工具 tools.* 9 个」把 `code_run / web_scan / web_execute_js / ask_user / process / memory` 全列为**未实现**。2026-10-04 实测：
  - `tools.code_run` **已实现**（`tools/builtin.py:187`）→ 文档过时；
  - `web_scan` / `web_execute_js` / `ask_user` / `tools.process` / `tools.memory` 在全仓**零出现** → 不是「未实现」，而是「**从未存在**」；
  - 实际实现集：`file_read` / `file_write` / `file_patch` / `code_run` / `web_fetch`（`builtin.py`）+ `install` / `uninstall` / `list`（`install_tools.py`）→ 与契约基线的**名字与集合都已对不上账**。
- **关闭动作（已落地）**：裁决依据是**层级**而非「谁更新」——`doc/openspec/specs/tool-use` 是规范文件、`cli-contract-baseline.md` 是 Phase 早期 `temp/plan_cli_ops/*` 推演稿（文件自附溯源），故**规格赢**。该 5 个名字在 `src/` 与 `specs/` **零出现**（从未存在），不是「未实现」；真实集合 8 个与规格对得上账。→ 订正 `cli-contract-baseline.md` §10 工具清单 + 头部标注「设计态快照、非规范文件」，**未**按过时清单补实现。
- **前置**：无（裁决已由 change `0056` 完成）。

### E8 CLI 契约基线 §11 未决项 — ✅ 已关闭（change `0056`；第 5 条转出 E13）

来源 `cli-contract-baseline.md` §11（其中「config set 写回 + revalidate」已闭环）：

- `--llm-*` / `--im-*` flag 是否接线（当时三模入口未实现，大概率仅设计态）→ 现状需复核（`--llm.embedding-model` 等已在 `0040` 落地，说明 flag 面已部分接通）。
- `permission-mode` 枚举成员未定（与 **E1** 的权限中间件相关）。
- **secret 校验不对称**：`secret_ref` 不强制非空/可解析 → 「空 secret 也能过校验」。
- `features` 无固定清单 → `--feature` 的补全/帮助无法静态枚举。
- `extra` 透传无校验 → 拼错的配置段名被静默吞进 `extra`，不报「未知配置键」。
- `streamable-http` transport 是否支持（= **B1** 子项）。
- **关闭动作（已落地，逐条定性）**：① flag 接线 —— 实测**已接线**（`_CONFIG_SPECS` 声明全部 `--llm.*`/`--im.*`）；② 已闭合；③ `secret_ref` 不对称 —— **已修**（`im.secret`/`judgment.api_key` 与 `llm.api_key` 同口径：非空 + 可解析）；④ features 无固定清单 —— 定性为**设计如此**；⑤ `extra` 未知键 —— **按用户裁决 B 未收紧**（收紧会拒绝既有自定义段），转出为 **E18**；⑥ streamable-http —— = **B2**；⑦ `permission.mode` 枚举 —— **已定并已强制**（四档 `read-only`/`interactive`/`auto-approve`/`high-risk-block`，校验期拒绝其他取值）。
- **前置**：无。

### E9 其他文档层的未闭合项

| 项 | 出处 | 处置 |
|---|---|---|
| `data-model.md` 待补实体 `Session` / `ExecContext` / `ExecRequest` / `ExecResponse`（「字段以编码阶段落地为准」） | `doc/01-architecture/data-model.md:130-138` | 反过来说明**从未回填** → 文档缺口，编码阶段已过，须补 |
| rag / mcp / git 的「替换 X→零改动」测试锚点待补 | `adr.md:329` | ADT 可替换性**无守护测试** |
| 远程制品仓库与凭证 / market-registry 远端服务 | `adr.md:293,302` | 真后端类 → 归 **C** |
| `doc/00-product/retrospective.md:86-90`「实现落地（src=0 是唯一短板）」 | retrospective | **已过时**（当时 `src/` 为空骨架）→ 属 D 类文档订正 |

#### ✅ 已关闭（change `0061-doc-layer-closeout`）

- **一手核实的关键订正**：四项里**只有两项是真缺口**，另两项本就已在账本他处具名 ——
  ① 四实体**均已落地为真实类型**（`core/im/models.py:27`、`core/constraints/models.py:16/24/34`），
  缺的只是 `data-model.md` 回填；② 三条替换性锚点**测试早已存在**
  （`Retriever(_FixedEmbedder(), store)` / `MCPClient(transport_factory=…)` / `GitClient(backend=FakeBackend())`），
  原判「ADT 可替换性**无守护测试**」**不成立** —— 缺的是 `test-cases.md` 的**追踪号**（规格→用例不可达）。
- **关闭动作**：`data-model.md` §4 按源码回填四实体（含权威位置 + 字段，可一步核对）；
  `test-cases.md` 补 `TC-RAG-10` / `TC-MCP-06` / `TC-GIT-11` 三条（挂靠三条「…依赖注入隔离」Requirement）；
  ADR-0040 后果行与 `retrospective.md` §六.1 各加**日期补记**（历史正文不改写 —— 那是伪造决策记录）。
- **改判归属**：远程制品仓库/凭证 与 market-registry 远端服务 → **C 类**（§5 已具名，非文档缺口）。
- **规格中性**：规格/接口/源码三者本就一致，本变更只补登记层 → `skip_specs: true`，`src/`+`tests/` **零改动**。
- **有意不造重复用例**：`_FixedEmbedder` / `FakeTransport` / `FakeBackend` 就是「替换 X」本身，
  再造同义测试是重复建设；rag「替换向量库」一侧仅单实现（生产 sqlite-vec → C 类），追踪行**如实标为半覆盖**。

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

#### ✅ ① 已关闭（change `0060-llm-reliability-tests`）

- **关闭动作**：`tests/test_llm_provider.py` 增「模型调用可靠性」节 **9 例**，按规格「模型调用可靠性」逐 Scenario 对应：退避口径（指数 + 8s 封顶）／重试（瞬时错误重试至成功、耗尽抛归一化异常、非可重试错误不重试）／超时（慢调用不挂起调用方，实测耗时断言）／降级（切备用模型 + 审计记**实际成功**的模型；非瞬时错误不降级）／断流（无 `[DONE]` 提前结束部分返回、传输中途异常**先给已收内容再抛**）。
- **关键事实**：**9 例一次全绿** —— 可靠性实现本就正确，Phase 1 未达成的直接原因是**缺验证**；故本变更 `src/` **零改动**（规格中性，`.openspec.yaml: schema: spec-driven + skip_specs: true`，本仓首个合法的无 delta 变更）。
- **接缝**：重试/超时/降级打桩 `_call_provider`（保留 `acompletion` 的重试循环/`wait_for`/`models` 遍历）；断流打桩 `urlopen`（让真实 `_iter_sse_payloads` 参与，且必须传**惰性生成器**——`list()` 会让异常在进 provider 前就抛，等于没测）。
- **衍生机制**：`skip_specs` 需与 `schema` 同现方被采信（仅 `skip_specs` 报 `expected string, received undefined`）——已由临时 `0060-probe` 探针核实，记入该 change design §4。

#### 🔶 ② 未闭：连接复用（保持未闭，不为未实现的行为写用例）

- **现状**：规格正文已声明「底层连接复用（connection reuse / keep-alive）」，实现未落地 —— `urllib.request.urlopen` 每请求新建连接。
- **关闭需**：`http.client.HTTPConnection` 长连接或自建池 + 失效重建 + 并发所有权模型，配 ADR（**实现变更 + spec delta**）。
- **先决定夺**：stdlib provider 是「零依赖基线」，量产通常换 `litellm`/`openai` 适配器（`runtime.py` 已按 provider 名分流）→ **自建池的收益需先论证**，故不排期。
- **规格处理**：本变更**既未删该条以掩盖差距、也未加「待办」注记污染规格** —— 差距留在账本此处。

---

### E12 崩溃恢复无真实 `kill -9` 用例（Phase 2 验收部分未达成）

- **现象**：`phase-2.md:122` 要求「崩溃恢复测试：`kill -9` 后重启，`resume()` 恢复且无重复副作用」。现有覆盖是**内存 store 模拟**的 resume 幂等单测（`tests/test_durability.py:55,67`），**无真实进程 `kill -9` + 子进程重启**的端到端用例。
- **根因**：durability 用例跑在进程内（快而稳），真实崩溃语义（半写日志、store 未 flush、锁残留）从未被验证。
- **关闭动作**：补 subprocess 用例——子进程写一半被 `SIGKILL` → 重启 → `resume()` 恢复且副作用不重复。
- **前置**：无（低成本，可顺手在 E1 之前做）。

#### ✅ 已关闭（change `0062-crash-recovery-e2e`）

- **关键发现：不只是缺用例，是**实现偏离规格**。一手读 `store.py:77-91`：`_persist` 用
  `Path.write_text` —— **先截断、再整写全量** `checkpoints.jsonl`。进程在截断后、写满前被终止
  → 文件空/半写 → `_load` 跳过不可解行 → 既有检查点**整体丢失**，直接违反 durability 规格
  「崩溃恢复」正文「**已持久化结果不丢失**」。生产已接线（`runtime.py:563`），非死代码。
- **关闭动作**：① 规格「崩溃恢复」MODIFIED —— 明确写入 SHALL 为**原子提交**（半写不损坏既有集合）
  + 新增场景「持久化写入原子性」「真实进程崩溃后续跑」；② `_persist` 改原子提交
  （同目录 tmp + `os.replace`，stdlib；成功路径行为/格式/路径不变）；
  ③ 新增 `tests/test_durability_crash.py`：真子进程 `SIGKILL` 端到端（重载 → `restore()` 取最近有效
  → 按**调用方游标** `resume()` 不重复副作用）+ 半写不损坏（**旧实现必红**，已实测复现：
  `assert [] == ['8d29b2ce…']`）。
- **语义归属不变**：跨进程「不重复副作用」由**调用方游标**（检查点快照状态）保证 —— 本变更把这条
  分工**验证**出来，未改 `resume` 口径（同句柄一次，进程内）。
- **不做**：fsync/掉电语义（`os.replace` 保的是**进程崩溃**原子性，即 E12 场景）；其他持久化点
  （memory/skills/pending）不顺手扩面。
- **衍生新报**：**E19**（下方）—— durability 模块文档 §5 承诺的「持久化故障降级为内存环形缓冲 +
  异步重试落盘」在实现中不存在。

---

### E13 `Validator.parse_output` 零生产调用方 — ✅ 已关闭（change `0063`，判定「有意不接线」）

- **现象**：`Validator.parse_output`（`constraints/validator.py:66`）零生产调用方；
  `LLMPlanner._parse`（`loop/planner.py:201-246`）自解析（`json.loads` + `_PARSE_FAILED`）。
- **一手核实的关键订正**：**规格该 Requirement 已被别处满足**。`specs/constraints/spec.md`
  「输入输出校验」要求「调用后把自由文本解析为结构化指令，解析失败绝不带病执行」，其生产实现是
  **动作感知**的 `LLMPlanner._parse`：原生 `tool_calls` 优先；失败产出 `Action(args={"reply":
  "LLM_PLAN_PARSE_FAILED: …"})` —— reply 是**终止 Action**（`loop/default.py` 的 `act()` 对
  `is_terminal` 直接返回参数）⇒ **工具不执行**；失败 reply 作为观察回灌 ⇒ 下一轮模型看到原因
  ⇒ 即规格场景的「不执行，请求模型修正」。
- **为何 `parse_output` 不该接线**：它是**无动作语义**的通用 JSON 解析（只保证解析出对象，
  判不了 `tool_id` / `reply` 契约、也不认原生 tool_calls）；接进 planner 会让「参数 JSON 损坏」
  这类可归因错误退化成「解析出 dict 就当动作」——**降级**。故是「**不该用**」而非「没用上」。
- **关闭动作**：`constraints-interface.md` §2 把原一句无因断言扩为**判定**（含规格该 Requirement
  的实现归属）；`doc/02-modules/constraints.md` §3.1/§5 指向生产实现；`test-cases.md` 补
  `TC-CONS-05`（此前景规格→用例不可达）；保留 `parse_output` 为中间件契约输出侧 API（有单测）。
- **明确不做**：下沉 planner 解析到 `Validator`（降级，见上）；删 `parse_output`（契约 API，有测试背书）。
- **前置**：无。

### E14 校验码重复 — ✅ 已关闭（change `0059`，ADR-0062）

- **现象**：同一套「schema / 类型 / 必填」校验有两份实现——`tools/provider.py:_matches_type` 与
  `constraints/validator.py:_matches_type` **逐字节相同**；`ToolProvider._validate_args` 与
  `Validator.validate_input` **语义逐行等价**（同 `required` 早返回、同 `properties` 遍历、同消息模板）。
  这是 E1 走查的残留：E1 订正「校验空转」后确认校验实由**工具层**承担，而 `Validator` 是同一口径的
  **第二份实现**（其 `before` 从未接进 loop 链，ADR-0055「有意未接」）。
- **关闭动作（已落地）**：真源留 `constraints`（该义务在 constraints spec 中即其 Requirement）→
  `ToolProvider._validate_args` 改为委托 `Validator().validate_input(tool_id, args, schema)`，
  删除 provider 内 `_matches_type` 副本。**行为中性**：拒绝码 `INVALID_ARGS` 与两条错误消息逐字不变
  （`validate_input` 把缺参列首位、`properties` 序一致 ⇒ `errors[0]` 恒等于旧实现早返回那条）。
- **方向核验（一手）**：`tools → constraints` 合法——`tests/test_architecture.py` 的 `BASE_MODULES`
  不含 `tools`；phase1 禁集只有 `tools → {memory, llm_provider}`；phase2 禁集只有
  `constraints → {loop, skills, orchestration}`；`constraints` 全包不 import `tools`（无环）。
  与 change `0052` 的 `loop → constraints` 同型（横切能力被使用方 import）。
- **验证**：`tests/test_tool_use.py` 增结构守护（`core.tools.provider` 不再有 `_matches_type`）
  + 行为等价（缺参 / 错型两条路径拒绝口径一致）+ 合法参数两条路径皆通过；四门全绿（780 passed）。
- **明确不做**：`Validator.parse_output`（planner 自解析、零调用方 → **E13**）；不改 `tool-use` 规格
  （行为中性，口径只在 constraints 侧记一次）。

### E18 `extra` 未知配置键无校验（E8 第 5 条转出）

- **现象**：`AppConfig.extra`（`models.py:82`）收纳「五类结构化段之外的一切」，拼错的段名（如 `llmm:`）被静默吞入，不报「未知配置键」；`permission.mode` 亦寄居其中。
- **根因**：`extra` 是设计态的宽松兜底；收紧为白名单会**拒绝既有自定义段**（改变既有接受行为）。
- **关闭动作**：先定夺形态 —— **仅告警**（未知键记 WARN 不阻断，兼容性最好）vs **硬拒**（严格，可能破坏既有部署）；定夺后入 spec（configuration「配置校验与生效」）+ 实现。
- **前置**：形态裁决（可能牵动 spec）。

---

### E19 durability 文档承诺的「持久化故障降级」未实现 — ✅ 已关闭（change `0063`；走查来源 change `0062`）

- **现象**：`doc/02-modules/durability.md:74`（§5）称「持久化本身故障（磁盘满 / 后端不可用）不得阻塞
  主循环：**降级为内存环形缓冲，异步重试落盘**」；实现 `CheckpointStore._persist` 失败**直接抛出**。
- **一手核实的关键事实**：该承诺**规格里从来没有** —— 逐字核对 `specs/durability/spec.md`，只有
  「崩溃恢复（含 `0062` 的原子提交）」「检查点损坏降级」两条；过度承诺仅存在于**模块文档**。
  故本项**无规格可订正**，属纯文档订正（规格中性）。
- **关闭动作（用户裁决：订正文档承认现状）**：`durability.md` §5 改写为实际策略 ——
  持久化故障**不静默降级**（直接抛结构化错误，不把「写失败」伪装成「已落盘」）；
  「不得阻塞主循环」的关切由事实兜底：检查点在**波次边界**回调创建（`scheduler.py:226-227`），
  **不在主循环热路径**上，失败即该波中止 → 由 orchestration「断点续跑」承接。
- **明确不做**：实现环形缓冲 + 异步重试 —— 静默降级会**掩盖磁盘满**（与「已持久化结果不丢失」
  的规格精神相悖），且需为一条无生产需求的愿景引入后台线程 + 两套真源（内存 buffer vs 磁盘）。
- **前置**：策略裁决（已裁决）。

---

## 4. B 类：Phase 12 MCP（B1 client 侧已关闭，余 4 行后续）

- **范围**：transport 生产实现（stdio/http）、client 安装分流、消费侧安全接线（本地 stdio 过 `SandboxManager`、远端 http 走出站白名单、不可逆工具走确认门）。

### B1 MCP client 侧：stdio 传输 + 安装分流 + 消费侧安全接线 — 🔶 部分关闭（change `0054`）

- **已关闭（change `0054-mcp-stdio-transport`，2026-10-04，**ADR-0057**）**：
  ① `StdioTransport` —— stdlib 手写换行分帧 JSON-RPC（`subprocess.Popen` + 读线程 + `queue` 超时按 `id` 配对），**零新依赖**；
  ② `SandboxManager.spawn(cmd, env, budget) -> Popen` —— 常驻子进程受 rlimit 约束，`permission` 仍是内核沙箱唯一 owner（复用 `_apply_resource_limits`，不重复实现）；
  ③ `build_transport` 按端点分派（stdio → `StdioTransport`；http/streamable-http → `build_http_transport`；未知 → 结构化 `MCP_CONNECT_FAILED`），**原占位抛错消除**；
  ④ `MCPClient.add` 按来源形状分流（`http(s)://` → http 端点，命令行 → stdio 端点；显式 `transport`/`command` 覆盖推断）+ ctor 注入 `sandbox`/`budget`/`policy`；
  ⑤ `MCPClient._call` 直通传输层结构化 `MCPError`（不再被兜底分支重包为 `MCP_UNAVAILABLE`）；`connect` 失败即 `close` 传输（不留半开连接）；
  ⑥ `plugins/install.py:_install_mcp` 传 `transport`/`command`/`args`（原硬编码 http 且丢参）；
  ⑦ 组合根装配 `SandboxPolicy → SandboxManager(policy=…) → MCPClient(sandbox=…, policy=…)` 并注入 `InstallDispatcher`；`Runtime` 增 `mcp_client` 字段；
  ⑧ `pyproject.toml` optional extra `mcp = ["mcp>=1"]`（ADR-0043 的 http 半边依赖声明）。
- **消费侧确认门经验证已成立**：`MCPToolAdapter` 适配的远端工具带 `coeffects=["network:outbound"]` + `reversible=False`，`PolicyEngine` 对 `network:` 前缀判 `HIGH_RISK` → `PermissionGuard.confirm` → `GateDecision("confirm")`。**无需新代码，仅补验证用例。**
- **ADR-0043 订正**：ADR-0043 字面写 stdio 用 `asyncio.create_subprocess_exec`，实际按同步 `Transport` 契约（`connect/call/ping/close`）落为**同步 stdlib**（`SandboxManager.spawn` + 读线程），已由 **ADR-0057** 记录理由（全 MCP/工具链同步，引 asyncio 会污染调用面）。
- **原阻塞原因（已解除）**：mcp SDK 离线不可装 + 「核心零第三方运行时依赖红线」→ 已由 ADR-0043 裁决（stdio stdlib 手写；http 懒 import 可选 extra）。
- **原现状（已消除）**：`build_transport` 占位抛 `MCP_CONNECT_FAILED` 与 `MCPClient.add` 硬编码 http 两条，均已在 `0054` 消除。

### B2 远端 http/streamable-http 会话 — ⏭ 待开工

- **残留**：`build_http_transport` 目前只完成**可离线验证的半边** —— 出站白名单守卫（非白名单 host → `PERMISSION_DENIED`）、SDK 缺失的清晰降级（`MCP_CONNECT_FAILED` 提示 `pip install core-agent[mcp]`）、已装 SDK 时明确报「会话待接入」。**真正的 http 会话未实现**（`Mcp-Session-Id` 复用、SSE 流解析、`headers` 透传）。
- **阻塞**：`mcp` SDK 为可选依赖，当前环境离线不可装 → 无法端到端验证，按 CLAUDE.md §2 不留投机实现。
- **附**：`pyproject.toml` 的 `[project.optional-dependencies].mcp = ["mcp>=1"]` 已随 change `0054` 声明，但 **`uv.lock` 未含该项**（本环境离线；`uv lock --offline` 会把既有 1600 行解析结果误删，已回滚）→ **联网后需执行 `uv lock`** 使锁文件与 `pyproject.toml` 一致。

### B3 `MCPServer.serve` stdio 事件循环 — ⏭ 待开工

- **残留**：服务端方向（本机作为 MCP server 暴露工具 + 白名单）的 stdio 事件循环未实现；client 方向已在 `0054` 打通。
- **规模**：独立切片，与 B1 无强耦合（可复用同一换行分帧约定）。

### B4 `mcp` CLI 接线 + 端点注册表持久化 — ⏭ 待开工

- **残留**：CLI `mcp serve/list/add/remove` 仍为 stub。`0054` 已把 `MCPClient.add` 与 `InstallDispatcher` 打通，缺的是 **CLI → installer 接线** 与**已安装端点的注册表落盘**（`remove` 的资源释放已随 `close` 终止子进程具备）。

### B5 出站白名单配置项 — ⏭ 待开工

- **残留**：`SandboxPolicy(host_allowlist=…)` 已在 `0054` 可注入且生效（默认空 = 全部拒绝，安全默认），但 `configuration/` 无 `permission.sandbox.host_allowlist` 段 → 生产无法配置放行。
- **前置**：E10 配置门控（与 E15 熔断阈值不可配同源）。

- **参考**：`coding-plan/phase-12.md` §5–§7；`archive/2026-10-01-0033-mcp-install-security/`（原始 tasks 真源）、`archive/2026-10-04-0054-mcp-stdio-transport/`（B1 client 侧关闭凭据）。

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

> **立场不变**：抽象不锁选型，待有真实选型需求时逐项接线。注意其中 **pet·beast 三行**曾是运行时的**接线**缺口（E3/E4）——**两者均已关闭**（change `0053` / `0057`），现余的只是后端本身。

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
| `phase-1.md` | 14 框 | **12 已勾**（`test_llm_provider` / `test_memory` / `test_tool_use` / `test_plugin_registry.py:69,83` 等） | `:30` LLM 可靠性 → **E11**（① 用例已补 change `0060`；② 连接复用未实现）；`:35` 并发压实一致 → **A8** |
| `phase-2.md` | 10 框 | **7 已勾**：durability `test_durability.py:37,105`、permission `test_permission.py:50,195,232`、架构 `test_architecture.py:268`、熔断 `test_constraints.py:75`、MCP 隔离 `test_mcp.py:117,160`、时间旅行与沙箱同族用例 | `:28` constraints 中间件 → **E1 ✅ 已关闭（change `0052`）**；`:31` mcp → **B1**；`:122` 真机崩溃恢复 → **E12** |
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
4. **A3 → A5 → A4 / E4**（进程内态 → 持久化 → 驱动面）：持久化先行，观察窗口 / pending 队列 / `PetManager` 才有意义。 ✅ **A3 全闭 + A5 + A10 + E4 已完成**（change `0050` 技能态落盘 / ADR-0053；change `0051` 进化冷路径驱动面 + 观察窗口落盘 + 批次成功率采样 / **ADR-0054**；A10 为本次走查新增的「冷路径无驱动面」发现；**E4** 见 change `0053` —— pet 纳入组合根 + 注册表落盘 + WebUI NL 入口 / **ADR-0056**）。✅ **A4 已完成**（change `0055-evolution-confirm-surface`：候选稳定身份 + 队列落盘 + `evolve` 操作面签发审批单 / **ADR-0058**）→ 本步**全闭**。
5. **B1**（独立轨）：🔶 **client 侧已关闭**（change `0054-mcp-stdio-transport`，ADR-0057 —— stdio 传输 / `add` 分流 / 消费侧安全接线 / 组合根装配；ADR-0043 的 ADR + spec delta 早已就绪）。**余 4 行后续**：B2 http 会话（需 SDK）/ B3 服务端 stdio / B4 CLI 接线 / B5 白名单配置。
6. **E1 + E7 + E8**（契约与中间件）：✅ **全闭** —— E1 见 change `0052`（ADR-0055；账本原「校验空转」说法已订正——校验实由工具层承担，真实残留是熔断）；**E7/E8 见 change `0056`（ADR-0059）**：E7 裁决「规格为准」→ 纯文档订正；E8 三处缺口修复，第 5 条转出为 E18。
7. **E3 / E6**（规格裁决）：✅ **全闭** —— 裁决「A 全做・解除 deferred」；**E3** 见 change `0057`（ADR-0060：神通注册 + 专属路由作用域 + 按兽 loop/共享记忆注入 + CLI 走组合根）；**E6** 无需代码（context 压实启发式已由 change `0041` 规格订正为有意行为，余两项转 A7/A8）。
8. **A7 + E6（miss 复用）**（低优先，同族）：✅ **全闭** —— **A7** 见 change `0058`（ADR-0061：排序分 = 基础分 × 历史成功率因子；预筛转出 A11）；**E6** 无需代码（见上，规格已由 change `0041` 订正）。
9. **A6 / A8 / A9 / A11 / E5 / E9 / E13 / E15–E18 / C 类**：随需（**A11 语义兜底候选预筛**（需先有比词法更粗的排序信号，**候选预筛**）/ E15 熔断阈值不可配 / E16 `AsyncNotifier` 无 channel / E17 pet 无后台 daemon / **E18 `extra` 未知键校验**）。✅ **E14 已关闭**（change `0059`，ADR-0062）。✅ **E11① 已关闭**（change `0060`：可靠性用例 9 例，`src/` 零改动；**E11② 连接复用**仍开）。✅ **A6 / E13 / E19 已关闭**（change `0063`，纯文档：已知语义登记 + 有意不接线判定 + 过度承诺订正）。
   ✅ **E9 已关闭**（change `0061`：`data-model.md` 四实体回填 + rag/mcp/git 锚点登记 TC-RAG-10/TC-MCP-06/TC-GIT-11 + 两处日期补记；纯文档、规格中性）。
   ✅ **E12 已关闭**（change `0062`：真子进程 `SIGKILL` 端到端 + **修持久化非原子写入**（tmp + `os.replace`）/ 规格 delta）；另新报 **E19**（durability 文档承诺的持久化故障降级未实现）→ **已由 change `0063` 关闭**（订正模块文档承认现状）。
10. **真机动作**：活 LLM 全回路冒烟（§8 末）。

---

## 10. 关闭判据

任一项标「已关闭」须同时满足：

1. 按所属 capability 走完 SDD：spec delta（或明确「规格中性」的判据）→ 测试先行 → 实现 → 四门全绿（ruff check / ruff format / pyright / pytest）；
2. `openspec validate --all` 全绿，change 已归档（本仓库 `openspec archive` 失败，须手动合并 delta + `mv`，见归档惯例）；
3. 本文件对应行更新为「✅ 已关闭（change id / commit）」；
4. 若改变了对外语义，同步 `doc/03-interfaces/*-interface.md` 及相应 ADR。
