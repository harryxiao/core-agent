# Design

## Context

Core-Agent 需要一份可声明式配置的「灵魂」预设：定义 Agent 的人格、宪法、全局规则，并按项目叠加项目信息。现状锚点分散——宪章仅 `constitution:v1` coeffect 一个锚点（无独立 spec），记忆 L0 是元策略非人格，项目信息由 `composition` profile/bundle/patch.yml 承载（无 project 语义），根 `CLAUDE.md`（72 行）已占据项目记忆语义位。本 design 引入两级 Core.md 补齐人格/宪法/项目信息的声明式载体，并与 CLAUDE.md 并存分工。

## Decisions

- **两级文件**：全局 `~/.core/Core.md`（人格/宪法/全局规则，Agent 启动读取）；项目 `<project>/Core.md`（项目信息，载入项目读取）。
- **双语义分区**：`~/.core/Core.md` 内部按分区标记切分——宪法/全局规则注入 `constitution:v1` coeffect，人格注入 L0 记忆层，二者语义不混淆。
- **项目级挂载**：`<project>/Core.md` 由 ContextEngine 按 cwd 向上查找并注入 context，复用现有上下文装配链，不新增 project 维度（轻量）。
- **与 CLAUDE.md 并存**：Core.md 承载人格/宪法/项目信息，CLAUDE.md 保留现有项目记忆语义位；二者并存互不加载，Core-Agent 仅读取 Core.md 作为自身预设。

## Risks / Trade-offs

- **CLAUDE.md 语义冲突**：根 CLAUDE.md 已占项目记忆语义位，需在文档中明确二者职责边界，避免同名配置二义。
- **L0 / 宪章 / 人格边界**：记忆 L0 原为元策略，接入人格后需区分「元策略 / 宪章 / 人格」三层语义，防止人格规则被当作元策略执行。
- **挂载链路缺失**：Core.md 需要「读取 + 装配」双链路（启动读取 + 运行时注入），二者缺一都会导致配置不生效。
- **project 概念缺失**：现有项目载入为 profile/bundle 而非 project 语义，项目级 Core.md 的查找与覆盖需明确与 profile 的关系。
- **deepseek 上下文窗口**：人格/宪法/项目信息常驻注入会增加上下文占用，需约束 Core.md 规模并支持按需裁剪。

## Open Questions

- Core.md 分区标记的具体语法（markdown 标题 / 显式标记行）留待实现阶段（编码）确定。
- 项目级 Core.md 查找上限（是否跨出 git 根 / 家目录）与多项目嵌套的最近优先规则细节。
- 是否支持环境变量覆盖 Core.md 路径（如 `CORE_PROFILE_PATH`），首期是否内置。
