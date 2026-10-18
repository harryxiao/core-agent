## ADDED Requirements

### Requirement: 里程碑报告锚定（milestone anchoring）

系统 SHALL 提供**确定性、零 LLM 调用**的「里程碑报告」路径：由**调用方（CLI / 上层）显式触发**，
把阶段收口的结论、关键决策、硬约束与关键事实装配为**一篇** canonical 笔记，并**置常驻**
（`pinned=True`）＋ **高 `pin_priority`**（缺省 `100`，可由调用方覆盖）⇒ 复用既有「常驻（pinned）
笔记」通道（整篇纳入 / 逐轮无条件注入 / 优先级决定在场），SHALL NOT 新增第二注入块、SHALL NOT
改变 loop 与 prompt 装配。

报告正文 SHALL 按**固定节次序**装配：**结论** → **关键决策** → **硬约束** → **关键事实**；
空节 SHALL **整节省略**。数据来源 SHALL 为以下**可选且可组合**的输入：调用方显式给出的结论 /
决策 / 硬约束条目；`session_id` 对应的记忆压实摘要（正文并入「结论」节）；该会话的 keyfact
条目（`key_fact` 标签且含 `session:<session_id>`，按条目 `id` 升序 ⇒ 确定性输出）。报告 SHALL NOT
引入任何模型调用与任何自动归纳。

`note_id` SHALL 由里程碑名**确定性派生**（`milestone-` + `slug_topic(<name>)`），SHALL 允许调用方以
**显式 `note_id`**（`--as`）覆盖。写入 SHALL 为**幂等覆盖**：同一里程碑重复收口 SHALL 命中**同一**
note、SHALL NOT 产生第二条；SHALL 复用**既有唯一写路径** `NoteStore.update()`（SHALL NOT 另开第二
写路径）。派生 `note_id` 为空且未给显式 id、或**全部内容为空**（无显式条目、无摘要、无 keyfact）
⇒ SHALL **不写盘**、SHALL 以**非零退出码**报错（SHALL NOT 新增 `notes` 错误码）。

报告 SHALL 受**来源守护**：当目标 `note_id` 撞上**来源非** `notes.milestone` 的既有笔记、且调用方
**未**显式给出 `--as` 时，SHALL **不写盘**、SHALL 返回空、SHALL 以**非零退出码**报错。调用方**显式**
给出 `--as <note_id>` ⇒ 视为**显式授权**，SHALL 照常覆写。既有笔记的 tags SHALL 并入产出（保留手工
标签），标题在调用方未给出时 SHALL 沿用既有标题。

报告正文 SHALL **有界且脱敏**：所有装配内容 SHALL 先经**同一份**密钥脱敏（`redact_secrets`，承
ADR-0141①）；装配后正文 SHALL 不超过模块常量 `MAX_MILESTONE_CHARS`（缺省 **3000** 字符，小于常驻
总预算 `_MAX_PINNED_CHARS` 4000）。超限时 SHALL **保留头部**并留下截断标记（含被截字符数），
SHALL NOT 静默截断。

里程碑产出的笔记 SHALL 属**全局文档层**，SHALL NOT 参与会话隔离（`session_id` 仅是内容来源与
`note_id` 的派生输入）。写入 SHALL **不接** `EffectTracker`（承 canonical 文档层既有取舍）。
该路径 SHALL **仅**由显式触发（SHALL NOT 由「跑了一轮 loop」「会话压实」等事件自动触发）——
自动置常驻与 ADR-0142① / ADR-0141① 冲突，属**明确否决**项。

CLI SHALL 暴露 `notes milestone <name> [--session <session-id>] [--as <note_id>] [--title <title>]
[--priority <n>] [--conclusion <text>]... [--decision <text>]... [--constraint <text>]...`；
无可写内容 / 派生 id 为空 / 来源冲突 ⇒ SHALL 报错且退出码非零、SHALL NOT 写任何文件。

#### Scenario: 一键生成结构化报告并置常驻
- **GIVEN** 一个里程碑名与显式给出的结论 / 决策 / 硬约束条目
- **WHEN** `notes milestone <name> --conclusion ... --decision ... --constraint ...`
- **THEN** canonical 目录新增**一篇** note（`source == "notes.milestone"`），正文含固定次序的
  结论 / 关键决策 / 硬约束三节及对应条目，且 `pinned == True`、`pin_priority == 100`

#### Scenario: 幂等覆盖（重复收口不增长）
- **GIVEN** 已收口一次
- **WHEN** 以**同一**里程碑名再次收口（内容不同）
- **THEN** 仍**只有一条**该里程碑 note、正文为第二次内容、`updated_at` 递增

#### Scenario: 从会话摘要与关键事实装配
- **GIVEN** 某会话已有压实摘要与若干 keyfact 条目（`session:<id>` 标签）
- **WHEN** `notes milestone <name> --session <id>`
- **THEN** 摘要正文出现在「结论」节、keyfact 条目按 `id` 升序出现在「关键事实」节；重复收口
  输出**逐字稳定**（确定性）

#### Scenario: 无内容 ⇒ 不写盘 + 非零退出
- **GIVEN** 既无显式条目、又无 `--session`（或该会话无摘要与 keyfact）
- **WHEN** `notes milestone <name>`
- **THEN** **不写任何文件**、退出码非零

#### Scenario: 派生 id 为空 ⇒ 不写盘 + 非零退出
- **GIVEN** 里程碑名不产生任何可保留字符（`slug_topic` 为空）且未给 `--as`
- **WHEN** `notes milestone "!!!" --conclusion X`
- **THEN** **不写任何文件**、退出码非零

#### Scenario: 来源守护与显式授权
- **GIVEN** canonical 目录已有一篇来源**非** `notes.milestone` 的笔记，其 `note_id` 恰等于
  某里程碑的派生 id
- **WHEN** `notes milestone <name>`（**不给** `--as`）
- **THEN** **不写任何文件**（该笔记正文逐字不变）、退出码非零；**AND GIVEN** 显式给出 `--as <id>`
- **THEN** 视为授权，照常覆写为里程碑报告

#### Scenario: 有界与脱敏
- **GIVEN** 显式条目中含密钥形态文本，且装配后正文超过 `MAX_MILESTONE_CHARS`
- **WHEN** 收口
- **THEN** canonical 正文**不含**密钥原文（出现 `REDACTED`），总长不超过上限，且头部内容保留、
  截断处有含字符数的标记

#### Scenario: 优先级高于普通常驻（在场次序）
- **GIVEN** 一篇人工常驻笔记（`pin_priority == 0`）与一篇里程碑报告（缺省优先级）
- **WHEN** `pinned()` / prompt 常驻块装配
- **THEN** 里程碑报告**先于**人工常驻笔记（优先级降序）；**AND GIVEN** 以 `--priority 0` 收口
- **THEN** 该篇按普通常驻优先级参与排序

#### Scenario: 不自动触发、不新增注入块（设计裁决护栏）
- **GIVEN** 跑一轮触发压实的 loop，以及任何非显式调用路径
- **WHEN** 该轮结束
- **THEN** canonical 目录**不出现**任何由里程碑路径自动产生的 note；里程碑产出**只**经既有
  「常驻笔记」块注入（无第二个注入块、prompt 结构逐字不变）
