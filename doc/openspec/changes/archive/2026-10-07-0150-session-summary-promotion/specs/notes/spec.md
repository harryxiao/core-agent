## ADDED Requirements

### Requirement: 会话摘要提升（promotion）

系统 SHALL 提供**确定性**「会话摘要 → canonical note」提升路径：由**调用方（CLI / 上层）显式触发**，
SHALL NOT 由 loop 压实**自动**触发、SHALL NOT 依赖模型自觉（对比既有仅靠技能纪律
`skills.notes.consult_build_update` 的路径）。该路径 SHALL NOT 引入任何 LLM 调用。

提升的 `note_id` SHALL 由 `session_id` **确定性派生**（前缀 + `slug_topic(session_id)`）；SHALL 允许调用方以
**显式 `note_id`** 覆盖派生结果。提升 SHALL 为**幂等覆盖**：同一会话重复提升 SHALL 命中**同一** note、
SHALL NOT 产生第二条；SHALL 复用**既有唯一写路径** `NoteStore.update()`（SHALL NOT 另开第二写路径）。
会话**无可提升摘要**、或派生 `note_id` 为空且未给显式 `note_id` ⇒ SHALL **不写盘**、SHALL 以**非零退出码**
报错（SHALL NOT 新增 `notes` 错误码）。

提升产出的 note SHALL **置 `pinned=True`**（每轮无条件注入；承 Requirement「常驻（pinned）笔记」）。
提升的 note SHALL 属**全局文档层**，SHALL NOT 参与会话隔离——`session_id` 仅是 **`note_id` 的派生输入**与
来源标注，**不是**隔离维度。提升写入 SHALL **不接** `EffectTracker`（承 canonical 文档层既有取舍）。

CLI SHALL 暴露 `notes promote <session-id> [--as <note_id>] [--title <title>]`；会话无摘要或派生 id 为空
⇒ SHALL 报错且退出码非零。

#### Scenario: 提升落 canonical 且可读回
- **GIVEN** 某会话已有压实摘要（`compaction.summary.<session-id>`）
- **WHEN** `notes promote <session-id>`
- **THEN** canonical 目录新增一篇 note，`notes show` 打印其正文含摘要内容、`source == "notes.promote"`、
  且 `pinned == True`

#### Scenario: 幂等：重复提升单条覆盖
- **GIVEN** 已提升一次
- **WHEN** 再次提升**同一**会话
- **THEN** 仍**只有一条**该会话 note、内容为第二次（覆盖式）、`updated_at` 递增

#### Scenario: note_id 确定性派生 + 显式覆盖
- **GIVEN** 同一 `session_id`
- **WHEN** 两次提升（不给显式 id）
- **THEN** 落到**同一** `note_id`（前缀 + `slug_topic(session_id)`）；**AND GIVEN** 给 `--as <x>`
- **THEN** 落到 `<x>`

#### Scenario: 无摘要 / 空 slug ⇒ 不写盘 + 非零退出
- **GIVEN** 会话无摘要（或 `slug_topic(session_id)` 为空且未给显式 `note_id`）
- **WHEN** `notes promote`
- **THEN** **不写任何文件**、退出码非零

#### Scenario: 提升后对任意会话可见（全局层护栏）
- **GIVEN** 提升产出一篇 note
- **WHEN** 在**不同**会话上下文 Consult
- **THEN** 命中集相同（非会话私有；承「刻意知识不参与隔离」）

#### Scenario: 不自动触发（设计裁决护栏）
- **GIVEN** 跑一轮触发压实的 loop
- **THEN** canonical 目录**不出现**任何由提升自动产生的 note（提升仅由显式调用触发）
