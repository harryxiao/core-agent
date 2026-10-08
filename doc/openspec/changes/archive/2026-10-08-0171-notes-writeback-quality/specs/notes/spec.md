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

任务后写回 SHALL 受**有意义闸门**（change `0171`）：本轮行动序列**为空**（纯文字回复轮 —— 无任何
工具动作）时，写回 SHALL **不落盘**（返回空，与 `ok=False` / 空 slug 的既有跳过口径一致），SHALL NOT
为该轮创建或覆写任何笔记。

任务后写回的**正文 SHALL 为人类可读**（change `0171`）：`## 解决过程` 之下的每条行动 SHALL 以
可读形式呈现（工具名 + **有界**参数摘要 + **有界**结果节选），SHALL NOT 落 ReAct 消息**原文**
（助手动作的 `json.dumps({"tool_id":…})` / 工具观察的 `json.dumps({"data":…})`）或**整篇**工具输出；
正文长度 SHALL 有界（容器型参数只报类型与规模，正文参数不 dump）。此为 loop 侧 `turn_observer`
交付的行动序列（`steps`）的渲染契约，**同源**供 SOP 提炼消费。

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

#### Scenario: 纯文字回复轮不写回
- **GIVEN** 一轮任务成功完成，但本轮**无任何工具动作**（行动序列为空）
- **WHEN** 收尾钩子触发任务后写回
- **THEN** 写回**不落盘**，canonical 目录**无新增文件**、既有文件**逐字不变**

#### Scenario: 解决过程人类可读（不落原文）
- **GIVEN** 一轮含工具动作的任务成功完成
- **WHEN** 写回 canonical 文件
- **THEN** `## 解决过程` 之下为人类可读行（工具名 + 有界参数摘要 + 有界结果节选）
- **AND** 正文**不含** ReAct 消息原文（如 `{"tool_id"` / `{"data"` 形态的 JSON 转储），
  亦**不含**整篇工具输出（正文长度有界）
