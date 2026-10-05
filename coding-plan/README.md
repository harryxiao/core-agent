# Core-Agent Coding Plan（编码落地总索引）

> **定位**：这是「架构设计 → 编码实现」开始前的最后一环规划产物，供 Claude Code / 开发 Agent 按序推进编码时使用。
> 本目录 `coding-plan/` 承载 23 份 Phase 文档（本 README 总索引 + `phase-0.md` ~ `phase-20.md`；含 `phase-2.5.md` / `phase-17.5.md` 两个补丁 Phase，Phase 12 为 DEFERRED 重开预案，Phase 19 为收口后的排期遗漏账本，Phase 20 为 C 类真后端的「代码半」账本）。
> **规则**：严格按依赖拓扑序推进；每 Phase 完成须 100% 通过门禁三件套；所有 spec/interface 契约以仓库原文为准，速查见契约速查表。

---

## 0. 全局背景（一次说清，后续 Phase 不再重复）

| 维度 | 现状（已实证） |
|---|---|
| 架构定稿物 | 29 specs / 36 changes / 42 ADR / 29 interfaces（`doc/03-interfaces/*-interface.md`） |
| 实现语言 | Python 3.11（`requires-python = ">=3.11"`，可用 `X \| None`、`list[T]`） |
| 代码现状 | `src/` 仅协议骨架（10 个 .py，211 行），几乎无实现，tests 极少 → **「骨架阶段」基线** |
| 分层架构 | `substrate(L0) → tools(L1) → memory(L2) → loop(L3) → evolution(L4) → composition(L5)`，横切 `mcp` 可被各层消费 |
| 工程规范基线 | Phase -1 已闭环：`doc/05-development/development-standards.md`（12 主题）+ ruff/pyright/pre-commit/pytest 门禁可运行 |

> ⚠ **命名注意**：分层图里的 L0 `substrate` 在 Phase 3 落地时**重命名为 `context`**（已拍板决策 D2）；读历史文档时二者同义。

---

## 1. 文档清单（Phase 文档 22 份）

| 文档 | 内容 | 对应里程碑 |
|---|---|---|
| `README.md`（本文件） | 总索引、Phase 映射、门禁、决策点 | — |
| `phase-0.md` | 底座与配置 | M0 底座就绪 |
| `phase-1.md` | 能力提供层 | M1 能力可调 |
| `phase-2.md` | 横切中间件 | —（随 M2 推进） |
| `phase-2.5.md` | 紧急补充：三方插件安装 + CLI 命令面契约回填 | —（无独立里程碑） |
| `phase-3.md` | 引擎主轴 | M2 单 Agent 闭环 |
| `phase-4.md` | 编排与检索 | M3 多 Agent 编排 |
| `phase-5.md` | 进化 | M4 自进化 |
| `phase-6.md` | 组合分发与部署 | —（随 M5 推进） |
| `phase-7.md` | 工程交付与用户入口 | M5 可发布产品 |
| `phase-8.md` | 宠物模式（后台自主增值） | —（随 M5 增值发布） |
| `phase-9.md` | 产品化入口层（entry/serve/repl/pet.md/user-guide） | M6 可启动产品 |
| `phase-10.md` | 神兽召唤层（beast-mode/summon） | M7 神兽召唤 |
| `phase-11.md` | 决策模型接入（judgment/JEV System One） | M8 决策模型接入 |
| `phase-12.md` | MCP 安装/传输/安全接线（stdio 沙箱 + 远端网络管控） | —（DEFERRED，待 ADR 重开） |
| `phase-13.md` | 系统级接线（runtime 组合根 + 热路径真闭环 + judgment DI + entry 贯通） | M9 系统级闭环 |
| `phase-14.md` | 冷路径 + 长任务（进化采集 EvolutionWorker + 多 Agent 长任务编排接线） | M10 进化闭环 |
| `phase-15.md` | 验证门 + 结晶（评测基建 + 进化结晶 + 沙箱颗粒度 + HITL + 崩溃恢复/时间旅行） | M10 进化闭环 |
| `phase-16.md` | 插件/工具链路缺口补齐（CLI 执行入口 + 插件安装分发 + coeffect 来源接线） | M9 修复补丁 |
| `phase-17.md` | 编排打通 + 记忆语义化（subagent 池 + delegate + 记忆落盘/语义读写） | M3 真实收口 |
| `phase-17.5.md` | 接线补丁：memory 召回注入 + pet/beast 运行时注入 | —（无独立里程碑） |
| `phase-18.md` | 记忆固化自动化 + 技能进化双维度 | M4 自进化收口 |
| `phase-19.md` | 排期遗漏账本（Phase 18 收口后的未排期项，全量走查）：A 收口遗留 / E 早期 Phase 未闭合（E1 已闭、含 E10–E29） / B Phase 12 重开（B1 client 侧 + B3 服务端 stdio + B4 CLI 接线 + B5 + B6 标准 envelope + B7 默认暴露面 + B8 远端错误码 已闭，余 B2） / C 真后端未接 / D 文档杂项 / F ✅ 已清尾 / G ✅ 已销账 | —（非里程碑，记账） |
| `phase-20.md` | C 类「代码半」账本（真后端的可离线验证接线工程：git / im(E27) / mcp-http(B2) / ui TTS+Tauri / observability / ci_cd / plugin_registry / skillhub） | —（非里程碑，记账） |

