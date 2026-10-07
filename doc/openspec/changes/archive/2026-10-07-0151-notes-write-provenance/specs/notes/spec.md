## MODIFIED Requirements

### Requirement: Consult → Build → Update 循环纪律

系统 SHALL 提供内置技能 `skills.notes.consult_build_update`（注册进 `SkillLibrary`），其
`instructions` SHALL 非空且**同时**承载「任务前先 Consult」与「任务后 Update」两段纪律。loop SHALL
提供**任务前 Consult 钩子**与**任务后 Update 钩子**：前者确定性读 `NoteStore.consult(query)` 命中的
note + `NoteStore.list()` 清单，作为「相关笔记」块注入本轮推理上下文（**不自动全量注入**）；后者在
**成功轮**把新结论**覆盖式**写回对应主题的 canonical 文件。loop SHALL NOT import `notes`（架构红线），
两枚钩子 SHALL 由组合根注入。

笔记层 SHALL 是**全局文档层**，SHALL NOT 参与会话隔离：Consult 与写入面 SHALL NOT 接受会话维度，
同一 query 在任意会话下的命中集 SHALL 相同——笔记是**被有意文档化的知识库**（刻意知识），
不是某一轮对话的残留，故按设计进全局层、跨会话共享。

任务后写回（`observe_turn`）SHALL 受**来源守护**：一条主题 SHALL 只由**产生它的那条写路径**覆写。
当任务主题（`slug_topic(task)`）撞上**来源非** `notes.turn` 的既有笔记（人工撰写 / promotion 产出 /
其他写路径）时，写回 SHALL NOT 覆写该主题的**正文与标题**；本轮沉淀 SHALL 改写入首个**不冲突**的
派生主题（`<topic>-<n>`，`n` 为 2 起、取首个「不存在或来源为 `notes.turn`」者）。既有笔记来源为
`notes.turn`（或该主题不存在）时，写回 SHALL 保持**覆盖式**、落到**同一**主题，且 SHALL 保留既有
`tags` 与 `pinned`（**逐字不变**）。来源守护 SHALL NOT 删除任何笔记、SHALL NOT 覆写任何**跨来源**正文。

#### Scenario: 任务前注入相关笔记
- **GIVEN** 组合根注入了 Consult 钩子，且 canonical 目录含与任务相关的 note
- **WHEN** loop 开始一轮任务
- **THEN** 命中的 note 内容与笔记清单确定性注入本轮推理上下文（同一输入产生同一 orientation）

#### Scenario: 笔记不参与会话隔离
- **GIVEN** canonical 目录含与某 query 相关的 note
- **WHEN** 分别在不同会话下以同一 query Consult
- **THEN** 两处命中集**相同**（Consult 面不接受会话维度，笔记为全局层）

#### Scenario: 任务后写回笔记
- **GIVEN** 一轮任务成功完成并产出新结论
- **WHEN** 收尾钩子触发
- **THEN** 对应主题的 canonical 文件内容含该新结论（覆盖式）

#### Scenario: 钩子故障不改本轮结局
- **GIVEN** Consult 或 Update 钩子内部抛错
- **WHEN** loop 执行该钩子
- **THEN** 故障降级留痕，本轮结果与终止语义不变

#### Scenario: 循环技能可被路由
- **GIVEN** 内置技能已注册进技能库
- **WHEN** 以文档化记忆相关任务路由
- **THEN** 命中 `skills.notes.consult_build_update`，其 `instructions` 含 Consult / Update 两段纪律

#### Scenario: 逐轮写回不覆写外来源笔记（来源守护）
- **GIVEN** canonical 目录含一篇来源**非** `notes.turn` 的笔记（人工撰写 / promotion 产出），
  其 `note_id` 恰等于 `slug_topic(task)`
- **WHEN** 一轮成功任务触发逐轮写回
- **THEN** 该笔记的**正文与标题逐字不变**（`source` / `pinned` 一并保留），本轮沉淀落在派生主题
  `<topic>-2` 中
- **AND GIVEN** 该既有笔记来源为 `notes.turn`
- **THEN** 仍**覆盖式**写回**同一**主题（既有行为逐字不变，保留 `tags` 与 `pinned`）

### Requirement: 会话摘要提升（promotion）

系统 SHALL 提供**确定性**「会话摘要 → canonical note」提升路径：由**调用方（CLI / 上层）显式触发**，
SHALL NOT 由 loop 压实**自动**触发、SHALL NOT 依赖模型自觉（对比既有仅靠技能纪律
`skills.notes.consult_build_update` 的路径）。该路径 SHALL NOT 引入任何 LLM 调用。

提升的 `note_id` SHALL 由 `session_id` **确定性派生**（前缀 + `slug_topic(session_id)`）；SHALL 允许调用方以
**显式 `note_id`** 覆盖派生结果。提升 SHALL 为**幂等覆盖**：同一会话重复提升 SHALL 命中**同一** note、
SHALL NOT 产生第二条；SHALL 复用**既有唯一写路径** `NoteStore.update()`（SHALL NOT 另开第二写路径）。
会话**无可提升摘要**、或派生 `note_id` 为空且未给显式 `note_id` ⇒ SHALL **不写盘**、SHALL 以**非零退出码**
报错（SHALL NOT 新增 `notes` 错误码）。

提升 SHALL 受**来源守护**：当目标 `note_id` 撞上**来源非** `notes.promote` 的既有笔记、且调用方
**未**显式给出显式 `note_id`（`--as`）时，提升 SHALL **不写盘**、SHALL 返回空、SHALL 以**非零退出码**
报错（与「无摘要 / 空 slug」**同口径**，SHALL NOT 新增 `notes` 错误码）。调用方**显式**给出
`--as <note_id>` ⇒ 视为**显式授权**，SHALL 照常覆写（**不**受来源守护约束）。

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

#### Scenario: 撞非 promotion 来源 ⇒ 拒绝且不写盘（来源守护）
- **GIVEN** canonical 目录已有一篇来源**非** `notes.promote` 的笔记（如人工撰写），
  其 `note_id` 恰等于某会话提升的派生 id（`session-<slug>`）
- **WHEN** `notes promote <session-id>`（**不给** `--as`）
- **THEN** **不写任何文件**（该笔记正文与标题逐字不变）、退出码非零
- **AND GIVEN** 同样情形但**显式给出** `--as <note_id>`
- **THEN** 视为显式授权，照常覆写为提升产出（`source == "notes.promote"`、`pinned == True`）
