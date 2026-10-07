# Notes Specification

## Purpose

为 Agent 提供**人类可读、可 diff、可 review 的文档化权威真相层**：按主题维护 canonical Markdown
文件（覆盖式更新、原子落盘、可 git diff），沿 **Consult → Build → Update** 循环运转。本层与既有
RAG 语义召回层（`MemoryStore` + `FileBackend`）**并列互补**——RAG 负责语义召回，notes 负责权威真相；
**不引入 RAG / embedding / 向量库**。

## Requirements

### Requirement: canonical Markdown 真相层与可插拔后端

系统 SHALL 提供 `NoteStore`（实现 Plugin 契约）与 `MarkdownBackend`（实现既有 `MemoryBackend`
Protocol 的 `get/put/search/list_index/delete`，**签名不改**）。note SHALL 以 **canonical Markdown
文件**落盘于**单一 canonical 目录**（可注入 `path`，缺省 `$CORE_STATE_DIR/notes`）；文件 SHALL
**自描述**（H1 标题 + 元数据行 + `## Search Queries` + 正文）且**人类可读**。`search` SHALL 为
**纯词法**打分（SHALL NOT 建向量库、SHALL NOT 引入 embedding），并 SHALL 对**语义浓缩字段加权**——
标题权重高于 tags 与 `## Search Queries`，后二者又高于正文（缺省 3× / 2× / 2× / 1×）——使**标题精确
命中**的主题排在**仅在正文顺带命中**的主题之前；命中判据（是否存在命中词）与 `search` 的返回结构、
`MemoryBackend` 契约 SHALL NOT 改变，加权**只影响排序**。

#### Scenario: 覆盖式更新
- **GIVEN** 同一主题已存在 canonical 文件
- **WHEN** 以新内容再次 `put` 该主题
- **THEN** 文件内容为**第二次**的内容（覆盖式），**不出现两段拼接**

#### Scenario: 原子写
- **GIVEN** 一次 `put` 写入
- **WHEN** 写入过程在替换前中断
- **THEN** canonical 文件不出现半截内容（先写临时文件、再 `os.replace`）

#### Scenario: 文件清单
- **GIVEN** canonical 目录下存在若干 note
- **WHEN** `list_index`
- **THEN** 返回全部 canonical 文件的 `IndexEntry` 清单

#### Scenario: 关键词命中
- **GIVEN** 某 note 的头部 `## Search Queries` 含关键词 K
- **WHEN** 以 K `search`
- **THEN** 命中该 note（标题 / tags / Search Queries 关键词匹配，**不建向量库**）

#### Scenario: 中文任务句命中
- **GIVEN** 某 note 的标题或关键词含「部署流程」
- **WHEN** 以无空格的中文任务句「部署流程怎么走」`search`
- **THEN** 命中该 note（CJK 按 **2-gram** 切词，不因缺词界空白而空手；英文/非 CJK 段保持整词包含）

#### Scenario: 语义浓缩字段优先（字段加权）
- **GIVEN** 两个 note 均含关键词 K：A 的**标题**含 K，B **仅在正文顺带**提及 K
- **WHEN** 以 K `search`
- **THEN** A 排在 B 之前（标题权重高于正文），二者**均被命中**（加权只改排序、不改过滤）
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

### Requirement: 结构化错误码与既有链路不变

读取不存在的 note SHALL 返回 `NOTE_NOT_FOUND`；对已存在主题**显式** `create` SHALL 返回
`TOPIC_EXISTS`（`ensure` 为幂等 get-or-create，不因已存在而报错）。本能力 SHALL NOT 改变
`MemoryStore` / `FileBackend` / RAG 链路语义，SHALL NOT 向 `plugin_registry` 引入外部插件装载路径。

#### Scenario: 读取不存在
- **GIVEN** canonical 目录无该 note
- **WHEN** `get`
- **THEN** 返回 `NOTE_NOT_FOUND`

#### Scenario: 显式创建已存在主题
- **GIVEN** 主题已存在
- **WHEN** 显式 `create`
- **THEN** 返回 `TOPIC_EXISTS`，既有内容不被覆盖

#### Scenario: 既有记忆链路未改
- **GIVEN** `notes` 已装配
- **WHEN** 走 `MemoryStore.read/write` 与 RAG 检索
- **THEN** 行为与装配前一致（两链路只并列、不交叉改写）

### Requirement: 常驻（pinned）笔记（任务级硬约束锚）

系统 SHALL 在 `NoteEntry` 提供布尔字段 `pinned`（缺省 `False`）与整数字段 `pin_priority`
（缺省 `0`）；canonical 元数据行 SHALL 为 `- pinned: true`（`pinned` 为 `False` 时该行 SHALL
**省略**）与 `- pin_priority: <n>`（`pin_priority` 为 `0` 时该行 SHALL **省略**）⇒ 既有 canonical
文件的渲染输出**逐字不变**（`render_note` / `parse_note` 仍互为逆）。`parse_note` SHALL 读回
`pinned` 行（大小写不敏感、接受 `true` / `yes` / `1` / `on` 等真值拼写）与 `pin_priority` 行（整数）；
**两处无法识别**的取值 SHALL 一律**不生效**（fail-closed：手误**绝不**意外把一个主题变成常驻、
也**绝不**意外把一个主题抬到高优先级）。