**契约速查**：`contracts_summary.md`（29 capability 的 spec 目标 + interface 核心方法签名 + 模块路径，写代码前先查它）。

---

## 2. Phase 总览与依赖拓扑

> 顺序即依赖序：先无依赖底座 → 能力层 → 横切中间件 → 引擎主轴 → 编排 → 进化 → 组合分发 → 入口。

| Phase | 状态 | 模块（实现顺序） | 里程碑验收 | 关键前置动作 |
|---|---|---|---|---|
| 0 底座与配置 | ✅ 完成 | plugin-registry → configuration → observability → core-profile | M0：可注册/卸载插件、配置单源、遥测可观测、宪法 coeffect 注入 | 无（首个无上游） |
| 1 能力提供层 | ✅ 完成 | llm-provider → tool-use → memory | M1：真实模型调用跑通、工具可定义/调用/校验、记忆可读写与结晶 | 依赖 Phase 0 |
| 2 横切中间件 | ✅ 完成 | constraints → permission → durability → mcp | —（无独立里程碑） | 依赖 tool-use；permission 另依赖 configuration |
| 2.5 紧急补充 | ✅ 完成 | plugin-registry 安装抽象 → configuration CLI 覆盖 → mcp add/remove → permission-mode | —（无独立里程碑） | 依赖 Phase 0/1/2；契约含 0028/0029（M3/M4 代码随 P3） |
| 3 引擎主轴（L3） | ✅ 完成 | context → loop → skills → skillhub | M2：单 Agent 端到端「观察→推理→行动→记忆」闭环 | 依赖 memory/llm-provider + 全部横切；**首步 substrate→context 重命名** |
| 4 编排与检索（L3.5） | ✅ 完成 | orchestration → rag | M3：多 Agent 协同编排、RAG 检索可用 | 依赖 loop/llm-provider/tool-use/durability/distributed |
| 5 进化（L4） | ✅ 完成 | evolution | M4：故障/反馈可触发诊断→提案→验证→结晶全链路 | 依赖 observability/memory/skills/plugin-registry；**evolution↔memory 钩子解耦** |
| 6 组合分发与部署（L5） | ✅ 完成 | composition → distributed → deployment | —（无独立里程碑） | distributed 依赖 mcp/permission；deployment 依赖 composition/configuration |
| 7 工程交付与用户入口 | ✅ 完成 | ci-cd → ui/im/git | M5：完整产品形态可发布 | ci-cd 依赖 composition；ui/im/git 依赖 loop/configuration/permission；**首步补 git 契约** |
| 8 宠物模式（后台自主增值） | ✅ 完成 | pet.core → pet.library → pet.explore → pet.safety → pet.notify → pet.microtask | —（随 M5 增值发布） | 依赖 Phase 0/1/2/3/4；**首步对齐 /pet 三入口↔cli-ops 命令面边界 + Loop.run 同步薄壳复用** |
| 9 产品化入口层 | ✅ 完成 | entry → serve → repl → pet.md → user-guide | M6：可启动产品（`pip install` 后 `core-agent` 可用、serve/repl 双入口跑通、pet.md 多宠物加载） | 依赖 Phase 7（三桥/UIAPILayer）+ Phase 8（PetSession/PetActivator）+ 门禁基线；**首步补 pet.* ConfigSpec + serve/REPL 落地契约** |
| 10 神兽召唤层 | ✅ 完成 | beast-registry → beast-mode → innate-skills → summon-activator | M7：20 神兽可召唤执行前台重大任务（异步并发 + 自动回归）、三入口 | 依赖 Phase 8（pet 范式）+ Phase 9（入口）+ orchestration + skills；**首步走 0034 契约 delta + 补 LoopResult.failed + handoff 异步化** |
| 11 决策模型接入 | ✅ 完成 | judgment（errors → models → router → provider → compactor → guardrail） | M8：三原语 choice/score/noul 统一决策入口 + JEV System One 接入 + 置信度回退主 LLM + 决策轨迹审计 | 依赖 observability + configuration + permission + llm_provider（均已落地）；契约已就绪（0035 + judgment-interface.md）；**首步补 judgment.* ConfigSpec + 归档 0035** |
| 12 MCP 安装/传输/安全 | ⏸ DEFERRED | transport 生产实现 → client 安装分流 → 消费侧安全接线 | —（延期待重开：mcp SDK 离线不可装 + 依赖红线须 ADR） | 依赖 permission（SandboxManager）+ plugin_registry（MCP_ENDPOINT）；**重开首步 ADR 评估 mcp SDK 依赖定位 + 落 0033 ADDED delta** |
| 13 系统级接线 | ✅ 完成 | runtime（组合根）→ loop.planner（LLMPlanner）→ loop tracer 注入 → 横切注入（PermissionGuard/constraints/observability/judgment 三决策点）→ entry 贯通 | M9：单 Agent 真闭环（runtime 全量装配 + loop.reason 接 LLM + judgment 三决策点 DI + entry 贯通走真链路） | 依赖 Phase 0–11（28 capability 已落地，缺系统级装配）+ architecture-overview §4.1/§5；**首步新建 runtime.py 组合根 + LLMPlanner** |
| 14 冷路径 + 长任务 | ✅ 完成 | evolution.worker（EvolutionWorker 消费 Tracer）→ orchestration 接线（TaskScheduler 真 DefaultLoop + checkpoint） | M10：进化采集冷路径 + 多 Agent 长任务「decompose→派发→handoff→checkpoint」跑通 | 依赖 Phase 13（Tracer/DefaultLoop）+ Phase 4/5（orchestration/evolution）；**首步 EvolutionWorker + TaskScheduler checkpoint 注入** |
| 15 验证门 + 结晶 | ✅ 完成 | evolution（评测基建 P2 + 验证门/结晶接线）→ permission（沙箱颗粒度 P1 + HITL P3）→ durability 接 loop | M10：一个真实缺陷走完「诊断→提案→验证→结晶」全链路 + P1/P2/P3 三缺口 + 崩溃恢复/时间旅行接 loop | 依赖 Phase 14（候选）+ Phase 5/2（Validator/Evaluator/SandboxManager/CrashRecovery）；**首步核对评测三件 vs evolution spec** |
| 16 插件/工具链路缺口 | ✅ 完成 | plugins（cli_adapter → install 按 kind 分发）→ runtime coeffect 接线 | M9 修复补丁：CLI 可执行 + 插件安装按 PluginKind 分发 + 内置文件工具 coeffect 贯通 | 依赖 Phase 13 组合根；**首步 CLI 适配层 + 组合根注入 resolver/installer** |
| 17 编排打通 + 记忆语义化 | ✅ 完成 | orchestration（subagent 池 + delegate 工具 + match 无命中报错）→ memory（落盘 + 语义读写 + session 维度）→ loop 委托接线 | M3 真实收口 + 记忆语义化：主 Agent 委托子 Agent 等结果 + 对话语义入记忆可检索 | 依赖 Phase 4（orchestration）/Phase 14（接线）/Phase 1（memory）；**首步 subagent 池注册 + match 无命中报错 + FileBackend 默认落盘** |
| 17.5 接线补丁 | ✅ 已完成（pet 半边 change `0053`、beast 半边 change `0057`） | memory（召回注入接合：task-keyed 检索进 prompt，D1=方案A）→ pet（运行时注入 loop/memory/explorer/safety + 跨进程存活 + wake）→ beast（router handoff + 神通注册 SkillLibrary） | —（无独立里程碑；Phase 18 开工前的接线补丁；memory 召回注入已由 change 0038 闭合、pet 运行时注入已由 change 0053 闭合，beast 运行时注入已由 change 0057 闭合） | 依赖 Phase 17（memory/subagent）/Phase 13（组合根）/Phase 8·10（pet·beast）；**首步 loop spec 补「记忆召回注入」场景 + 修 retrieval query** |
| 18 记忆固化自动化 + 技能进化双维度 | ✅ 完成 | memory（字段扩展 importance/kind → 多因子检索 → 摘要压缩 → 固化 → 遗忘）→ skills（SOP 提取器 → 语义路由 → Skill 迭代）→ evolution（confirm 收口 + auto-dissolve） | M4 自进化收口 + 记忆固化：维度1 技能库/SOP 全自动进化（任务→SOP→Skill→迭代，仅技能库层不动架构代码）、维度2 架构级进化人工审核（confirm 必审）、超阈值自动 dissolve、semantic 摘要可逆可追溯 | 依赖 Phase 15（Validator/Evaluator/SandboxManager/HITL）/Phase 11（judgment，JEV 优先 LLM 兜底）/Phase 17（session 维度）；**首步 MemoryEntry 增字段 + read 多因子检索 + 接口文档同步回填** |
| 19 排期遗漏账本 | 📋 记账中（D/F/G 已清尾（D6 由 change `0069` 闭合）；A1/A2+E2 已闭；A3/A4/A5/A6/A7/A8/A9/A10/A11 已闭；E1/E3/E4/E6/E7/E8 已闭；B1 client 侧已闭；E11 全闭；E5/E9/E10/E12/E13/E15/E16/E17/E18/E19/E21/E22/E24/E25/E28/E29 已闭；E20①/E20②/E23 已闭；**E26 已闭（change `0086` + `0087` + `0088`）**；B3/B4/B5/B6/B7/B8 已闭） | —（非里程碑：A 收口遗留 A1/A3–A9 / E 早期 Phase 未闭合 E1–E12 / B Phase 12 重开 / C 真后端未接 / D 文档杂项 / F ✅、G ✅ 已清尾） | —（不设里程碑；逐项关闭后销账） | 依赖 Phase 18（已完成）；A2+E2 由 change `0048` 闭合、A1 由 change `0049` 闭合、A3 全闭（skills 半边 change `0050` / evolution 半边 change `0051`）、A5 + A10 由 change `0051` 闭合、**E1 由 change `0052` 闭合（constraints 熔断接入 loop / ADR-0055）**、**E4 由 change `0053` 闭合（pet 纳入组合根 + 注册表落盘 + WebUI NL 入口 / ADR-0056）**、**B1 client 侧由 change `0054` 闭合（MCP stdio 传输 + `add` 分流 + 沙箱/白名单/确认门接线 + 组合根装配 / ADR-0057；余 B2–B5 见 `phase-19.md` §4）**、**A4 由 change `0055` 闭合（候选稳定身份 + 队列落盘 + `evolve pending|confirm|reject` 操作面签发审批单 / ADR-0058）**、**E7/E8 由 change `0056` 闭合（密钥引用校验对称化 + `permission.mode` 枚举校验 + 契约基线订正 / ADR-0059；余 `extra` 未知键转 E18）**、**E3 由 change `0057` 闭合（神通注册 + 专属路由作用域（`SkillRouter.match(domain=)`）+ 按兽 loop/共享记忆注入 + CLI 走组合根 / ADR-0060）**、**E6 关闭（context 压实启发式已由 change `0041` 规格订正为有意行为，余两项转 A7/A8）**；**A7 由 change `0058` 闭合（排序分 = 基础分 × 历史成功率因子（冷启动中性 + 下限），判定仍用基础分 / ADR-0061；候选预筛转出 A11）**；**E14 由 change `0059` 闭合（校验口径单一真源：工具层调用前校验委托 constraints `Validator`，行为中性 / ADR-0062）**；**E11 由 change `0060` + `0066` 全闭（① 可靠性用例 9 例：重试/超时/降级/断流，`src/` 零改动 —— 实现本就正确；② **连接复用已实现**：`http_pool.HTTPConnectionPool` 线程本地按 origin 复用 keep-alive + 失效重建 + 代理/3xx 回落，真实 socket 用例 9 例 / ADR-0064）**；**E9 由 change `0061` 闭合（`data-model.md` 四实体按源码回填 + rag/mcp/git 替换性锚点登记 TC-RAG-10/TC-MCP-06/TC-GIT-11 + ADR-0040/retrospective 日期补记；纯文档 / 规格中性）**；**E12 由 change `0062` 闭合（真子进程 `SIGKILL` 崩溃恢复端到端 + 修持久化非原子写入：tmp + `os.replace` / 规格 delta；新报 E19）**；**A6 / E13 / E19 由 change `0063` 闭合（纯文档、规格中性：观察窗口覆盖为有意语义登记 / `parse_output` 有动作语义的是 planner ⇒ 有意不接线 + 补 `TC-CONS-05` / durability 过度承诺订正为「不静默降级」）**；**E18 由 change `0064` 闭合（未知配置段**仅告警**（WARN 不阻断）：`ValidationResult.warnings` + `load()` 发出（stdlib `warnings`，零接线）/ 已知段白名单由 `_CONFIG_SPECS` 派生（单一真源）/ 口径只到顶层段名 / ADR-0063；规格 delta：configuration「配置校验与生效」）**；**E17 由 change `0065` 闭合（**规格未要求 daemon**：规格无条款（Lifecycle「每次唤醒…逐次执行」/ Yielding「同步 + 锁」）+ `pet <verb>` 一次性进程无法承载线程 ⇒ 登记「`wake()` 由**宿主**驱动、内核不常驻」；纯文档 / 规格中性 `skip_specs`）**；**A9 已销账（规格明文认可 stage 不参与事实选择，零变更）**；**A8 已销账（**零变更**：`FileBackend` 单把 `RLock` 覆盖全部读写路径 + 压实只归档不删除 ⇒ 规格「加锁/等待」已满足；订正原判「无并发调用方」——`ui serve` 同步路由走 Starlette 线程池，与事件循环 `/run` 真并发）**；**E10 由 change `0067` 闭合（功能开关运行时门控：门控名单 `pet`/`beast`/`evolution` 归组合根单一真源 `runtime.GATABLE_MODULES` + **缺省装配**（未声明即开，仅显式 `features.<模块>: false` 才不装配：不构造 / 不注册神通 / 不读状态文件 / 冷路径置空 / 7 入口拒绝）+ 新增谓词 `is_disabled`（`is_enabled` 语义不变）/ ADR-0065；新报 E20「未知模块名无告警 + 非布尔强转」/ E21「`entry._pet` 判据忽略 yaml」）**；**E15 由 change `0068` 闭合（熔断阈值/冷却可配：`constraints.failure_threshold` / `constraints.cooldown_s` 经 `ConfigSpec` **单一真源**四通道可配 + **不新增结构化段**（`extra` 驻留）+ 非法取值**校验期拒绝不兜底** + 组合根注入、主/子 loop 共享同链 / ADR-0066）**；**D6 由 change `0069` 闭合（订正 llm-provider「LiteLLM 默认实现」陈旧措辞 + 全仓现行文档同类措辞；纯文档 / 规格中性 `skip_specs`）**；**E21 由 change `0070` 闭合（`entry._pet` 前置判定接入 `ConfigManager.config_value(key)`：CLI > env > **config.yaml** > 缺省，ConfigSpec 单一真源 + 配置缺文件按「无 yaml 层」容错 + persona 目录同源读取；同型缺陷 `config get` 转出为账本新行 **E22**）**；**B5 由 change `0071` 闭合（出站白名单可配：`permission.sandbox.host_allowlist` **CSV 标量**（yaml 子集无列表 ⇒ 三面统一、解析/写回不动）+ `ConfigSpec` 单一真源 + 非法条目**校验期拒绝**不静默 + 组合根注入（缺省空 = fail-closed 不变）/ ADR-0068）**；**E20② + E23 由 change `0072` 闭合（feature flag 三面取值同口径：合法集合 `true/false`·`yes/no`·`on/off`·`1/0` + 原生布尔、其余**校验期拒绝不静默强转**（`off` 不再被 `bool()` 当作开启）；`--feature NAME[=BOOL]` 经覆盖层 `features.<模块>` 接入优先级链并**真的**支配装配（此前**零消费**）；**E20① 保持开放**（规格限告警于顶层段名，须先改规格）/ ADR-0069；**新报 E24** —— env 前缀实现为复数 `CORE_FEATURES_`、规格/文档写单数，改名属对外破坏性变更，**待裁决**；**已由 change `0080` 关闭**（裁决改规格/文档向实现靠拢：单数 → 复数，零代码，spec MODIFIED + 补齐 `0072` 丢失正文段））**；**B3 由 change `0073` 闭合（MCP Server 模式 stdio 事件循环：`serve_stdio` 换行分帧 JSON-RPC 事件循环（按 `id` 应答 / 通知不应答 / 非法行跳过 / EOF 退出）+ `mcp serve` 接线（`_HANDLERS` 注册 + `--whitelist` 逗号分隔）+ **单条请求异常隔离为错误应答、绝不终止循环**（协议层 `-32601`/`-32603` 与工具层 `CallResult` 分层）+ 补齐文档已写而代码缺席的暴露面契约（对外名 `core.<tool_id>` / 白名单接受裸名与带前缀 / `mcp.*` **禁止二级代理**）+ 协议版本提为共享常量 `core.mcp.models.PROTOCOL_VERSION`；端到端用例用本仓 `MCPClient` 拉起真实子进程锁住 / ADR-0070；**新报 B6**（wire envelope 未对齐标准 ⇒ 第三方客户端直接挂载不可用）/ **B7**（默认暴露面启发式过粗 ⇒ `tools.delegate`/`tools.web_fetch` 默认亦暴露），均待裁决）**；**B4 由 change `0074` 闭合（`mcp` CLI 接线 + 端点注册表持久化：`mcp add/list/remove` 接线（**先连通验证再落盘**）+ 端点落 `$CORE_STATE_DIR/mcp-endpoints.json`（**状态非配置**，**原子写** tmp + `os.replace`）+ **装配期**读回经同一安装管线连接注册（`handle_id` 取安装名 ⇒ 工具名 `mcp.<端点名>.<工具>` **跨进程稳定**）+ 重名 `ENDPOINT_NAME_CONFLICT` 拒绝（不静默覆盖）+ **单端点不可达只告警跳过、不阻断装配**（注册表损坏同口径）+ `mcp remove` 先卸载释放连接/子进程再删记录；`mcp` spec MODIFIED + 7 新场景；排查记录：`--command` 的 argparse `dest` 与顶层 `dest="command"` 冲突曾把 `mcp add` 静默送进 REPL / ADR-0071）**；**B6 由 change `0075` 闭合（MCP 标准 envelope 双向对齐：两侧最小对齐 + 载荷恒 JSON 编码 + client 容忍厂商扩展字段并兼容旧式裸形状；**真机双向验收** —— `claude mcp add` 挂本 server 报 `✔ Connected`、本 client 挂 `claude mcp serve` 发现 20 工具 / ADR-0072；转出「远端 JSON-RPC 错误码未映射」B8）**；**B7 由 change `0076` 闭合（MCP 默认暴露面收窄：默认面判据由「无 `write`」改为**安全 coeffect 白名单**（`⊆ {filesystem:read}`，空集=只读）⇒ 出网 / 进程派生 / 委托驱动一律默认不出；`tools.delegate` 补声明 `agent:delegate`（原 `coeffects=[]` 漏声明）+ 组合根注册（运行期行为不变，新增可见性）；白名单语义不动 / ADR-0073）**；**B8 由 change `0077` 闭合（远端 JSON-RPC 错误码映射：`transport.map_remote_error` 按「方法 + 标准码」归一 —— `tools/call` 的 JSON-RPC 错误 → `MCP_TOOL_NOT_FOUND`（MCP 约定工具**执行**失败走 `isError` 结果信封，故该路径上的错误 = 调用本身被拒）、其余 `-32700/-32600/-32601/-32602` → `MCP_PROTOCOL_MISMATCH`、`-32603`/未知码 → `MCP_UNAVAILABLE`；映射为可测纯函数，原始码保留于文本 / ADR-0074）**；**E22 由 change `0078` 闭合（`config get` 接入 yaml 层：`entry._config` 的 `get` 分支改用 `ConfigManager.config_value`（与 `pet` 门控同一通路）⇒ 完整优先级链 CLI > env > config.yaml > 缺省 / ADR-0075；转出『feature flag 未知名告警』E20① 仍开）**；**E16 由 change `0079` 闭合（pet 通知三环接线：一手核实后比记载严重 —— 生产者 `PetSession._notifier` 零调用 / 通道 `AsyncNotifier()` 无 `channel` / 投递点 `flush()` 零调用方三层全断；接通为 生产者落 `wake()` 收尾（反馈周期命中投递 `report()` 产出）+ 缺省通道 = stderr 一行（可宿主替换为 IM）+ 投递点由组合根收成单一可调用体（入队即 flush，注入面签名不变）/ ADR-0076；转出 pet 安全越界路径 **E25**、`surprise()`/`MicrotaskRunner` 零调用方 **E26**、`IMGateway` 零生产装配 **E27**、无宿主驱动 `wake()` **E28**）**；**E29 由 change `0082` 闭合**（pet「Runtime Wiring」的「主 loop」字面订正为「组合根装配的真实 loop（专属 loop，非 echo 兜底）」，零代码、由 `0081` 自报）；**E26 保持开放 / D4 保持不动不提交**（用户裁决）；**E28 由 change `0083` 闭合**（CLI `pet run --interval` 宿主驱动 + 驱动薄壳故障隔离 + 注册表恢复；规格中性）；**E5 由 change `0084` 闭合**（引擎侧自动课程：结构化信号定序议程 + 先验权重 < 1.0（只破并列不压证据）+ 显式目标入口 `evolve run --goal`；spec ADDED「自动课程」+ MODIFIED「对比诊断」「冷路径驱动」/ ADR-0079）；**A11 已销账（零变更**：规格明文「逐条打分」（`skills/spec.md:65-66`）⇒ 未预筛是规格行为；O(N) 成本需 JEV 真凭证 + 库规模大 + 词法 miss 三重条件同时成立，当前均不成立；用户裁决登记销账、不做投机预筛）**；**E20① 由 change `0085` 关闭**（`features` 段未知模块名告警：规格先行 —— 顶层段名口径加 `features` 唯一例外 + 组合根注入已知模块名集合、仅告警／ADR-0080）**；**E26 全关闭（change `0086`／ADR-0081 + change `0087`／ADR-0082 + change `0088`／ADR-0083**：pet 惊喜去谎报与上报（surprise 半边）+ 微任务真实化与空闲自治睡眠（microtask 半边 —— `MicrotaskRunner` 接线且三条任务真实化、`wake()` 消费队首任务、队列清空 ⇒ 入睡、新任务自动唤醒）+ **控制面** `/pet [cmd]`（用户诉求① —— `PetControl` 单门面收口 `status`/`sleep`/`wake`/`assign`/`stop`、CLI 与 `UIAPILayer.pet_command` 复用同一实现、寻址不猜、`status` 不外泄偏好与任务正文、**仅本进程**））**；**余 B2/E27/C 类（C 类代码半见 `phase-20.md`）** |
| 20 C 类「代码半」账本 | 📋 记账中 | 真后端的**代码半**：git 真实现 + im(E27) 装配/宿主入口 + mcp-http(B2) 适配器 + ui TTS/Tauri sidecar + observability 一行装配 + ci_cd 门禁执行器 + plugin_registry 多源 resolver + skillhub 接线 | —（非里程碑：对 `debug-gaps.md` §2.3 的 9 行做「代码半 / 凭证半」二分；8 项有可离线验证的代码半、0 项纯凭证、1 行过时） | —（不设里程碑；逐项关闭后销账） | 依赖 Phase 19（已完成）；凭证半仍在 `phase-19.md` §5；关闭判据见 `phase-20.md` §6；**C4 `observability` 已关闭（change `0089`）；C2 `git` 已关闭（change `0090`，余装配待消费者）；C3 `ci_cd` 已关闭（change `0091`，余装配/CLI 待消费者）；C5 `skillhub` 已关闭（change `0092`，余真实市场 fetcher）；C6 `plugin_registry` 四源解析器已关闭（change `0093`，余 git 远端/市场/端点凭据）；C8 `ui` Tauri 桌面壳已关闭（change `0100`／ADR-0093，余壳二进制打包未验证）** |

