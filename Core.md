<!-- Core Profile · 项目级（<project>/Core.md）· 载入项目时读取，cwd 向上查找 -->
<!-- 仅承载「项目信息」，同名配置项覆盖全局级 -->

## 项目信息
> 本分区 → 注入 ContextEngine 上下文（随项目切换自动装载）

- 项目：CORE-Harness（core-agent）——无特权核心、可组合、可观测、递归可进化的插件化智能体运行时；插件即原子、记忆即光谱、进化即结晶。
- 技术栈：Python 3.11+（类型注解 + dataclass/Protocol）、uv 包管理、pytest（+pytest-bdd）、OpenSpec CLI（Node.js ≥ 20.19）、MCP、LiteLLM（LLMProvider 归一化接入）、CLI(Textual)/Web(SPA)/Desktop(Tauri) 三模前端。
- 能力清单：L0 基底（插件注册/可逆效应/coeffect/HMR）· L1 原子工具 · L2 分层记忆 · L3 智能体循环（context+skills）· L3.5 任务编排 · L4 进化引擎（诊断→提案→验证→评测）· L5 组合分发；横切 permission/constraints/observability；capabilities 含 mcp、ui、im、llm-provider、distributed、rag、git、deployment、core-profile。
- 文档真源：`doc/openspec/specs/`（行为规格，唯一事实来源）+ `doc/openspec/changes/`（变更提案），SOP 走 OpenSpec SDD 流程。
- 目录约定：`doc/00-product` ~ `doc/12-git`（SDD 文档集）、`src/core/`（substrate/tools/memory/loop/context/skills/orchestration/evolution/permission/constraints/observability/mcp）、`tests/`。
- 关键约束：改动须过 `openspec validate` 全绿；交付须含 proposal/design/tasks 三件套且语义一致；写操作必须 `EffectTracker.record(effect, undo)`；密钥只引用不读取、绝不进日志/记忆。
- 编码期约定：提交格式 `feat(<capability>): ...`，一个 commit 对应一个 change/规格 delta；规格先行，先写测试再实现。
