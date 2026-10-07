## MODIFIED Requirements

### Requirement: 会话摘要提升（promotion）

系统 SHALL 提供**确定性**「会话摘要 → canonical note」提升路径：由**调用方（CLI / 上层）显式触发**，
或由 **memory 压实侧在会话摘要首次越过滚动上界时**（见下「半自动触发」）**半自动**触发；SHALL NOT 依赖
模型自觉（对比既有仅靠技能纪律 `skills.notes.consult_build_update` 的路径）。该路径 SHALL NOT 引入任何
LLM 调用。

提升的 `note_id` SHALL 由 `session_id` **确定性派生**（前缀 + `slug_topic(session_id)`）；SHALL 允许调用方以
**显式 `note_id`** 覆盖派生结果。提升 SHALL 为**幂等覆盖**：同一会话重复提升 SHALL 命中**同一** note、
SHALL NOT 产生第二条；SHALL 复用**既有唯一写路径** `NoteStore.update()`（SHALL NOT 另开第二写路径）。
会话**无可提升摘要**、或派生 `note_id` 为空且未给显式 `note_id` ⇒ SHALL **不写盘**、SHALL 以**非零退出码**
报错（SHALL NOT 新增 `notes` 错误码）。

提升 SHALL 受**来源守护**：当目标 `note_id` 撞上**来源非** `notes.promote` 的既有笔记、且调用方
**未**显式给出显式 `note_id`（`--as`）时，提升 SHALL **不写盘**、SHALL 返回空、SHALL 以**非零退出码**
报错（与「无摘要 / 空 slug」**同口径**，SHALL NOT 新增 `notes` 错误码）。调用方**显式**给出
`--as <note_id>` ⇒ 视为**显式授权**，SHALL 照常覆写（**不**受来源守护约束）。

提升产出的 note SHALL 置 `pinned=True`（每轮无条件注入；承 Requirement「常驻（pinned）笔记」）——
该**自动置常驻**语义 SHALL **仅**适用于**显式路径**；**半自动路径** SHALL 以 `pin=False` 提升、SHALL NOT
自动置常驻（半自动产出是**普通** canonical 笔记：只经 Consult 命中面与 digest 注入，**不**占常驻预算）。
提升的 note SHALL 属**全局文档层**，SHALL NOT 参与会话隔离——`session_id` 仅是 **`note_id` 的派生输入**与
来源标注，**不是**隔离维度。提升写入 SHALL **不接** `EffectTracker`（承 canonical 文档层既有取舍）。

**半自动触发的判据与频次** SHALL 严格限定：仅当 **memory 压实**发现该会话摘要**首次越过**滚动上界
（既有摘要长度 ≤ 上界而本次产出摘要长度 > 上界；见 `memory`「记忆压实」）时，由 memory 侧**注入的提升
钩子**交付**一次**；**已越过**上界的会话 SHALL NOT 重复交付（避免以**已稀释**的后继摘要覆写上一层已保存
的完整内容）。钩子 UNWIRED（缺省）⇒ SHALL NOT 交付、行为与变更前逐字一致。半自动路径 SHALL 复用本
Requirement 的**全部**既有约束（幂等覆盖 / 唯一写路径 / 确定性派生 / 来源守护 / 不引 LLM）。

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
- **GIVEN** 跑一轮触发压实的 loop，其会话摘要**未越过**滚动上界
- **THEN** canonical 目录**不出现**任何由提升自动产生的 note（半自动提升**仅**由「首次越过」滚动上界
  触发、且每会话**至多一次**，**不**由「跑了一轮压实」触发）

#### Scenario: 首次越界 ⇒ 半自动提升且不自动 pin
- **GIVEN** 某会话既有摘要长度不超过滚动上界，且 memory 侧已注入提升钩子
- **WHEN** 本次压实产出的摘要**首次越过**上界
- **THEN** canonical 目录新增**一篇**该会话 note（`source == "notes.promote"`、正文含摘要内容），
  且其 `pinned is False`（**不**占常驻预算，**不**每轮无条件注入）

#### Scenario: 已越界不再重复交付（一次语义）
- **GIVEN** 某会话摘要已越过上界（半自动提升已交付过）
- **WHEN** 该会话再次压实
- **THEN** canonical 目录仍**只有一篇**该会话 note，且其正文**不被**本次（已稀释的）后继摘要覆写

#### Scenario: 撞非 promotion 来源 ⇒ 拒绝且不写盘（来源守护）
- **GIVEN** canonical 目录已有一篇来源**非** `notes.promote` 的笔记（如人工撰写），
  其 `note_id` 恰等于某会话提升的派生 id（`session-<slug>`）
- **WHEN** `notes promote <session-id>`（**不给** `--as`）
- **THEN** **不写任何文件**（该笔记正文与标题逐字不变）、退出码非零
- **AND GIVEN** 同样情形但**显式给出** `--as <note_id>`
- **THEN** 视为显式授权，照常覆写为提升产出（`source == "notes.promote"`、`pinned == True`）
