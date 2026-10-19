## MODIFIED Requirements

### Requirement: Consult → Build → Update 循环纪律

系统 SHALL 提供内置技能 `skills.notes.consult_build_update`（注册进 `SkillLibrary`），其
`instructions` SHALL 非空且**同时**承载「任务前先 Consult」与「任务后 Update」两段纪律。loop SHALL
提供**任务前 Consult 钩子**与**任务后 Update 钩子**：前者确定性读 `NoteStore.consult(query)` 命中的
note + `NoteStore.list()` 清单，作为「相关笔记」块注入本轮推理上下文（**不自动全量注入**）；后者在
**成功轮**把本轮沉淀写入**候选区**（见 Requirement「沉淀候选区与晋升」），SHALL NOT 直接写 canonical。
loop SHALL NOT import `notes`（架构红线），两枚钩子 SHALL 由组合根注入。

Consult 的**命中节选面** SHALL 排除**归档来源**笔记（`source` 属归档来源集合，当前为提升产物
`notes.promote`，见 Requirement「会话摘要提升（promotion）」）：此类笔记 SHALL NOT 出现在「命中的笔记」
节选中——其正文**已由**记忆侧「历史摘要（长期）」块（`memory`「记忆压实」的会话摘要）每轮注入，
同一份内容 SHALL NOT 经两条通道重复注入同一次请求。归档来源笔记 SHALL 仍以**「笔记清单」标题 + `note_id`**
在场（存在性可见）；其正文 SHALL 只经**显式常驻通道**（`pinned=True`，承 Requirement「常驻（pinned）笔记」）
或 canonical 真相层（人工 `notes show` / 编辑）触达。该排除 SHALL **只**落在 `digest` 注入面：
`consult` / `search` / `list` 的检索语义 SHALL **逐字不变**（CLI `notes search` 仍可检索到归档来源笔记）；
**非**归档来源笔记的命中节选 SHALL 逐字不变。

笔记层 SHALL 是**全局文档层**，SHALL NOT 参与会话隔离：Consult 与沉淀候选 SHALL NOT 接受会话维度，
同一 query 在任意会话下的命中集 SHALL 相同——笔记是**被有意文档化的知识库**（刻意知识），
不是某一轮对话的残留，故按设计进全局层、跨会话共享。

**运行时任务后沉淀 SHALL 走候选通道**：成功轮先经**确定性预滤**，任一不满足即 SHALL **零落盘、
零模型调用**——`ok=True`；行动序列**非空**；行动序列含至少一个**成功的写效应工具动作**（纯读型
工具产出的内容属素材，归 memory 侧 keyfact 抽取；写效应动作失败——行含 `错误：`——不计）；
任务文本去空白后 ≥ 6 字符（寒暄 / `继续` / `ok` 等短指令不沉淀）。预滤通过后，注入的**提炼器**
（DI 可调用，缺省不启用）SHALL 判定本轮是否产生**值得长期保留的知识**并产出结构化候选
（结论 / 步骤 / 依据，而非对话原文）；提炼器 SHALL 输出**严格 JSON**，解析失败 / `durable=false` /
空 `content` / 空 `topic` 时 SHALL 丢弃该轮。提炼器输入 SHALL 先脱敏、再有界，SHALL NOT 落 ReAct
消息原文或整篇工具输出。

`NoteStore.observe_turn` SHALL 保留为**低层原语**（供显式调用与既有来源守护用例），其下列旧语义
（来源守护 / 有意义闸门 / 效应闸门 / 人类可读正文）SHALL 逐字保留；但运行时收尾 SHALL NOT 调用它——
默认沉淀路径唯一：候选区 → 晋升。晋升 SHALL 以 `NoteStore.update()` 为唯一 canonical 写路径，
`source=notes.sediment`，并受来源守护（见「沉淀候选区与晋升」）。

#### Scenario: 任务前注入相关笔记
- **GIVEN** 组合根注入了 Consult 钩子，且 canonical 目录含与任务相关的 note
- **WHEN** loop 开始一轮任务
- **THEN** 命中的 note 内容与笔记清单确定性注入本轮推理上下文（同一输入产生同一 orientation）

