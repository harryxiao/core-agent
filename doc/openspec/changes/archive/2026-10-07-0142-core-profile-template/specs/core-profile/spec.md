## MODIFIED Requirements

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