> **里程碑口径（M0~M10）**：M0 底座就绪（P0）→ M1 能力可调（P1）→ M2 单 Agent 闭环（P3）→ M3 多 Agent 编排（P4）→ M4 自进化（P5）→ M5 可发布产品（P7）→ M6 可启动产品（P9，M5 的入口侧补缺）→ M7 神兽召唤（P10，前台重大任务）→ M8 决策模型接入（P11，judgment/JEV System One）→ M9 系统级闭环（P13，runtime 组合根 + 单 Agent 真闭环）→ M10 进化闭环（P14+P15，冷路径采集 + 长任务编排 + 验证门/评测/结晶）。
> Phase 2（横切中间件）、Phase 6（组合分发部署）为**贯穿阶段**，不单设里程碑，其成果在 M2/M5 验收中一并体现。

---

## 3. 工程规范基线（Phase -1 已闭环，全程硬约束）

门禁命令（**提交前四者必须全绿**，否则该 Phase 视为未完成）：

```bash
ruff check src tests            # lint（select 规则集）
ruff format --check src tests   # 格式（行宽 100、双引号）
pyright                         # 类型（strict，include=src）
pytest -q                       # 单元 + 架构测试
```

12 条编码规范主题（详见 `../doc/05-development/development-standards.md`）：
1. Python 编码规范（PEP8 + ruff format/check + pyright strict，目标 py311）
2. 命名约定（类 PascalCase / 函数 snake_case / 常量 UPPER_SNAKE / 私有 `_` 前缀，禁止缩写）
3. 多线程安全（锁/队列/asyncio 三选一，明确线程归属，禁止裸锁跨 async 边界）
4. if/else 最大嵌套 ≤3 层（超限抽函数/卫语句/字典分发）
5. 低耦合高内聚（单一职责、依赖倒置、禁止跨层 import 实现类）
6. 串行/并行规范（默认串行，仅独立 I/O + 无共享状态才并行，禁止裸 fork）
7. 异常处理（DomainError/SystemError 分层、禁止裸 except、跨边界记录 trace_id）
8. 状态机设计（enum + 迁移表显式建模、非法迁移抛错、状态持久化）
9. 模块设计（L0-L5 分层、`__init__.py` 白名单导出、接口与实现分离）
10. 函数复用（DRY，≥3 处重复即抽取，复用优先于新写）
11. 最小化实现（KISS + YAGNI，每个类/函数可解释「为什么存在」）
12. CPU 性能（先 cProfile/py-spy 定位热点再优化，禁止无依据预优化）