#### Scenario: 笔记不参与会话隔离
- **GIVEN** canonical 目录含与某 query 相关的 note
- **WHEN** 分别在不同会话下以同一 query Consult
- **THEN** 两处命中集**相同**（Consult 面不接受会话维度，笔记为全局层）

#### Scenario: 任务后写回笔记
- **GIVEN** 显式调用低层原语 `observe_turn`，一轮任务成功完成并产出新结论
- **WHEN** 该原语执行
- **THEN** 对应主题的 canonical 文件内容含该新结论（覆盖式；**运行时默认路径不走此原语**，
  运行时见「成功轮产出候选而非 canonical」）

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
- **WHEN** 显式调用低层原语 `observe_turn`
- **THEN** 该笔记的**正文与标题逐字不变**（`source` / `pinned` 一并保留），本轮沉淀落在派生主题
  `<topic>-2` 中
- **AND GIVEN** 该既有笔记来源为 `notes.turn`
- **THEN** 仍**覆盖式**写回**同一**主题（既有行为逐字不变，保留 `tags` 与 `pinned`）

#### Scenario: 纯文字回复轮不写回
- **GIVEN** 一轮任务成功完成，但本轮**无任何工具动作**（行动序列为空）
- **WHEN** 收尾钩子触发任务后沉淀（或显式调用低层原语）
- **THEN** 不落盘，canonical 目录与候选区均**无变化**

#### Scenario: 解决过程人类可读（不落原文）
- **GIVEN** 一轮含工具动作的任务成功完成
- **WHEN** 显式调用低层原语写回 canonical 文件
- **THEN** `## 解决过程` 之下为人类可读行（工具名 + 有界参数摘要 + 有界结果节选）
- **AND** 正文**不含** ReAct 消息原文（如 `{"tool_id"` / `{"data"` 形态的 JSON 转储），
  亦**不含**整篇工具输出（正文长度有界）

#### Scenario: 纯读轮不写回（效应闸门）
- **GIVEN** 一轮任务成功完成，行动序列**仅含纯读型工具动作**（如 `web_fetch` / `file_read`，
  无任何写效应动作）
- **WHEN** 收尾钩子触发任务后沉淀
- **THEN** 不调用提炼器、不写候选；canonical 目录**无新增文件**、既有文件**逐字不变**——
  纯读产出的事实属素材，归 memory 侧 keyfact 抽取沉淀

#### Scenario: 写效应失败不计入（效应闸门失败口径）
- **GIVEN** 一轮任务成功完成（`ok=True`），行动序列含 `code_run` 动作但其结果为**失败**
  （行含 `错误：` 前缀）
- **WHEN** 收尾钩子触发任务后沉淀
- **THEN** 不调用提炼器、不写候选——只沉淀**验证过的**行动与结果

#### Scenario: 含写效应轮正常写回
- **GIVEN** 一轮任务成功完成，行动序列含至少一个**成功的**写效应工具动作
  （如 `file_write` / `code_run` 成功 / `gate_run` 通过）
- **WHEN** 收尾钩子触发任务后沉淀
- **THEN** 经提炼器判定为持久知识时写入候选区（不直写 canonical）；判定为非持久时无落盘

#### Scenario: 命中面排除归档来源（提升产物以清单标题在场）
- **GIVEN** canonical 目录含一篇提升产物（`source == "notes.promote"`）与一篇普通笔记
  （`source == "notes"`），二者正文都与本轮任务词法相关
- **WHEN** loop 装配「相关笔记」块（`digest`）
- **THEN** 「命中的笔记」节选**只含普通笔记**的节选；提升产物**不进**命中节选（其正文不注入本轮请求），
  但**仍在**「笔记清单」中以标题 + `note_id` 在场；**AND** 同一 query 下
  `consult()` / `search()` / `list()` 对提升产物的结果**逐字不变**（排除只在 `digest` 注入面）

#### Scenario: 成功轮产出候选而非 canonical
- **GIVEN** 一轮含成功写效应动作的任务成功完成，提炼器判定 `durable=true`
- **WHEN** 收尾钩子触发
- **THEN** 候选区新增一条候选（topic / title / 结构化正文 / tags / queries），
  且 canonical 目录**无新增文件**

