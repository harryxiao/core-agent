# 模块设计：核心画像（Core Profile）

> 对应规格：`doc/openspec/specs/core-profile/spec.md` ｜ 接口：`doc/03-interfaces/core-profile-interface.md`
> 定位：**启动与载入项目侧**，为 Core-Agent 提供可预设的人格、宪法与全局规则（灵魂文件），与 CLAUDE.md 分工并存。

---

## 1. 模块定位

Core Profile（灵魂文件）是 Core-Agent 的"人格与宪法"预设载体。它让 Agent 的行为特色（人格）、必保约束（宪法与全局规则）、项目上下文（项目信息）都能通过 Markdown 文件在启动与载入项目时被读取，从而塑造稳定的 Agent 身份，避免每次会话都要重新口头交代。

本模块通过**两级文件、双语义分区、按需注入**三件事，把文件预设转化为运行时生效的 coeffect 与记忆层内容。

---

## 2. 内部组成

```
CoreProfileEngine（启动 / 载入项目装配侧）
├── GlobalProfileLoader   全局级 ~/.core/Core.md 加载（人格/宪法/全局规则）
├── ProjectProfileLoader  项目级 <project>/Core.md 加载（cwd 向上查找）
├── SectionParser         分区解析（宪法与全局规则 / 人格 双语义分区）
├── Merger                多级合并（项目级覆盖全局级）
└── Validator             格式校验与容错
```

---

## 3. 关键设计

### 3.1 两级加载时机

- 全局级 `~/.core/Core.md`：Agent 启动时读取，承载人格、宪法与全局规则。
- 项目级 `<project>/Core.md`：载入项目时读取，承载项目信息。
- 加载结果分别注入：宪法与全局规则 → constitution:v1 coeffect（LoopContext 装配时）；人格 → L0 记忆层；项目信息 → ContextEngine 注入上下文。

### 3.2 双语义分区

- 「宪法与全局规则」分区：注入 constitution:v1 coeffect，作为必保约束参与执行。
- 「人格」分区：落入 L0 记忆层，作为元策略与人格预设参与决策。
- 两分区职责不重叠，由 SectionParser 按分区标记解析。

### 3.3 项目级 cwd 向上查找

- ContextEngine 载入项目时，从当前工作目录向上逐级查找 Core.md，命中最靠近的项目根文件，注入其项目信息。
- 不新增 project 维度，保持轻量；向上到文件系统根未命中时静默降级。

### 3.4 多级合并优先级

- 项目级覆盖全局级：同名配置项以项目级为准。
- 与 CLAUDE.md 分工并存：CLAUDE.md 保留给外部 Claude Code（项目记忆），Core-Agent 仅读取 Core.md 作为自身预设，二者互不干扰。

### 3.5 题词技法

- 「宪法与全局规则」分区：命令式可判定句式，每条以「必须/禁止」表述、可判定真伪，不承载具体操作细节。
- 「人格」分区：结构化描述（身份 / 工作风格 / 沟通风格 / 决策偏好 / 边界意识）。
- 「项目信息」分区：仅承载项目特有信息，不重复全局规则。
- 篇幅受控：单个 Core.md 建议不超过 50 行，细节下沉 L2/L3 记忆层。

### 3.6 题词模板

全局级 `~/.core/Core.md` 模板：

```markdown
<!-- Core Profile · 全局级（~/.core/Core.md）· Agent 启动时读取 -->
## 宪法与全局规则
> 本分区 → 注入 constitution:v1 coeffect，每次执行必保

1. 必须……（命令式、可判定真伪）

## 人格
> 本分区 → 写入 L0 记忆层

- 身份：
- 工作风格：
- 沟通风格：
- 决策偏好：
- 边界意识：
```

项目级 `<project>/Core.md` 模板：

```markdown
<!-- Core Profile · 项目级（<project>/Core.md）· 载入项目时读取 -->
## 项目信息
> 本分区 → 注入 ContextEngine 上下文

- 项目：
- 技术栈：
- 文档真源：
- 目录约定：
- 关键约束：
```

---

## 4. 与上下文/记忆的分工

| 层 | 职责 |
|---|---|
| CoreProfileEngine | 读取/解析/合并/注入灵魂文件预设 |
| constitution:v1 coeffect | 宪法与全局规则注入（必保约束） |
| L0 记忆层 | 人格承载（元策略与人格预设） |
| ContextEngine | 项目信息注入窗口（cwd 向上查找） |

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 全局级/项目级 Core.md 缺失 | 静默降级，按无该级别预设继续运行，不报错 |
| 分区标记格式非法或无法解析 | 记录告警并跳过非法分区，加载其余合法分区，不阻断启动或载入 |
| 同名配置项冲突 | 项目级覆盖全局级 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/core-profile-interface.md`
- 规格：`doc/openspec/specs/core-profile/spec.md`
- 测试：`doc/04-testing/test-cases.md`（CP 系列）
