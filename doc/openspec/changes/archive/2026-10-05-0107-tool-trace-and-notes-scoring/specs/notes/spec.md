# Notes Specification Delta

## MODIFIED Requirements

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