> **离线工具链**：ruff 0.15.6 / pyright / pytest 均已缓存；**勿用 `uv run`**（会触发环境解析超时），直接调缓存二进制（路径见 development-standards.md 附录）。

---

## 4. 已拍板决策点（D1~D4，各 Phase 文档须遵守）

| 决策 | 内容 | 影响 Phase |
|---|---|---|
| D1 | `rag`、`git` 两个 capability 补契约（spec 已有，缺 interface） | P4 / P7 首步 |
| D2 | 分层 L0 `substrate` → 重命名 `context` | P3 首步 |
| D3 | `evolution` ↔ `memory` 的 Protocol 钩子解耦（避免循环依赖） | P5 |
| D4 | 全程按 M0~M6 里程碑口径推进，全量覆盖 Phase 0~9 | 全部 |

---

## 5. 每 Phase 文档统一模板

各 `phase-N.md` 一律采用以下 8 段结构，保证跨 Phase 可读性与可执行性：

1. **范围与定位**：本 Phase 覆盖哪些 capability，在分层图 L0~L5 中的位置
2. **里程碑验收**：对应 M 里程碑 + 具体验收标准（可勾选清单）
3. **依赖与前置**：上游 Phase / capability，无上游则明示「首个」
4. **首步任务**（如有）：补契约 / 重命名 / 钩子解耦等先行动作
5. **实现顺序**：模块级拓扑序 + 每个模块的关键类/接口
6. **契约对齐**：引用 `contracts_summary.md` 对应章节 + 关键方法签名
7. **门禁验收**：ruff / pyright / pytest 四命令全绿 + 本 Phase 专属校验
8. **提交规范**：一个 Phase 一个 commit，更新 `README.md` §2 状态列