`NoteStore` SHALL 提供 `set_pinned(note_id, *, pinned=True, priority=0) -> NoteEntry`、
`pinned() -> list[NoteEntry]`、`pinned_digest() -> str` 与 `pinned_overflow() -> list[str]`。
目标 note 不存在 ⇒ SHALL 返回 `NOTE_NOT_FOUND`；`pinned` 与 `priority` **皆未变化** ⇒ SHALL NOT
写盘、SHALL NOT 变更 `updated_at`（幂等，不搅动「最新即权威」判据）；**清常驻**（`pinned=False`）
SHALL 同时把 `pin_priority` 归零（退出常驻面即不再有优先级）。既有逐轮写回（`observe_turn`）
SHALL NOT 抹除既有 `pinned` 与 `pin_priority`。

`pinned()` SHALL 按 **`pin_priority` 降序**、同优先级按 **`note_id` 升序**返回常驻笔记
⇒ 「谁在场」由**显式优先级**（操作者的决定）而非 `note_id` 字典序决定；次序**确定性**（同输入同
输出），使注入块跨轮稳定。

`pinned_digest()` SHALL 返回常驻笔记的**完整正文**（SHALL NOT 截为节选），按 `pinned()` 次序
**确定性**拼接，总长 SHALL **有界**（模块常量 `_MAX_PINNED_CHARS`，缺省 4000 字符）。装配 SHALL
**整篇纳入**：一篇常驻笔记要么**整篇**在场、要么**整篇**不在场，SHALL NOT 出现**半篇**（半截硬约束
可能语义反转，比缺席更危险）。预算不足以纳入下一篇**整篇**时，该篇 SHALL **整篇排除**，且其后的
常驻笔记 SHALL NOT 越过它挤入（在场集合 SHALL 是优先级次序的**前缀**）。**唯一例外**：次序**首篇**
（最高优先级）即便**自身**超预算 SHALL **整篇纳入** —— 常驻块 SHALL NOT 因单篇超限而整体为空
（硬约束全灭）。正文为空的常驻笔记 SHALL NOT 占块（既不纳入、也**不计**未进场）。无常驻笔记或正文
全空 ⇒ SHALL 返回空串。

预算超限 SHALL **可见**：`pinned_digest()` 在**注入块超预算**时（发生排除，**或**单篇超限致块超上界）
SHALL 经 `warnings.warn` 留痕（列出未进场 `note_id`；无整篇可排除时明示系单篇超限），
`pinned_overflow()` SHALL 返回被预算排除的 `note_id` 列表（次序同 `pinned()`；单篇超限的**首篇**
不在其列——它**在场**）——「谁没进场」不再静默。

loop SHALL 提供**任务前常驻注入钩子**（**无 query 入参**）——其产出 SHALL 写入
`LoopContext.pinned_notes`；`LLMPlanner` 在该字段非空时 SHALL 渲染为**独立块**，位置 SHALL
**紧随「宪法规则」块之后、「相关事实」块之前**。常驻注入 SHALL **逐轮无条件生效**，SHALL NOT
以 query 命中为条件。该语义 SHALL NOT 改变 Requirement「Consult → Build → Update 循环纪律」的口径：
`digest`（Consult）SHALL NOT 自动全量注入正文，且常驻笔记 SHALL NOT 折入「相关笔记」块——常驻注入是
**仅对显式标记 `pinned: true` 的笔记**开启的**独立通道**，不是对未标记笔记的全量注入。loop SHALL NOT
import `notes`（架构红线），钩子 SHALL 由组合根注入，且 SHALL 同时注入主 Agent、子 Agent 与神兽 loop。

常驻笔记 SHALL 属**全局文档层**，SHALL NOT 参与会话隔离：`pinned` / `pinned_digest` / `set_pinned` /
`pinned_overflow` SHALL NOT 接受会话维度。

常驻注入钩子抛错 SHALL 降级留痕（`pinned_notes_consult_failed`）、置空该块，且 SHALL NOT 改变本轮
结果与终止语义。

CLI SHALL 提供 `notes pin <note_id> [--priority <n>]`（置常驻并设优先级）、`notes unpin <note_id>`
与 `notes pinned`（列出常驻笔记：`note_id` / 标题 / 优先级 / **是否在场**）；缺失 id ⇒ SHALL 报
`NOTE_NOT_FOUND` 且退出码非零。`notes list` SHALL 以**追加列**标记常驻笔记，非常驻行输出 SHALL NOT
改变（`notes pinned` 是「未进场篇目」的**报出**面，`notes list` 输出面 SHALL 逐字不变）。

