Core Profile（灵魂文件）让 Core-Agent 具备可预设的人格、宪法与全局规则：通过两级 Core.md（全局级 `~/.core/Core.md` 与项目级 `<project>/Core.md`）在启动与载入项目时分别塑造 Agent 的行为特色与约束，采用双语义分区（宪法与全局规则→constitution:v1 coeffect 注入，人格→L0 记忆层），项目级按 cwd 向上查找注入上下文，与 CLAUDE.md 分工并存。（来源：exploration_findings.md，2026-09-21）

## ADDED Requirements

### Requirement: 两级 Core Profile 文件
系统 SHALL 支持两级 Core.md 灵魂文件：全局级 `~/.core/Core.md`（承载人格、宪法与全局规则）与项目级 `<project>/Core.md`（承载项目信息），使 Core-Agent 在启动与载入项目时分别读取对应级别的预设，塑造 Agent 的行为特色与约束。

#### Scenario: 全局级 Core.md 加载
- **GIVEN** 用户主目录下存在 `~/.core/Core.md`
- **WHEN** Core-Agent 启动
- **THEN** 系统读取并加载该文件的人格、宪法与全局规则预设

#### Scenario: 项目级 Core.md 加载
- **GIVEN** 某项目根目录下存在 `Core.md`
- **WHEN** Core-Agent 载入该项目
- **THEN** 系统读取并加载该文件的项目信息预设

### Requirement: 双语义分区
系统 SHALL 将 Core.md 内容划分为两个语义分区：「宪法与全局规则」分区承载以 constitution:v1 coeffect 注入的必保约束，「人格」分区承载 L0 记忆层的元策略与人格预设，两分区职责不重叠。

#### Scenario: 宪法分区注入 coeffect
- **GIVEN** Core.md 含「宪法与全局规则」分区
- **WHEN** 系统装配 LoopContext
- **THEN** 该分区内容作为 constitution:v1 coeffect 注入，作为必保约束参与执行

#### Scenario: 人格分区落 L0
- **GIVEN** Core.md 含「人格」分区
- **WHEN** 系统初始化记忆层
- **THEN** 该分区内容落入 L0 记忆层，作为元策略与人格预设参与决策

### Requirement: 项目级按 cwd 向上查找
系统 SHALL 支持 ContextEngine 在载入项目时从当前工作目录向上逐级查找 Core.md，将命中的项目级内容注入上下文，不新增 project 维度。

#### Scenario: 向上查找命中
- **GIVEN** 当前工作目录位于某项目子目录，项目根目录存在 Core.md
- **WHEN** ContextEngine 执行载入
- **THEN** 从 cwd 向上逐级查找并命中最靠近的项目根 Core.md，注入其项目信息

#### Scenario: 未命中项目级
- **GIVEN** cwd 向上到文件系统根均无 Core.md
- **WHEN** ContextEngine 执行载入
- **THEN** 不注入项目级内容，仅使用全局级预设，且不报错

### Requirement: 多级合并优先级
系统 SHALL 定义多级 Core.md 的合并优先级：项目级覆盖全局级（同名配置以项目级为准），CLAUDE.md 保留给外部 Claude Code，与 Core.md 分工并存不冲突。

#### Scenario: 项目级覆盖全局级
- **GIVEN** 全局级与项目级 Core.md 对同一配置项给出不同值
- **WHEN** 系统载入项目
- **THEN** 项目级值生效，覆盖全局级值

#### Scenario: 与 CLAUDE.md 分工
- **GIVEN** 仓库同时存在 CLAUDE.md（外部 Claude Code 项目记忆）与 Core.md（Core-Agent 运行时灵魂文件）
- **WHEN** Core-Agent 运行
- **THEN** 系统仅读取 Core.md 作为自身预设，不加载 CLAUDE.md，二者互不干扰

### Requirement: 校验与容错
系统 SHALL 对 Core.md 进行格式校验与容错：文件缺失时静默降级，格式非法时告警并跳过非法分区，不阻断启动或载入。

#### Scenario: 文件缺失静默降级
- **GIVEN** `~/.core/Core.md` 或项目级 Core.md 不存在
- **WHEN** 系统执行读取
- **THEN** 静默降级，按无该级别预设继续运行，不报错

#### Scenario: 格式非法告警跳过
- **GIVEN** Core.md 存在但分区标记格式非法或内容无法解析
- **WHEN** 系统解析该文件
- **THEN** 记录告警并跳过非法分区，加载其余合法分区，不阻断启动或载入