---

## 6. 使用方式（给 Claude Code / 开发 Agent）

1. **总则**：从 `phase-0.md` 开始，按 Phase 0 → 1 → … → 9 顺序推进，**完成一个再开下一个**，禁止跳跃。
2. **每 Phase 的三件套动作**：
   - 读对应 `phase-N.md` + `contracts_summary.md` 中该 Phase 涉及的 capability 契约；
   - 实现代码，并逐一对齐 interface 契约（方法签名/语义）；
   - 跑门禁四命令全绿 + 单测/契约校验通过后，方视为完成该 Phase。
3. **跨 Phase 一致性**：接口引用以 `doc/03-interfaces/*-interface.md` 为准；出现契约冲突时，回读 spec 原文裁决，不要凭记忆改接口。
4. **回填**：每 Phase 完成后更新 `README.md` §2 总览表状态列并 commit（一个 Phase 一个 commit，便于回溯）。

---

## 7. 快速入口索引

| 想查什么 | 去哪 |
|---|---|
| 29 capability 的契约（方法签名/模块路径） | `contracts_summary.md` |
| 开发路线图（M0~M5 全貌） | `/home/harry/work/generic-agent/GenericAgent/temp/plan_devroadmap/plan.md` |
| 编码规范 + 门禁 | `../doc/05-development/development-standards.md` |
| 接口契约原文 | `../doc/03-interfaces/*-interface.md` |
| spec 目标原文 | `../doc/02-modules/*/spec.md` |
