# CLAUDE.md — core-agent (CORE-Harness)

> 本文件是 Claude Code 的项目记忆：进入本仓库开发时，先按此处导航理解项目，再动手。
> Core-Agent 自身的运行时灵魂文件是 `~/.core/Core.md`（全局：人格/宪法/全局规则，启动时读取）与 `<project>/Core.md`（项目信息，载入项目时按 cwd 向上查找），由 Core-Agent 读取；本 CLAUDE.md 仅供外部 Claude Code 使用，二者分工并存、互不加载。

## 一句话定位

**CORE-Harness** 是一个「无特权核心」的插件化智能体运行时：以**可逆插件**为最小原子、以**分层记忆**为进化轨迹载体、以**对比诊断 + 验证门**为进化引擎，让系统沿「经验 → 技能 → 插件」方向**结晶**，失败时沿反方向**可逆溶解**。

## 中心隐喻与设计原则

- **插件即原子、记忆即光谱、进化即结晶** —— 记忆与代码是同一光谱的两端（结晶经济）。
- P1 无特权核心（loop/记忆/进化引擎/模型适配器都是插件）
- P2 一切副作用可逆（`EffectTracker.record(effect, undo)`，时间/空间可组合）
- P3 进化局部化与可归因（缺陷定位到具体插件）
- P4 进化必经验证门 + 不可变世代（无 review + 运行时验证不出世代）
- P5 记忆先行、代码后置；技能结晶、token 有界

## 分层架构（L0–L5）

```
L5 组合分发    profile · bundle · patch
L4 进化引擎    诊断 → 提案 → 验证 → 留出评测        ← 进化即结晶
L3.5 任务编排  状态机 · 子任务拓扑 · 交接 · 断点续跑
L3 智能体循环  感知 → 推理 → 行动 → 写记忆（~100 行）
   ├─ context  上下文工程（信息地图 · 压实 · 预算）
   └─ skills   技能封装（版本 · 灰度 · 路由）
L2 分层记忆    L0元规则 · L1索引 · L2事实 · L3技能 · L4归档
L1 原子工具    9 个可逆插件（code_run/file_*/web_* ...）
L0 基底        插件注册 · 可逆效应追踪 · coeffect 解析 · HMR
横切能力       permission 权限/审批/沙箱 · constraints 约束/熔断/压缩 · observability 日志/指标/追踪
```

## 目录导航

| 路径 | 内容 |
|---|---|
| `core_harness_architecture.md` | 架构总纲（三源融合 + 结晶经济） |
| `doc/` | SDD 开发文档集（00产品 → 05开发，入口 `doc/README.md`） |
| `openspec/specs/` | **行为规格（source of truth，勿直接改根目录）** |
| `openspec/changes/` | 变更提案（proposal/tasks/design + spec delta） |
| `src/core/` | 代码（substrate / tools / memory / loop / evolution / mcp） |
| `tests/` | pytest（单元 + 集成，BDD 用 pytest-bdd） |
| `openspec/config.yaml` | SDD 上下文与规则（AI 生成 artifact 时可见） |

## 技术栈与常用命令

- Python 3.11+（type hints + dataclass/Protocol），包管理用 **uv**
- 依赖安装：`uv sync`（venv 在 `.venv/`）
- 运行测试：`uv run pytest`（testpaths=tests，pythonpath=src）
- OpenSpec CLI（Node.js ≥ 20.19）：
  - `openspec validate` —— 校验 specs 与 delta 一致性（**归档前必须全绿**）
  - `openspec list` / `openspec show <spec>`
  - `openspec validate <change-id>` → `openspec archive <change-id>`

## 开发约定（必须遵守）

1. **SDD 规格先行**：行为规格是事实唯一来源；实现偏离规格时，**先改规格再改代码**；按 `tasks.md` 逐项实现，先写测试再实现。
2. **插件契约**：插件实现 `plugin_id / generation / schema / coeffects` + `load/unload/check`。
3. **可逆副作用**：所有写操作必须 `EffectTracker.record(effect, undo)`。
4. **密钥安全**：配置/密钥经 `CoeffectResolver` 注入；**密钥只引用不读取、绝不进日志/记忆**。
5. **错误处理**：结构化错误码，不向模型抛裸异常。
6. **提交格式**：`feat(<capability>): ...`
7. **规格引用**：需求以 `CORE-<模块>-R<n>` 编号，变更须指明改哪条 Requirement。

## 文档阅读顺序

- 产品/PM：`doc/00-product` → `openspec/specs`
- 架构师：`doc/00-product` → `doc/01-architecture` → `doc/03-interfaces`
- 开发者：`doc/01-architecture` → `doc/02-modules` → `doc/03-interfaces` → `doc/05-development`
- 测试：`openspec/specs`（场景）→ `doc/04-testing`

> 完整方法论见 `doc/README.md`；架构取舍见 `doc/01-architecture/adr.md`。
