# notes Specification Delta — 提升产物退出 Consult 命中面（语义记忆去重）

## MODIFIED Requirements

### Requirement: Consult → Build → Update 循环纪律

系统 SHALL 提供内置技能 `skills.notes.consult_build_update`（注册进 `SkillLibrary`），其
`instructions` SHALL 非空且**同时**承载「任务前先 Consult」与「任务后 Update」两段纪律。loop SHALL
提供**任务前 Consult 钩子**与**任务后 Update 钩子**：前者确定性读 `NoteStore.consult(query)` 命中的
note + `NoteStore.list()` 清单，作为「相关笔记」块注入本轮推理上下文（**不自动全量注入**）；后者在
**成功轮**把新结论**覆盖式**写回对应主题的 canonical 文件。loop SHALL NOT import `notes`（架构红线），
两枚钩子 SHALL 由组合根注入。

Consult 的**命中节选面** SHALL 排除**归档来源**笔记（`source` 属归档来源集合，当前为提升产物
`notes.promote`，见 Requirement「会话摘要提升（promotion）」）：此类笔记 SHALL NOT 出现在「命中的笔记」
节选中——其正文**已由**记忆侧「历史摘要（长期）」块（`memory`「记忆压实」的会话摘要）每轮注入，
同一份内容 SHALL NOT 经两条通道重复注入同一次请求。归档来源笔记 SHALL 仍以**「笔记清单」标题 + `note_id`**
在场（存在性可见）；其正文 SHALL 只经**显式常驻通道**（`pinned=True`，承 Requirement「常驻（pinned）笔记」）
或 canonical 真相层（人工 `notes show` / 编辑）触达。该排除 SHALL **只**落在 `digest` 注入面：
`consult` / `search` / `list` 的检索语义 SHALL **逐字不变**（CLI `notes search` 仍可检索到归档来源笔记）；
**非**归档来源笔记的命中节选 SHALL 逐字不变。

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

任务后写回 SHALL 受**效应闸门**（change `0176`）：本轮行动序列中**不含任何写效应工具动作**（轮内
未产生持久化效应——仅含纯读型工具如 `web_fetch` / `file_read`，或写效应动作**失败**）时，写回
SHALL **不落盘**（返回空），SHALL NOT 为该轮创建或覆写任何笔记。纯读型工具产出的内容属**素材**，
归 memory 侧 keyfact 抽取路径沉淀，不进 canonical notes（刻意知识层）。写效应判据 SHALL 为
**确定性**的（按行动序列中的工具名匹配写效应工具集——文件系统写 / 代码执行成功 / 质量门禁通过 /
插件安装卸载），SHALL NOT 引入 LLM 评分（与 ADR-0045 依赖方向一致）。

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

#### Scenario: 纯读轮不写回（效应闸门）
- **GIVEN** 一轮任务成功完成，行动序列**仅含纯读型工具动作**（如 `web_fetch` / `file_read`，
  无任何写效应动作）
- **WHEN** 收尾钩子触发任务后写回
- **THEN** 写回**不落盘**（返回空），canonical 目录**无新增文件**、既有文件**逐字不变**——
  纯读产出的事实属素材，归 memory 侧 keyfact 抽取沉淀

#### Scenario: 写效应失败不计入（效应闸门失败口径）
- **GIVEN** 一轮任务成功完成（`ok=True`），行动序列含 `code_run` 动作但其结果为**失败**
  （行含 `错误：` 前缀）
- **WHEN** 收尾钩子触发任务后写回
- **THEN** 写回**不落盘**——只沉淀**验证过的**行动与结果，失败执行不构成可沉淀效应

#### Scenario: 含写效应轮正常写回
- **GIVEN** 一轮任务成功完成，行动序列含至少一个**成功的**写效应工具动作
  （如 `file_write` / `code_run` 成功 / `gate_run` 通过）
- **WHEN** 收尾钩子触发任务后写回
- **THEN** 写回落盘（覆盖式，来源守护与派生主题逻辑**逐字不变**），正文含本轮行动序列

#### Scenario: 命中面排除归档来源（提升产物以清单标题在场）
- **GIVEN** canonical 目录含一篇提升产物（`source == "notes.promote"`）与一篇普通笔记
  （`source == "notes"`），二者正文都与本轮任务词法相关
- **WHEN** loop 装配「相关笔记」块（`digest`）
- **THEN** 「命中的笔记」节选**只含普通笔记**的节选；提升产物**不进**命中节选（其正文不注入本轮请求），
  但**仍在**「笔记清单」中以标题 + `note_id` 在场；**AND** 同一 query 下
  `consult()` / `search()` / `list()` 对提升产物的结果**逐字不变**（排除只在 `digest` 注入面）

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
自动置常驻（半自动产出的定位是**归档留档物**：其正文 SHALL NOT 注入 prompt —— 不进 Consult 命中节选
（承 Requirement「Consult → Build → Update 循环纪律」的**归档来源排除面**），只以「笔记清单」标题在场、
**不**占常驻预算；正文经 canonical 真相层（人工 `notes show` / 编辑）触达，操作者**显式** `pin` 后
可由常驻通道在场）。提升的 note SHALL 属**全局文档层**，SHALL NOT 参与会话隔离——`session_id` 仅是
**`note_id` 的派生输入**与来源标注，**不是**隔离维度。提升写入 SHALL **不接** `EffectTracker`
（承 canonical 文档层既有取舍）。

提升产出的注入面 SHALL 为**单通道**：置常驻者只经「常驻笔记」块（**完整正文**）、不置常驻者**不经**
prompt 正文——**无论** `pinned` 与否，提升产物 SHALL NOT 进 Consult 命中节选（同一篇 SHALL NOT 同时
在两条通道出现）；该会话的摘要正文在 prompt 侧的**承载者** SHALL 为记忆侧「历史摘要（长期）」块
（`memory`「记忆压实」），本路径 SHALL NOT 引入第二条正文通道。

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

#### Scenario: 半自动提升产物不进命中节选（只以清单标题在场）
- **GIVEN** 半自动提升落下一篇该会话 note（`source == "notes.promote"`、`pinned is False`），
  且其正文与某任务词法相关
- **WHEN** 该任务轮装配「相关笔记」块（`digest`）
- **THEN** 「命中的笔记」节选**不含**其正文；其标题 + `note_id` **仍在**「笔记清单」中；
  **AND** 该会话摘要的 prompt 正文**仍由**「历史摘要（长期）」块承载（唯一正文通道，逐字不变）

#### Scenario: 提升产物置常驻也不进命中节选（通道分列）
- **GIVEN** 一篇提升产物已置常驻（`pinned=True`），其正文长于 `_MAX_EXCERPT_CHARS`(200)
- **WHEN** 装配本轮推理上下文
- **THEN** 「常驻笔记（任务级硬约束…）」块含其**完整正文**，而「相关笔记」块**不含**其节选——
  同一篇提升产物 SHALL NOT 同时在两条通道出现
