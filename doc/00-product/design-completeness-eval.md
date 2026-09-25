# Core-Agent 架构 SDD 功能设计全面性评估报告

> 评估时间：2026-09-20
> 评估对象：Core-Agent SDD 文档体系（`doc/` 全量）
> ⚠️ 本评估基于**补齐前 17-capability 基线**；补齐后为 **24 capability**（新增 `rag`、`git`、`deployment`、`core-profile`、`durability`、`configuration`、`skillhub`），详见 §4.2「缺口排序与补齐路线」
> 数据基线：既有架构审计报告（17 capability / 10章105篇 / 15接口 / 9 change / 23 ADR）+ 本轮横向调研
> 调研方法：开源框架取 GitHub README 实证；闭源产品取公开文档与业界共识（官网 JS 渲染，正文不可 fetch）

---

## 一、评估方法与对象

本报告回答三个问题：
1. 架构设计完善度如何；
2. 相对主流 Agent 产品处于什么位置；
3. SDD 文档的功能设计是否「全面」。

功能设计全貌取自 `requirements.md` 24 模块 + `openspec/specs/*` 24 capability（Purpose/Requirements 已逐一核对），对比基线为 5 个开源框架 + 4 个闭源产品 + 2 个自托管个人助理（OpenClaw/Hermes）。

---

## 二、SDD 功能设计全貌：24 capability → 5 大功能域

Core-Agent 的 24 个 capability 按职责收敛为五层，功能面覆盖完整、职责边界清晰：

| 功能域 | capability | 功能要点 |
|---|---|---|
| ① 运行时核心 | loop / orchestration / composition / deployment / core-profile | 观察→推理→行动→记忆稳态循环 + 状态机/子任务拆解/多Agent协同 + 组合代数静态层（无业务逻辑、永不进化）+ 运行环境抽象（进程/容器）/自托管优先+可选云托管 BYOC/生命周期管理 + 两级 Core.md 灵魂文件（~/.core/Core.md 人格/宪法 + <project>/Core.md 项目信息）启动/载入读取注入 |
| ② 记忆与进化 | memory / context / evolution / skills / skillhub / rag | L0元策略~L4原始会话光谱 + 动态上下文/信息地图/自动压实 + 结晶经济闭环（采集→结晶→溶解→提案→验证门→评测）+ 技能库/灰度A/B/路由 + 本地向量库语义检索补知识缺口 |
| ③ 能力接入 | tool-use / plugin-registry / mcp / llm-provider / git | schema化工具+coeffect副作用契约 + 插件注册/依赖/隔离 + MCP双向(client+server) + LiteLLM归一化/可替换 + 版本控制核心操作/高危操作审批链 |
| ④ 安全横切 | permission / constraints / observability / durability / configuration | 分级权限/人工审批/沙箱隔离 + 输入输出校验/容错/压缩中间件 + 日志/指标/链路追踪三信号 + checkpoint/崩溃恢复/回滚 + 配置加载/功能开关/密钥解析 |
| ⑤ 交互协作 | ui / im / distributed | CLI/Web/Desktop三模统一内核 + 微信/飞书/TG/Discord社交入口 + A2A双向/AgentCard/安全鉴权/多设备拓扑 |

**设计特色**：五层职责单向依赖、横切能力以「中间件」形式插入 loop（权限/约束/观测），是「无特权核心 + 分层插件化」的完整工程化表达。

---

## 三、主流 Agent 产品架构对比矩阵

（●=完整支持 ◐=部分/需扩展 ○=缺失）

