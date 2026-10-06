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
