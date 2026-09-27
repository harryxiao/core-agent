# Tasks

## 1. Core.md 文件格式与分区解析（P0）

- [x] 1.1 定义 Core.md 双语义分区语法（宪法/全局规则 vs 人格），分区语义落 spec（分区标记语法留待实现阶段确定）
- [x] 1.2 实现 Core.md 解析器，按分区标记切分内容并产出结构化 CoreProfile

## 2. 全局级加载（P0）

- [x] 2.1 Agent 启动时读取 `~/.core/Core.md`（人格/宪法/全局规则）
- [x] 2.2 将宪法/全局规则注入 constitution:v1 coeffect，人格注入 L0 记忆层

## 3. 项目级加载（P0）

- [x] 3.1 ContextEngine 按 cwd 向上查找 `<project>/Core.md`（项目信息）
- [x] 3.2 载入项目时注入 context，项目级条目覆盖全局级同键条目

## 4. 与 CLAUDE.md 并存分工（P1）

- [x] 4.1 Core.md 承载人格/宪法/项目信息，CLAUDE.md 保留现有项目记忆语义位，二者职责边界写入文档
- [x] 4.2 二者并存互不加载，Core-Agent 仅读取 Core.md 作为自身预设

## 5. 校验与容错（P1）

- [x] 5.1 缺失 Core.md 时静默降级（不报错、不影响启动）
- [x] 5.2 格式错误/分区标记不完整时告警并跳过非法分区，保留合法分区