#### Scenario: 短任务不产候选
- **GIVEN** 一轮成功任务的任务文本去空白后少于 6 字符（如 `继续` / `ok`）
- **WHEN** 收尾钩子触发
- **THEN** 不调用提炼器、不写候选

#### Scenario: 提炼失败或非持久不产候选
- **GIVEN** 提炼器返回坏 JSON、`durable=false` 或空 `content`
- **WHEN** 收尾钩子触发
- **THEN** 候选区无变化；留痕**不含**对话或提炼正文

#### Scenario: 候选不进上下文
- **GIVEN** 候选区含与 query 词法相关的候选
- **WHEN** 装配「相关笔记」块（`digest`）或执行 `notes list/search`
- **THEN** 候选**不出现**在命中节选、笔记清单与检索结果中

## ADDED Requirements

### Requirement: 沉淀候选区与晋升

系统 SHALL 提供**候选区**：候选以 JSON 落盘于 `$CORE_STATE_DIR/notes-candidates.json`，
SHALL 由 `CandidateStore` 统一读写。文件 SHALL 以 **0600** 权限原子写入（临时文件 + 替换），
条目上限 SHALL 为 128（超出按 `last_seen` 淘汰最旧），读取损坏或结构不符时 SHALL 降级为空态并留痕
（只报条数，**不**回显内容）。候选区 SHALL NOT 进入 `digest` / `list` / `search` / `consult` /
`pinned` 任一注入或检索面。

候选字段 SHALL 含：`candidate_id`（topic slug）、`title`、`content`、`tags`、`queries`、`kind`、
`support`、`first_seen`、`last_seen`、`trace_digests`（≤8）、`evidence`（任务首行，≤120 字符）。
同一 topic 的重复观察 SHALL **upsert**（刷新内容与 `last_seen`）；`support` 仅在
`trace_digest`（脱敏行动序列摘要）**未出现过**时 +1——同一轨迹重复提交 SHALL NOT 虚增支持度。

晋升（`notes candidate-promote <candidate_id> [--as NOTE_ID] [--title TITLE]`）SHALL：
以 `NoteStore.update()`（唯一 canonical 写路径）写入，`source=notes.sediment`；保留既有
`pinned` / `pin_priority`；`tags` 取并集并追加 `sediment:<candidate_id>`；成功后移除候选。
目标主题已存在且来源非 `notes.sediment`，或带 `sediment:<别的候选>` 标签时 SHALL 拒绝
（`TOPIC_EXISTS`，CLI 退出 1），候选 SHALL 保留。`--as` SHALL 允许显式指定目标 note_id。

`notes candidate-reject <candidate_id>` SHALL 移除候选（不写 canonical）。
自动晋升 SHALL 缺省**关闭**；开启时同一候选 `support ≥ 2` SHALL 尝试晋升，冲突时只留痕
（只报候选 id），候选保留。

#### Scenario: 重复观察按 topic 合并且支持度去重
- **GIVEN** 提炼器两次对同一 topic 产出候选，且两次行动序列逐字相同
- **WHEN** 两次收尾均写入候选区
- **THEN** 候选数不增；`support` 仍为 1；`last_seen` 刷新

#### Scenario: 不同轨迹提升支持度
- **GIVEN** 同一 topic 的两次观察，行动序列不同
- **WHEN** 第二次写入候选区
- **THEN** `support == 2`

#### Scenario: 候选上限有界
- **GIVEN** 候选区已有 128 条
- **WHEN** 写入一条新 topic 候选
- **THEN** 总数为 128；`last_seen` 最旧的候选被淘汰

#### Scenario: 显式晋升写入 canonical
- **GIVEN** 候选区含一条候选，canonical 无同名主题
- **WHEN** 执行 `notes candidate-promote <candidate>`
- **THEN** canonical 新增笔记：`source=notes.sediment`、正文/title/queries 取自候选、
  tags 含 `sediment:<candidate_id>`；候选被移除

#### Scenario: 晋升保留常驻与优先级
- **GIVEN** canonical 已有同一候选的晋升产物且 `pinned=true, pin_priority=100`
- **WHEN** 再次晋升同一候选
- **THEN** 正文更新，`pinned` 与 `pin_priority` 逐字保留

