# Change: Core.md 灵魂预设（两级 Core Profile）

## Why

Core-Agent 目前缺少「灵魂」级的人格预设载体：业界主流 Agent（OpenClaude 等）都提供一份定义 Agent 人格/宪法/全局规则的全局 md（俗称「灵魂 md」），而 Core-Agent 现状是——宪章仅有一个锚点 `constitution:v1` coeffect（`loop/protocol.py`，无独立 spec），记忆 L0 承载的是元策略而非人格，全仓无 Core.md / persona / 人格类文件。用户希望 Core-Agent 也具备同类的 md 预设能力：

- 全局 `~/.core/Core.md`：定义人格、宪法、全局规则，Agent 启动时读取；
- 项目 `<project>/Core.md`：定义项目信息，载入项目时读取。

缺失该能力会导致 Core-Agent 无法像同类产品一样通过一份文件刻画「这个 Agent 是谁、遵循什么、如何行事」，个性与规则散落在代码与宪章 coeffect 中，无法由用户以声明式 md 配置。

## What Changes

- 新增 `core-profile` capability：Core.md 文件格式规范（双语义分区：宪法/全局规则、人格），以及两级加载（全局 + 项目）与合并优先级
- 扩展 `context` capability：项目级 Core.md 由 ContextEngine 按 cwd 向上查找并注入上下文（项目信息）
- 扩展 `memory` capability：L0 记忆层承载人格；全局宪法/全局规则注入 `constitution:v1` coeffect
- 与 CLAUDE.md 并存分工：Core.md 承载人格/宪法/项目信息，CLAUDE.md 保留现有项目记忆语义位，二者职责边界写入文档，并存互不加载（Core-Agent 仅读取 Core.md 作为自身预设，不加载 CLAUDE.md）

## Impact

- **Affected specs**：新建 `core-profile`；扩展 `context`（项目级 Core.md 注入）、`memory`（L0 人格承载 + constitution 来源）
- **Affected docs**：`02-modules/core-profile.md`（模块文档）、`03-interfaces/core-profile-interface.md`（接口文档）、根 `CLAUDE.md`（与 Core.md 分工说明）
- **Affected code**：无（本 change 声明 Core.md 行为，具体实现由后续步骤确定）
- **Dependencies**：复用 `constitution:v1` coeffect（`loop/protocol.py`）、`memory` L0 记忆层、`composition` profile/bundle 载入链