| 架构维度 | Core-Agent | Claude Code | Cursor | Manus | Devin | LangGraph | CrewAI | AutoGPT | OpenAI Agents | LiteLLM | OpenClaw | Hermes |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 核心循环/运行时 | ● | ● | ● | ● | ● | ●(graph) | ● | ●(blocks) | ●(handoffs) | — | ●(Gateway) | ●(loop+TUI) |
| 编排/工作流 | ● | ◐ | ◐ | ● | ● | ● | ●(Flows) | ●(builder) | ● | — | ◐(skills) | ◐(subagents/cron) |
| 分层记忆 | ●(L0-L5) | ◐(CLAUDE.md) | ◐(索引) | ◐ | ◐(KNOWLEDGE) | ● | ◐(knowledge) | ◐ | ●(sessions) | — | ◐(MEMORY.md) | ●(持久+画像+程序性) |
| 上下文工程 | ●(信息地图/压实) | ● | ◐ | ●(压缩) | ◐ | ◐ | ○ | ○ | ◐ | — | ◐(session) | ◐(context-files) |
| 工具/插件 | ● | ● | ● | ● | ● | ● | ● | ● | ● | — | ●(tools/skills) | ●(40+tools) |
| 技能/子代理 | ●(skills) | ●(skills/subagents) | ◐ | ● | ◐ | ◐ | ●(Crews) | ● | ●(agents) | — | ◐(skills) | ●(skills自改进+subagents) |
| MCP | ●(双向) | ●(client+server) | ● | ◐ | ◐ | ◐ | ◐ | ○ | ◐ | — | ◐(未明示) | ●(MCP集成) |
| LLM归一化 | ●(LiteLLM) | ◐(Anthropic原生) | ◐ | ◐ | ◐ | ◐ | ◐ | ◐ | ◐(OpenAI) | ● | ◐(多provider) | ●(任意模型) |
| 权限/审批 | ●(分级+审批) | ● | ◐ | ● | ● | ◐(HITL) | ◐ | ◐ | ●(guardrails) | — | ●(DM配对+审批) | ●(命令审批+DM配对) |
| 沙箱隔离 | ●(设计) | ●(bash隔离) | ○ | ●(VM) | ●(VM) | ○ | ○ | ◐(托管) | ◐ | — | ◐(默认host/可选) | ●(7终端后端) |
| 约束/容错中间件 | ●(输入输出校验) | ◐ | ○ | ◐ | ◐ | ◐ | ○ | ○ | ●(guardrails) | — | ◐(不可信输入防护) | ◐ |
| 可观测性 | ●(三信号) | ● | ◐ | ◐ | ◐ | ●(tracing) | ◐ | ◐ | ●(tracing) | ●(网关日志) | ◐(events) | ◐(trajectory) |
| 进化/自优化闭环 | ●(结晶经济) | ○ | ○ | ◐ | ○ | ○ | ○ | ○ | ○ | ○ | ○ | ●(learning-loop+skills自改进) |
| 人机协作(HITL) | ●(审批流) | ● | ● | ● | ● | ● | ● | ● | ● | — | ●(聊天+审批) | ●(聊天+审批) |
| UI/多入口 | ●(CLI/Web/Desktop) | ●(CLI) | ●(IDE) | ●(Web) | ●(Web) | ◐ | ◐ | ●(platform) | ◐(SDK) | ◐(网关) | ●(UI/CLI/TUI+app) | ●(TUI/CLI/Desktop) |
| 社交IM入口 | ●(微信/飞书/TG/Discord) | ○ | ○ | ○ | ◐(Slack) | ○ | ◐(Slack) | ◐ | ○ | ○ | ●(8渠道) | ●(5渠道+HA) |
| 分布式A2A | ●(AgentCard/拓扑) | ○ | ○ | ○ | ○ | ◐ | ○ | ○ | ○ | ○ | ◐(Gateway多节点) | ◐(subagents/RPC) |
| 多模态/语音 | ◐(语音输入转写+实时语音输出，缺视觉) | ◐(图像) | ◐ | ● | ◐ | ◐ | ◐ | ◐ | ●(voice) | ◐ | ●(voice/camera/screen) | ◐(voice转录) |
| 代码库索引/embedding | ◐(信息地图+RAG，已落地未工程化) | ◐ | ● | ○ | ●(index-repo深度索引) | ◐ | ◐ | ○ | ○ | — | ○ | ○ |
| 托管/部署平台 | ◐(自托管+可选云托管BYOC) | ◐(Claude服务) | ● | ● | ● | ●(LangGraph Cloud) | ◐ | ●(platform) | ● | ●(网关) | ◐(自托管) | ◐(自托管+多后端) |

---

## 四、完善度评估

### 4.1 架构设计完善度：B+（与审计报告一致，此处以横向视角复核）

**结构性优势（相对主流产品显著领先的 3 点）：**

1. **进化引擎（evolution）是体系化程度最高的差异化能力**。9 个既有对比对象全部是「固定能力 + 人工调优」，唯一例外是 Hermes Agent——它内置 learning loop（自主创建 skills + skills 自我改进 + trajectory 压缩），印证了「自优化」路线的可行性；但 Hermes 的进化停留在「技能层面的自我改进」，缺少 Core-Agent「采集→结晶→溶解→提案→验证门→评测」的四阶段闭环与结晶经济。Core-Agent 把进化做成一等公民，仍是功能设计上最大的前瞻性。

2. **记忆光谱 + 组合代数是体系化设计**。L0~L5 分层记忆（含「无行动不记忆」原则）、composition 静态组合层（组合代数无业务逻辑、永不进化）在主流产品中无对应物——LangGraph 只有 state、Claude Code 只有 CLAUDE.md，都远不及 Core-Agent 的体系化程度。

3. **入口维度最全（CLI/Web/Desktop + IM + A2A）**。多数对比对象为单一入口（Claude Code=CLI、Cursor=IDE、Manus/Devin=Web）；同为个人助理的 OpenClaw/Hermes 在 IM 渠道数量上更广（含 iMessage/Signal/Teams），但只有 Core-Agent 一次设计覆盖「人→机器→机器」三类入口（IM + UI + A2A），入口完整性业界少见。

