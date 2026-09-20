# CORE-Harness（core-agent）开发文档中心

> 本目录是 **CORE-Harness** 架构（以下简称 **CORE**）从**产品 → 架构 → 模块 → 接口 → 测试 → 开发**的完整开发文档集，
> 采用 **SDD（Spec-Driven Development，规格驱动开发）** 方法论组织，规格格式对齐 GitHub 官方 SDD 工具
> **[Fission-AI/OpenSpec](https://github.com/Fission-AI/OpenSpec)**（★69k+，最主流 SDD 框架）。

---

## 0. 什么是 SDD，以及我们如何使用它

**SDD 的核心思想**：先把系统**应该做什么**（行为规格）写清楚、写可验证，再由 AI / 人类据此实现与测试。
"规格先行" —— 行为是规格的正文，代码是实现；规格是**事实的唯一来源（source of truth）**。

我们严格遵循 OpenSpec 的约定：

| OpenSpec 概念 | 在本仓库的落点 | 说明 |
|---|---|---|
| **Spec（规格）** | `openspec/specs/<capability>/spec.md` | 系统**当前应如何行为**的唯一事实来源 |
| **Requirement（需求）** | `### Requirement:` + `SHALL/MUST/SHOULD` | 一条可观察的行为，一个句子一个 `SHALL` |
| **Scenario（场景）** | `#### Scenario:` + `GIVEN/WHEN/THEN/AND` | 可自动化成测试的具体例子 |
| **Change（变更）** | `openspec/changes/<id>/` | 一次有单一意图的修改提案 |
| **Delta（增量规格）** | change 内 `## ADDED/MODIFIED/REMOVED Requirements` | 描述相对现状的增/改/删 |

**RFC 2119 关键词强度**：`MUST/SHALL`（硬性、不可协商）＞ `SHOULD`（强烈建议、可有正当例外）＞ `MAY`（可选）。

**一条好需求的标准**：*一个从未看过代码的测试者，能否判断它是否通过？* 能 → 合格；不能 → 需打磨。

---

## 1. 文档目录结构

```
doc/
├── README.md                      ← 本文件：方法论 + 索引 + 使用方式
│
├── 00-product/                    【产品定义层】
│   ├── product-definition.md      愿景/目标/用户/价值主张/范围/非目标/成功指标
│   └── requirements.md            功能需求 + 非功能需求（PRD 风格，可追踪到规格）
│
├── 01-architecture/               【架构设计层】
│   ├── architecture-overview.md   总体架构（L0–L5 分层 + 组件图 + 数据流）
│   └── adr.md                     架构决策记录（ADR，关键取舍与理由）
│
├── 02-modules/                    【模块设计层】
│   ├── plugin-registry.md         插件注册/组合基底（L0，一切皆插件）
│   ├── loop.md                    智能体循环（L3：感知→推理→行动→写记忆）
│   ├── memory.md                  分层记忆（L2：L0元规则–L4归档）
│   ├── tool-use.md                工具使用（L1：原子工具 + 可逆效应）
│   ├── mcp.md                     MCP 集成（Model Context Protocol 外部能力）
│   ├── evolution.md               进化引擎（L4：诊断→提案→验证→评测，结晶经济）
│   ├── context.md                 上下文工程（L3 输入侧：信息地图 + 压实 + 预算）
│   ├── skills.md                  技能封装（L3 结晶层：版本/灰度/路由）
│   ├── orchestration.md           任务编排（L3.5：状态机/子任务/交接/断点续跑）
│   ├── permission.md              权限与审批管控（横切策略层：分级/审批/沙箱）
│   ├── constraints.md             约束与容错（横切：校验/熔断/重试/压缩中间件）
│   ├── observability.md           可观测性（横切：日志/指标/追踪/审计）
│   ├── llm-provider.md            三方 LLM 归一化接入（LLMProvider 抽象 + LiteLLM 默认实现）
│   └── composition.md             组合与分发（L5：profile 命名组合 / bundle 分发 / patch 覆盖）
│
├── 03-interfaces/                 【接口设计层】
│   ├── plugin-registry-interface.md        插件契约（trait/lifecycle/reversible effect/coeffect）
│   ├── memory-interface.md        分层记忆读写/查询接口
│   ├── tool-use-interface.md          工具调用与结果接口
│   ├── mcp-interface.md           MCP server/client 接口
│   ├── evolution-interface.md     进化引擎四阶段接口
│   ├── context-interface.md       上下文装配/信息地图/压实接口
│   ├── skills-interface.md        技能注册/版本/路由接口
│   ├── orchestration-interface.md 任务编排/交接接口
│   ├── permission-interface.md    权限判定/审批/沙箱接口
│   ├── constraints-interface.md   约束中间件接口
│   ├── observability-interface.md 日志/指标/追踪接口
│   ├── llm-provider-interface.md  三方 LLM 归一化调用接口（completion/stream/embedding）
│   ├── composition-interface.md   组合分发接口（解析 / 打包 / 编排 / 分发）
│   ├── loop-interface.md          智能体循环插件契约（coeffect + run）
│   └── ui-interface.md            统一后端 API + CLI/Web/Desktop 三模桥接
│
├── 04-testing/                    【测试设计层】
│   ├── test-strategy.md           测试策略（金字塔、可逆效应性质测试、留出评测）
│   ├── test-plan.md               测试计划（层级/环境/进出准则/责任人）
│   └── test-cases.md              测试用例（逐条对齐 openspec 场景）
│
├── 05-development/                【开发层】
│   ├── development-guide.md       工程规范/目录布局/插件开发流程/Git 工作流
│   └── sdd-workflow.md            SDD 工作流（spec → change → delta → archive）
│
├── 06-ui-frontend/                【UI 界面与启动模式】
│   └── ui-architecture.md         CLI(Textual)/Web(SPA)/Desktop(Tauri) 三模方案与 ADR-0013~15
│
├── 07-mcp-server/                 【MCP Server 模式】
│   └── mcp-server.md              对外工具源（机器→core-agent 入口）与 ADR-0016~17
│
├── 08-im-gateway/                 【IM 网关模式】
│   └── im-gateway.md              社交 App 远程入口（随身→core-agent）与 ADR-0018~20
│
└── openspec/                      【SDD 规格（唯一事实来源）】
    ├── specs/                     ← 系统当前应有的行为（只描述 what，不描述 how）
    │   ├── plugin-registry/spec.md
    │   ├── loop/spec.md
    │   ├── memory/spec.md
    │   ├── tool-use/spec.md
    │   ├── mcp/spec.md
    │   ├── evolution/spec.md
    │   ├── context/spec.md
    │   ├── skills/spec.md
    │   ├── orchestration/spec.md
    │   ├── permission/spec.md
    │   ├── constraints/spec.md
    │   ├── observability/spec.md
    │   ├── ui/spec.md
    │   ├── im/spec.md
    │   ├── llm-provider/spec.md
    │   └── composition/spec.md
    └── changes/                   ← 修改提案（proposal + design + tasks + delta specs）
        ├── 0001-bootstrap-core/   核心骨架引导变更（原 6 能力）
        ├── 0002-safety-crosscutting/  安全与横切能力变更（新增 6 模块）
        ├── 0003-ui-frontend/          UI 界面与启动模式变更（CLI/Web/Desktop）
        ├── 0004-mcp-server/           MCP Server 模式变更（对外工具源）
        ├── 0005-im-gateway/           IM 网关模式变更（社交 App 远程入口）
        ├── 0006-llm-provider/         LLM Provider 归一化接入变更（任意三方模型）
        ├── 0007-composition/          组合与分发能力变更（L5 新增 capability）
        └── 0008-evolution-four-stages/  进化四阶段闭环变更（诊断→提案→验证→评测）
```

---

## 2. 文档之间的追踪关系（可追溯性矩阵）

```
产品需求(requirements.md)  ──追踪──►  规格(openspec/specs/*)  ──实现──►  模块设计(02-modules/*)
        │                                     ▲                            │
        │                                     │                            ▼
        └── 非功能需求 ──► 架构(01-architecture)                   接口(03-interfaces)
                                              ▲                            │
                                              └──────── 测试(04-testing) ──┘
```

- **每个 Requirement ID**（`CORE-<模块>-R<n>`）在 `requirements.md`、`openspec/specs/*`、`test-cases.md` 三处保持**同号**，保证可追踪。
- **每个 Scenario**（GIVEN/WHEN/THEN）对应 `test-cases.md` 里至少一条自动化/人工测试用例。

---

## 3. 如何使用（配合 OpenSpec CLI）

```bash
# 1) 安装 OpenSpec（需 Node.js ≥ 20.19）
npm install -g @fission-ai/openspec@latest

# 2) 在 core-agent 目录初始化（生成 config.yaml + 空 specs/、changes/archive/ 骨架）
cd /home/harry/work/core-agent
openspec init --tools none

# 3) 校验规格合法性
openspec list        # 列出规格与变更
openspec validate    # 校验 spec 格式与 delta 一致性
openspec show <spec> # 查看某规格

# 4) 提出新变更（SDD 工作流）
#    在 openspec/changes/<change-id>/ 下写 proposal / tasks / design + spec delta
openspec validate <change-id>  # 校验 change 与 delta 一致性
openspec archive <change-id>   # 合并 delta 进 specs/ 并归档到 archive/
```

> 未安装 OpenSpec 时，`doc/openspec/` 内的 Markdown 规格**同样可读、可审查**——它们本身就是格式化的行为契约。

---

## 4. 阅读顺序建议

| 角色 | 建议路径 |
|---|---|
| 产品/PM | 00-product → openspec/specs（只看行为） |
| 架构师 | 00-product → 01-architecture → 03-interfaces |
| 开发者 | 01-architecture → 02-modules → 03-interfaces → 05-development |
| 测试 | openspec/specs（场景）→ 04-testing |
| 全流程 | 按编号 00→05 顺序通读，最后对照 openspec/ |

---

## 5. 顶层架构速览（详见 01-architecture）

```
L5 组合分发   profile · bundle · patch
L4 进化引擎   诊断 → 提案 → 验证 → 留出评测        ← 进化即结晶
L3.5 任务编排 状态机 · 子任务拓扑 · 交接 · 断点续跑
L3 智能体循环 感知 → 推理 → 行动 → 写记忆（~100 行）
   ├─ context  上下文工程（信息地图 · 压实 · 预算）
   └─ skills   技能封装（版本 · 灰度 · 路由）
L2 分层记忆   L0元规则 · L1索引 · L2事实 · L3技能 · L4归档
L1 原子工具   9 个可逆插件（code_run/file_*/web_* ...）
L0 基底       插件注册 · 可逆效应追踪 · coeffect 解析 · HMR
横切能力     permission 权限/审批/沙箱 · constraints 约束/熔断/压缩 · observability 日志/指标/追踪
```

**中心隐喻**：*插件即原子、记忆即光谱、进化即结晶*——想法先以经验进入（L4），稳定后结晶为技能（L3），
足够稳定则提升为插件（代码）；失败则可逆卸载、降级回记忆。**记忆与代码是同一光谱的两端。**