#### Scenario: 每轮无条件注入（不依赖 query 命中）
- **GIVEN** 一篇 `pinned: true` 的 note，其标题 / 关键词 / 正文**均不含**本轮任务文本的任何命中词
- **WHEN** loop 跑一轮
- **THEN** 该 note 的正文出现在本轮 system prompt 的「常驻笔记」块中（与 Consult 命中集**无关**）

#### Scenario: 注入完整正文（非节选）
- **GIVEN** 一篇常驻 note 的正文长于 `_MAX_EXCERPT_CHARS`(200)
- **WHEN** `pinned_digest()` / prompt 装配
- **THEN** 块内含**完整正文**（超出 200 字符的尾部同样在场），而对同一 note 的 `digest()` 仍只给
  ≤200 字符的节选（两通道互不交叉）

#### Scenario: 独立块：紧随宪法规则、不折入相关笔记
- **GIVEN** 同时存在常驻笔记与 Consult 摘要
- **WHEN** 装配 prompt
- **THEN**「常驻笔记」块**先于**「相关笔记」块、二者为**不同**块；**GIVEN** 二者皆空
- **THEN** prompt 中两个块均不出现（既有行为逐字不变）

#### Scenario: 标记往返 + 幂等 + 逐轮写回不抹除
- **GIVEN** `notes pin <id>`（或 `set_pinned`）
- **WHEN** 以**新进程 / 新实例**读回
- **THEN** canonical 文件含 `- pinned: true`、`parse_note` 返回 `pinned=True`；再 `pin` 同一 id
  ⇒ 文件字节与 `updated_at` **不变**；`unpin` ⇒ 该行消失、渲染输出回到置位前的**逐字**字节
- **AND GIVEN** 一个成功轮的逐轮写回与常驻 note **同 `note_id`**
- **THEN** `observe_turn` 触发后常驻标记**仍在**

#### Scenario: 全局层 + 降级
- **GIVEN** 同一常驻 note
- **WHEN** 在 A / B 两个会话下各注入一次
- **THEN** 两处 `ctx.pinned_notes` **相同**（注入面不接受会话维度）；**AND GIVEN** 常驻钩子抛错
- **WHEN** loop 跑一轮
- **THEN** `ctx.pinned_notes` 为空、留有 `pinned_notes_consult_failed` 留痕，且本轮结果与终止语义**不变**

#### Scenario: 优先级往返 + 幂等 + 逐轮写回不抹除
- **GIVEN** `notes pin <id> --priority 5`（或 `set_pinned(id, priority=5)`）
- **WHEN** 以**新进程 / 新实例**读回
- **THEN** canonical 文件含 `- pin_priority: 5`、`parse_note` 返回 `pin_priority == 5`；再以**同一**
  `(pinned, priority)` 置位 ⇒ 文件字节与 `updated_at` **不变**
- **AND GIVEN** 手改该行为无法解析的取值（`- pin_priority: abc`）
- **THEN** `parse_note` 返回 `pin_priority == 0`（fail-closed，绝不意外抬高优先级）
- **AND GIVEN** 该常驻 note 与某成功轮逐轮写回**同 `note_id`**
- **THEN** `observe_turn` 触发后 `pin_priority` **仍在**；**AND GIVEN** `unpin` 该 note
- **THEN** `pin_priority` 归零、`- pin_priority` 行消失

#### Scenario: 优先级决定在场（预算紧张时高优先级优先）
- **GIVEN** 两篇常驻笔记，其正文合计**超出** `_MAX_PINNED_CHARS`；A 的 `pin_priority` **高于** B
- **WHEN** `pinned_digest()`
- **THEN** `pinned()` 与块内次序均为 A 先于 B（判据＝优先级，**不**由 `note_id` 字典序决定）

#### Scenario: 整篇纳入，绝不半篇
- **GIVEN** 常驻笔记 B 的正文**完整纳入会超预算**
- **WHEN** `pinned_digest()`
- **THEN** 块内含**整篇** A、**完全不含** B 的任何片段（B 的正文**既不整篇在场、也不半篇在场**），
  且**其后的**常驻笔记同样**不入场**（在场集合是优先级次序的**前缀**）

#### Scenario: 超限可见（留痕 + 未进场篇目可查）
- **GIVEN** 如上发生排除
- **WHEN** `pinned_digest()`
- **THEN** 触发 `warnings.warn`（含未进场 `note_id`）；**AND** `pinned_overflow()` 返回被排除的
  `note_id` 列表（次序同 `pinned()`）；**AND GIVEN** 常驻笔记合计**未**超预算
- **THEN** `pinned_digest()` **不**留痕、`pinned_overflow()` 返回空列表

#### Scenario: 单篇超限仍整篇纳入（不空块）
- **GIVEN** **唯一**（或次序首篇）的常驻笔记**自身**即超 `_MAX_PINNED_CHARS`
- **WHEN** `pinned_digest()`
- **THEN** 该篇 SHALL **整篇**在场（块 SHALL NOT 为空 —— 硬约束全灭比超预算更糟），且 SHALL 留痕
  （明示系单篇超限）；**AND** `pinned_overflow()` **不含**该篇（它在场）

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
