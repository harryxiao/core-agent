# Core-Agent Coding Plan（编码落地总索引）

> **定位**：这是「架构设计 → 编码实现」开始前的最后一环规划产物，供 Claude Code / 开发 Agent 按序推进编码时使用。
> 本目录 `coding-plan/` 承载 22 份 Phase 文档（本 README 总索引 + `phase-0.md` ~ `phase-19.md`；含 `phase-2.5.md` / `phase-17.5.md` 两个补丁 Phase，Phase 12 为 DEFERRED 重开预案，Phase 19 为收口后的排期遗漏账本）。
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
| `phase-19.md` | 排期遗漏账本（Phase 18 收口后的未排期项，全量走查）：A 收口遗留 / E 早期 Phase 未闭合（E1 已闭、含 E10–E17） / B Phase 12 重开（B1 client 侧已闭，余 B2–B5） / C 真后端未接 / D 文档杂项 / F ✅ 已清尾 / G ✅ 已销账 | —（非里程碑，记账） |

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
| 17.5 接线补丁 | 🔶 部分完成（pet 半边已由 change `0053` 闭合；遗留见 `phase-19.md` E3） | memory（召回注入接合：task-keyed 检索进 prompt，D1=方案A）→ pet（运行时注入 loop/memory/explorer/safety + 跨进程存活 + wake）→ beast（router handoff + 神通注册 SkillLibrary） | —（无独立里程碑；Phase 18 开工前的接线补丁；memory 召回注入已由 change 0038 闭合、pet 运行时注入已由 change 0053 闭合，beast 运行时注入未做） | 依赖 Phase 17（memory/subagent）/Phase 13（组合根）/Phase 8·10（pet·beast）；**首步 loop spec 补「记忆召回注入」场景 + 修 retrieval query** |
| 18 记忆固化自动化 + 技能进化双维度 | ✅ 完成 | memory（字段扩展 importance/kind → 多因子检索 → 摘要压缩 → 固化 → 遗忘）→ skills（SOP 提取器 → 语义路由 → Skill 迭代）→ evolution（confirm 收口 + auto-dissolve） | M4 自进化收口 + 记忆固化：维度1 技能库/SOP 全自动进化（任务→SOP→Skill→迭代，仅技能库层不动架构代码）、维度2 架构级进化人工审核（confirm 必审）、超阈值自动 dissolve、semantic 摘要可逆可追溯 | 依赖 Phase 15（Validator/Evaluator/SandboxManager/HITL）/Phase 11（judgment，JEV 优先 LLM 兜底）/Phase 17（session 维度）；**首步 MemoryEntry 增字段 + read 多因子检索 + 接口文档同步回填** |
| 19 排期遗漏账本 | 📋 记账中（D/F/G 已清尾；A1/A2+E2 已闭；A3/A4/A5/A10 已闭；E1/E7/E8 已闭；E4 已闭；B1 client 侧已闭） | —（非里程碑：A 收口遗留 A1/A3–A9 / E 早期 Phase 未闭合 E1–E12 / B Phase 12 重开 / C 真后端未接 / D 文档杂项 / F ✅、G ✅ 已清尾） | —（不设里程碑；逐项关闭后销账） | 依赖 Phase 18（已完成）；A2+E2 由 change `0048` 闭合、A1 由 change `0049` 闭合、A3 全闭（skills 半边 change `0050` / evolution 半边 change `0051`）、A5 + A10 由 change `0051` 闭合、**E1 由 change `0052` 闭合（constraints 熔断接入 loop / ADR-0055）**、**E4 由 change `0053` 闭合（pet 纳入组合根 + 注册表落盘 + WebUI NL 入口 / ADR-0056）**、**B1 client 侧由 change `0054` 闭合（MCP stdio 传输 + `add` 分流 + 沙箱/白名单/确认门接线 + 组合根装配 / ADR-0057；余 B2–B5 见 `phase-19.md` §4）**、**A4 由 change `0055` 闭合（候选稳定身份 + 队列落盘 + `evolve pending|confirm|reject` 操作面签发审批单 / ADR-0058）**、**E7/E8 由 change `0056` 闭合（密钥引用校验对称化 + `permission.mode` 枚举校验 + 契约基线订正 / ADR-0059；余 `extra` 未知键转 E18）**；**下一步第 7 步 E3/E6 规格裁决（见 `phase-19.md` §9）** |

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