#### Scenario: 晋升撞外来源被拒绝
- **GIVEN** canonical 目录含一篇来源非 `notes.sediment` 的笔记，其 `note_id` 恰等于候选 topic
- **WHEN** 执行 `notes candidate-promote <candidate>`
- **THEN** 退出非零；该笔记正文与标题**逐字不变**；候选**仍保留**

#### Scenario: 异候选不可互相覆盖
- **GIVEN** canonical 已有候选 A 的晋升产物（带 `sediment:A`）
- **WHEN** 晋升候选 B 且 `--as` 指向 A 的 note_id
- **THEN** 拒绝（退出 1），A 的正文逐字不变，B 候选保留

#### Scenario: 自动晋升缺省关闭
- **GIVEN** 未开启 `notes.candidate_auto_promote`，候选 `support` 已达 2
- **WHEN** 候选写入候选区
- **THEN** canonical 不新增笔记，候选保留

#### Scenario: 开启后达支持度自动晋升
- **GIVEN** 已开启 `notes.candidate_auto_promote`，候选 `support` 达到 2
- **WHEN** 候选写入候选区
- **THEN** 自动晋升为 canonical，候选移除

#### Scenario: 拒绝候选
- **GIVEN** 候选区含一条候选
- **WHEN** 执行 `notes candidate-reject <candidate>`
- **THEN** 候选移除，canonical 无变化

#### Scenario: 候选文件损坏可降级
- **GIVEN** `notes-candidates.json` 内容不是合法 JSON
- **WHEN** 构造候选区
- **THEN** 候选区为空态，留痕只报条数/错误类别，**不**回显文件内容

### Requirement: 存量清理（回收目录）

系统 SHALL 提供 `notes prune --source <SOURCE> [--dry-run] [--include-pinned] [--trash-dir DIR]`：
把 canonical 中 `source` 等于给定值的笔记**移动**到 `DIR/<UTC 时间戳>/<note_id>.md`（0600），
SHALL NOT 物理删除。缺省 SHALL 跳过 `pinned` 笔记并报告跳过数量；`--include-pinned` 才纳入。
移动前 SHALL 读取原始 canonical 字节，移动后 SHALL 写 `manifest.json`（0600，含 source / 时间戳 /
moved 列表 / kept_pinned 列表），使恢复可审计。

`--dry-run` SHALL 只列出将被移动的 note_id 与跳过数量，SHALL NOT 创建目录或改盘。
非 dry-run 且移动数为 **0** 时 SHALL 退出非零。恢复方式 SHALL 为把回收目录中的
`<note_id>.md` 复制回 canonical 目录（原文件名即注记 id）。

#### Scenario: 按来源移入回收目录
- **GIVEN** canonical 含 2 篇 `notes.turn` 与 1 篇 `notes.promote`
- **WHEN** 执行 `notes prune --source notes.turn`
- **THEN** 2 篇 `notes.turn` 被移入回收目录、canonical 不再列出；`notes.promote` 不受影响；
  manifest 记录 2 条 moved

#### Scenario: 默认保留常驻笔记
- **GIVEN** 一篇 `notes.turn` 笔记 `pinned=true`
- **WHEN** 执行 `notes prune --source notes.turn`（未加 `--include-pinned`）
- **THEN** 该笔记留在 canonical，manifest 的 `kept_pinned` 含其 id

#### Scenario: dry-run 不改盘
- **GIVEN** canonical 含若干目标来源笔记
- **WHEN** 执行 `notes prune --source notes.turn --dry-run`
- **THEN** 只打印将移动的 id 与计数；canonical 与回收目录均无变化

#### Scenario: 零移动退出非零
- **GIVEN** canonical 不含目标来源笔记
- **WHEN** 执行 `notes prune --source notes.turn`
- **THEN** 退出 1

#### Scenario: 回收文件可逐字恢复
- **GIVEN** 一篇笔记已被 prune 移入回收目录
- **WHEN** 把 `<note_id>.md` 复制回 canonical 目录
- **THEN** 其内容与原 canonical 字节逐字相同
