# CORE-Harness 架构审计报告
## CLI 命令集 / 启动参数 / 三方插件运行期安装

> 审计日期 2026-09-26 ｜ 审计对象：L0-L5 分层 + 横切 + 工程交付
> 依据：architecture-overview.md（L0-L5 + 组件 + 目录树）、core_harness_architecture.md、adr.md（36 ADR）、25 specs、27 changes、12+ 接口文档、roadmap、coding-plan 交付物
> 本报告为只读交付，不改动任何 spec/ADR/interface。

---

## 0. 审计结论（TL;DR）

架构对 **skill** 有完整闭环（L3 skillhub：市场发现→多源路由→签名校验→发布审核），
但对以下三个面存在**系统性缺口**：

1. **三方插件统一安装（mcp / cli）**：只有 skill 有"安装"闭环，mcp/cli 无运行期安装生命周期
2. **core-agent 自身运维 CLI 命令集**：仅三模入口（TUI/serve/app），无 status/doctor/install/mcp 等命令
3. **启动参数 ↔ 配置参数一一对应**：configuration 只有 yaml+env+默认值，无 CLI 参数覆盖层与映射模型

结论：需一次**架构微调**（不新增分层，补 1 个横切能力 + 扩展 L0 来源抽象 + 补参数映射模型）。详见 `architecture-adjustment-plan.md`。

---

## 1. 审计诉求拆解（用户原话）

1. 架构后续仅针对 skills，但外部 **cli、mcp** 都是三方插件 —— 能否统一支持？
2. skill/mcp/cli 是否支持 **Agent 运行后通过 AI 对话安装** 或 **Agent 工具集安装**？
3. 系统化审查 L0-L5，**不同层/模块的参数与 CMD 覆盖**情况
4. 参数/指令：除启动输入外，还有**配置参数一一对应**

### 关键概念界定（三个"CLI/命令"易混淆，审计先分清）

| 概念 | 含义 | 归属维度 |
|---|---|---|
| (A) 三方 CLI 工具 | 作为插件安装的第三方命令行工具（资产），安装后 Agent 经 subprocess/coeffect 调用 | 插件安装 |
| (B) core-agent 自身 CLI 命令集 | 运维命令 status/doctor/install/mcp/auth... | 命令面 |
| (C) 启动参数 | `--flag` 与配置项一一对应 | 参数映射 |

---

## 2. 审计方法与硬证据

### 2.1 已读权威文档
- 分层权威：`doc/01-architecture/architecture-overview.md`（L0-L5 + 组件表 + 目录树）、`core_harness_architecture.md`
- 决策权威：`doc/01-architecture/adr.md`（ADR-0001~0036 全部）
- 契约权威：25 specs 中与本题强相关的 12+ 份（ui / configuration / plugin-registry / permission / skillhub / mcp / tool-use / loop / context / orchestration / evolution / composition）
- 变更记录：27 changes（含最新 0027-ops-crosscutting 全文实测）

### 2.2 硬证据（grep 全库 = 0 命中）
```
uninstall | subcommand | 子命令
permission-mode | --json-schema | --input-format
argparse | click
```
→ CLI 命令集与启动参数映射在**设计文档层完全缺失**（非实现缺失）。

### 2.3 0027-ops-crosscutting 实测结论
该 change 内容 = **ci-cd 交付流水线 + evolution 任务质量评测泛化 + observability 指标导出/告警**，
**不含** CLI 命令集 / 启动参数 / 插件安装。故"ops-crosscutting"虽名为 ops，实为 CI/CD 与监控，不覆盖本审计的三层缺口。

---

## 3. 三层缺口详解

### 3.1 维度 A：三方插件统一安装（skill / mcp / cli）

**现状证据：**

| 层/横切 | Requirement（实测） | 覆盖判定 |
|---|---|---|
| L0 plugin-registry | 插件注册与生命周期 / 依赖解析 / 隔离与安全 | 只有**进程内**生命周期（注册/启停/卸载/依赖/隔离），**无来源（PluginSource）** |
| L3 skillhub | 技能市场与技能发现 / 多源路由与健康回退 / 签名校验与可信下载 / 技能发布与审核流 | **只覆盖 skill**，不覆盖 mcp/cli |
| 横切 mcp | 连接管理 / 工具资源发现 / 调用转发错误隔离 / Server 模式 / 工具暴露白名单 / 安全约束透传 / 会话调用隔离 / 多流复用 | 有"连接管理+发现"，**无运行期安装/添加生命周期**（连接管理=已配置连接，非安装语义） |
| L1 tool-use | 6 Requirement 全框架语义（注册/校验/coeffect/撤销/超时/异步） | **无 install/uninstall 工具**，Agent 无法经 AI 对话安装 |

> **销账状态（2026-10-04 走查）**：上表三层缺口（InstallableAsset / install-uninstall 工具 / cli-ops 命令集 / CLI 覆盖层 / permission-mode）**除 mcp 传输外均已由后续 Phase 补齐** —— 见 `phase-19.md` G 类。

**缺口判定：**
- ❌ 无统一"可安装资产"抽象（InstallableAsset），skill/mcp/cli 三类的"**获取→校验→安装→注册→激活**"前半段生命周期缺失
- ❌ skillhub 的"签名校验 / 多源路由"能力未上提到统一层复用，导致 mcp/cli 无法复用
- ❌ Agent 无 install/uninstall 工具 → **AI 对话安装不可行**；无 CLI 安装命令 → **工具集安装不可行**

### 3.2 维度 B：core-agent 自身 CLI 命令集

