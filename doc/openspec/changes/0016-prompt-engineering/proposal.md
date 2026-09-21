# Change: Core.md 题词工程（题词规范 + 题词模板）

## Why

change 0015 已落地两级 Core Profile 的文件格式与加载行为，但只有「文件能解析、能加载」的骨架，缺少「如何写好这份文件」的编写指导：用户拿到两级 Core.md 后不知道宪法/人格/项目信息各分区该怎么写——宪法条目应写成什么句式才能被 constitution:v1 coeffect 可靠执行、人格应覆盖哪些维度才能有效塑造行为、项目信息与全局规则如何避免重复、篇幅如何控制。没有题词规范与模板，用户产出的 Core.md 质量参差：宪法可能写成不可判定的散文导致约束失效，人格可能冗长稀释 L0 记忆层，上下文窗口被无谓占用。本 change 补齐编写侧的题词规范与题词模板。

## What Changes

- 扩展 `core-profile` capability：新增「题词规范」——指导用户以可判定、可注入的方式编写各分区内容
- 扩展 `core-profile` capability：新增「题词模板」——全局级/项目级两级骨架，引导三段式填写，附注入说明注释

## Impact

- **Affected specs**：扩展 `core-profile`（追加 R6 题词规范、R7 题词模板）
- **Affected docs**：`02-modules/core-profile.md`（模块文档追加 §3.5 题词技法、§3.6 题词模板）
- **Affected code**：无（本 change 声明编写规范与模板，不涉及运行时行为）
- **Dependencies**：复用 change 0015 的 `core-profile` 文件格式与双语义分区；对齐 `constitution:v1` coeffect、`memory` L0 记忆层、`context` 注入通道
