# Core Profile Specification

## Purpose

Core Profile（灵魂文件）让 Core-Agent 具备可预设的人格、宪法与全局规则：通过两级 Core.md（全局级 `~/.core/Core.md` 与项目级 `<project>/Core.md`）在启动与载入项目时分别塑造 Agent 的行为特色与约束，采用双语义分区（宪法与全局规则→constitution:v1 coeffect 注入，人格→L0 记忆层），项目级按 cwd 向上查找注入上下文，与 CLAUDE.md 分工并存。并提供题词规范与题词模板，指导用户以可判定、可注入的方式编写各区内容。

## Requirements

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

### Requirement: 题词规范
系统 SHALL 提供 Core.md 的题词编写规范，指导用户以可判定、可注入的方式编写各分区内容：宪法与全局规则分区采用命令式可判定句式（每条以「必须/禁止」表述、可判定真伪，不承载具体操作细节），人格分区采用结构化描述（身份/工作风格/沟通风格/决策偏好/边界意识），项目信息分区仅承载项目特有信息且不重复全局规则，单个 Core.md 篇幅受控（建议不超过 50 行，细节下沉 L2/L3 记忆层）。

#### Scenario: 宪法分区命令式可判定
- **GIVEN** 用户编写全局级 Core.md 的「宪法与全局规则」分区
- **WHEN** 参照题词规范书写规则条目
- **THEN** 每条规则以命令式「必须/禁止」表述且可判定真伪，不承载具体操作细节，可直接作为 constitution:v1 coeffect 注入执行

#### Scenario: 人格分区结构化与篇幅受控
- **GIVEN** 用户编写人格分区或项目信息分区
- **WHEN** 参照题词规范填写
- **THEN** 人格以「身份/工作风格/沟通风格/决策偏好/边界意识」结构化描述，项目信息仅写项目特有信息且不重复全局规则，整体篇幅受控

### Requirement: 题词模板
系统 SHALL 提供 Core.md 题词模板（骨架），引导用户按「宪法与全局规则/人格/项目信息」三段式结构填写两级文件：全局级模板含「宪法与全局规则」「人格」两个分区，项目级模板含「项目信息」分区，模板附分区注入说明注释，注明各分区内容落向的运行时通道。模板 SHALL 以仓库内**可直接复制**的骨架文件形式产出：`templates/Core.global.md`（落向 `~/.core/Core.md`）与 `templates/Core.project.md`（落向 `<project>/Core.md`）；两份骨架的分区标题 SHALL 与运行时解析器约定的标记**逐字一致**（`## 宪法与全局规则` / `## 人格` / `## 项目信息`），且每个分区 SHALL 含可被解析器接受的内容行 —— 复制后按 `SectionParser` + `Validator` 解析 SHALL NOT 产生 `SECTION_INVALID` 告警（标题未被识别或分区为空都会落该告警并被跳过）。

#### Scenario: 全局级模板产出
- **GIVEN** 用户新建全局级 `~/.core/Core.md`
- **WHEN** 参照全局级题词模板填写
- **THEN** 产出含「宪法与全局规则」「人格」两个分区的文件，分区内容分别落向 constitution:v1 coeffect 与 L0 记忆层

#### Scenario: 项目级模板产出
- **GIVEN** 用户新建项目级 `<project>/Core.md`
- **WHEN** 参照项目级题词模板填写
- **THEN** 产出含「项目信息」分区的文件，分区内容落向 ContextEngine 注入上下文

#### Scenario: 骨架复制即被解析器接受
- **GIVEN** 仓库内 `templates/Core.global.md` 与 `templates/Core.project.md` 两份骨架文件
- **WHEN** 以其**原文**（未改写）分别运行 `SectionParser` + `Validator`
- **THEN** 全局骨架产出 `constitution` 与 `personality` 两个合法分区、项目骨架产出 `project_info` 合法分区，**两者均无 `SECTION_INVALID` 告警**（分区标题逐字一致且分区非空）