**现状证据：**
- ui spec 9 Requirement：三模统一内核启动 / LLM API 可配置 / **CLI 友好交互** / Web 界面访问 / 桌面打包 / Web桌面一致 / 多模态 / 语音 / Web Client 分离
  → "CLI 友好交互"指 **TUI 交互体验**，非命令集；三模入口 = `core-agent`(TUI) / `core-agent serve` / `core-agent.app`
- ADR 仅 0013（Textual TUI）、0015（MCP 暴露 ToolProvider）两条 UI 相关决策，**无 CMD/启动参数决策**
- grep `subcommand` = 0

**缺口判定（缺失命令清单）：**
- ❌ 生命周期：start / stop / restart / kill（进程守护）
- ❌ 状态：status / doctor / logs / version / help
- ❌ 资产：install / uninstall / list / info（skill/mcp/cli 三类）
- ❌ 连接：mcp add / mcp remove / mcp list
- ❌ 安全：auth / permission-mode
- ❌ 网关：gateway（本地服务网关）

### 3.3 维度 C：启动参数 ↔ 配置参数一一对应

**现状证据：**
- configuration spec 6 Requirement：配置源与分层 / LLM 提供商 / feature flag / IM 接入 / 密钥分级 / 配置校验与生效
  → "配置源与分层"**只有 yaml + env + 默认值，无 CLI 参数覆盖层**
- permission spec 5 Requirement：分级权限体系 / 人工审批流 / 沙箱隔离 / 沙箱执行颗粒度 / 审批动作分级协议
  → **无 permission-mode / dangerous-permission 的 CLI/启动参数表达**
- grep `permission-mode` / `--json-schema` / `--input-format` = 0

**缺口判定：**
- ❌ 无参数优先级链（CLI flag > env > config.yaml > 默认值）的显式建模
- ❌ 无"配置项 ↔ CLI flag ↔ env var"一一对应映射模型（缺单一真源 ConfigSpec）
- ❌ 无 permission-mode 启动开关的 CLI 表达

---

## 4. L0-L5 覆盖矩阵（核心交付）

图例：✅ 完整 ｜ ⚠️ 部分（有语义缺 CLI/参数表达）｜ ❌ 缺失 ｜ - 不适用

| 层/模块 | 插件安装 (A) | CLI 命令集 (B) | 参数映射 (C) |
|---|---|---|---|
| L0 PluginRegistry | ⚠️ 有生命周期无来源 | ❌ | ⚠️ 无注册插件命令 |
| L0 EffectTracker / CoeffectResolver | - | ❌ | ⚠️ 无 CLI 指定 |
| L0 CoreProfileEngine | - | ❌ | ⚠️ 两级 Core.md 无 CLI 指定 |
| L1 ToolProvider | ⚠️ 无 install 工具 | ❌ | - |
| L2 MemoryStore | - | ❌ | ⚠️ backend/路径无 CLI 覆盖 |
| L3 AgentLoop | - | ❌ | ⚠️ max_turns 等无 CLI |
| L3 ContextEngine | - | ❌ | ⚠️ 上下文预算无 CLI |
| L3 SkillRegistry / SkillHub | ⚠️ 只 skill | ❌ | - |
| L3.5 Orchestrator | - | ❌ | ⚠️ 队列配置无 CLI |
| L4 Evolution | - | ❌ | ⚠️ 后台 worker 无 CLI |
| L5 Composition | ⚠️ bundle/pat 分发 | ❌ | - |
| 横切 permission | - | ❌ | ⚠️ 无 permission-mode CLI |
| 横切 configuration | - | ❌ | ❌ 无 CLI 覆盖层 |
| 横切 observability | - | ❌ status/logs | ⚠️ 无日志级别 CLI |
| 横切 durability | - | ❌ stop/start | ⚠️ 无检查点 CLI |
| 横切 mcp | ❌ 无安装生命周期 | ❌ mcp add/remove | ⚠️ 无连接 CLI |
| 工程交付 ui | - | ❌ 仅三模入口 | ❌ 无启动参数 |

**矩阵结论：** 全库"参数/CMD 覆盖"几乎全是 ❌/⚠️，无一行 ✅ —— 印证用户"不同层不同模块可能都有参数和 CMD 覆盖"的直觉，
且**缺口是系统性的（横切配置/权限/ui 三个收口点全缺）**，非个别模块遗漏。

---

## 5. 证据索引

| # | 证据 | 来源 | 结论 |
|---|---|---|---|
| E1 | grep `uninstall|subcommand|argparse|click|permission-mode|--json-schema|--input-format` = 0 | 全库 | CLI 命令集/参数映射设计层完全缺失 |
| E2 | 0027-ops-crosscutting 全文 = ci-cd+evolution+observability | changes/0027 | 名为 ops 实为 CI/CD，不覆盖本缺口 |
| E3 | plugin-registry 3 Requirement 无"来源" | specs/plugin-registry | 无 PluginSource |
| E4 | skillhub 4 Requirement 仅 skill | specs/skillhub | 不覆盖 mcp/cli |
| E5 | mcp 8 Requirement 无"安装" | specs/mcp | 无运行期安装生命周期 |
| E6 | tool-use 6 Requirement 全框架语义 | specs/tool-use | 无 install/uninstall 工具 |
| E7 | ui 9 Requirement 无命令集（"CLI 友好交互"=TUI 体验） | specs/ui | 无运维命令集 |
| E8 | configuration "配置源与分层"仅 yaml+env+默认值 | specs/configuration | 无 CLI 覆盖层 |
| E9 | permission 5 Requirement 无 mode | specs/permission | 无 permission-mode |