### 4.2 功能设计全面性：A-（覆盖广），本轮补齐多模态/托管两处缺口

相对主流产品，SDD 功能设计在以下维度覆盖不足或缺失：

| # | 缺口维度 | 现状 | 主流产品参照 | 影响 |
|---|---|---|---|---|
| 1 | 代码库索引/embedding | context 仅有「信息地图」（语义层），无 embedding/向量检索工程化定义 | Cursor 的 codebase indexing 是核心竞争力；Devin 有 | 长代码库/大仓库场景的检索性能与精度存疑 |
| 2 | 多模态/语音 | 已有语音输入转写，本轮落地实时语音输出（0014-voice），仍缺视觉多模态 | OpenAI Agents SDK 有 voice；Manus/Claude Code 有图像；OpenClaw 有 companion apps（voice/camera/screen） | 语音链路已闭环，视觉多模态（图像/屏幕理解）仍无设计位 |
| 3 | 沙箱执行的工程颗粒度 | permission 有「沙箱隔离」但停留在概念层 | Devin/Manus 的云端 VM（browser+terminal+FS 全隔离）、Claude Code 的 bash 沙箱 | 交付就绪度 C 的关键短板之一，需补齐到可执行规格 |
| 4 | HITL 审批颗粒度 | 「人工审批流」未展开（approve/reject/edit-plan 分级） | Claude Code permission 规则、OpenAI HITL 粒度 | 审批流的具体交互协议缺失 |
| 5 | 评测/eval 平台 | evolution 有「评测留出」但未工程化 | OpenAI Agents eval、LangSmith eval | 进化闭环的「验证门」缺可落地的评测基建 |
| 6 | 托管/部署平台 | 已落地 deployment capability（自托管+可选云托管 BYOC，0013-deployment） | AutoGPT platform、LangGraph Cloud、LiteLLM 网关 | 云端托管可选项已补齐，自托管仍为主路径 |

**缺口排序与补齐路线：**

| 优先级 | 缺口 | 补齐路线 | 落点 |
|---|---|---|---|
| P0 | #1 代码库索引/embedding | 任务2/3 引入 RAG（specs/rag）+ codebase-memory-mcp 接入（doc/10-codebase-engine） | specs/rag/spec.md + doc/10-codebase-engine/ |
| P1 | #3 沙箱执行的工程颗粒度 | 扩展 specs/permission 沙箱执行规格 | specs/permission/spec.md |
| P2 | #5 评测/eval 平台 | 扩展 specs/evolution 验证门评测基建 | specs/evolution/spec.md |
| P3 | #4 HITL 审批颗粒度 | 扩展 specs/permission 审批流协议 | specs/permission/spec.md |
| P4 | #2 多模态/语音 | 已落地：specs/ui 实时语音输出（0014-voice）+ 原有语音输入转写 | specs/ui/spec.md |
| 已落地 | #6 托管/部署平台 | 0013-deployment：自托管+可选云托管 BYOC | specs/deployment/spec.md |

### 4.3 交付就绪度：C（不变，仅确认）

以上缺口均属**设计层可补**（不涉及架构推倒），但与审计结论一致：**src 目录零实现**，SDD 停留在「功能设计全面、工程落地为空」的状态。全面性评估针对的是**设计文档**而非交付能力。

---

## 五、结论

| 评估项 | 评级 | 依据 |
|---|---|---|
| 架构设计完善度 | **B+** | 五域 24 capability 职责清晰、横切中间件化、入口最全 |
| 功能设计全面性 | **A-** | 覆盖 20 个对比维度（原 ○ 的多模态/托管已由 ○→◐ 补齐，无 ○ 残留），进化引擎体系化程度业界最高、记忆光谱/组合代数仍为独有，6 处对比缺口本轮补齐多模态/托管两处 |
| 相对主流产品定位 | **设计前瞻性领先，工程落地滞后** | 差异化能力多（evolution/光谱记忆/IM/A2A），但 src=0、沙箱/评测/embedding 未落地 |
| 交付就绪度 | **C** | 纯文档态 |

**一句话总结**：Core-Agent 的 SDD 在功能设计的广度与前瞻性上已达到甚至超越主流 Agent 产品的架构高度（体系化进化闭环、光谱记忆、三模+IM+A2A 入口、组合代数均为业界少见的原创设计），但纵向深度不均——6 处对比缺口中的多模态/托管已在本轮补齐（语音实时输出 0014-voice、托管 deployment 0013），其余集中在「工程落地颗粒度」（沙箱、embedding、eval、HITL 协议），且整体仍为零实现文档态，设计全面性 A- 与交付就绪度 C 之间的落差是当前最大风险。
