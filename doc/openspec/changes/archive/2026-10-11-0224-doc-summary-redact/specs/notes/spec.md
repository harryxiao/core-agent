# notes 规格 Delta — 文档摘要落盘前无条件脱敏（change 0224）

## MODIFIED Requirements

### Requirement: 文档摘要笔记（notes.rag）
系统 SHALL 支持把**一份原始文档的摘要**落成 canonical **结论笔记**：`note_id` 由文档 `doc_id`
确定性派生（`doc-<slug>`），`source` 标记为 `notes.rag`，并携带 `rag` / `doc:<doc_id>` / `summary`
标签。此类笔记 SHALL **不**自动置常驻（`pinned=False`）—— 只经 Consult 命中面与 digest 注入，
SHALL NOT 占常驻预算。

写入 SHALL 复用 `NoteStore.update`（**唯一**写路径，幂等覆盖）：同一 `doc_id` 重复落摘要 SHALL
命中同一篇笔记并**覆盖式刷新**（不增长、不重复）。此类笔记 SHALL **不**计入**归档来源**
（`_ARCHIVE_SOURCES`，其只含提升产物）⇒ SHALL 进 digest **命中节选**面（结论层需在推理上下文可见），
而非仅以清单标题在场。

落盘前系统 SHALL **无条件**对摘要正文执行密钥脱敏（`core.memory.redact_secrets` 同口径：命中密钥
形态的子串替换为 `<redacted>`，保留工具名与其余结构）—— **信任边界在写入侧**，SHALL NOT 依赖提示词
使模型自律。该脱敏 SHALL 与是否配置摘要器无关，且 SHALL NOT 改变幂等覆盖语义（同一 `doc_id` 的
脱敏后正文照常覆盖刷新）。

#### Scenario: 文档摘要落成结论笔记
- **GIVEN** 一份文档摘要（源自 `rag ingest --summarize`）
- **WHEN** 调用 `write_doc_summary(store, doc_id=…, summary=…)`
- **THEN** canonical 目录出现一篇 `note_id="doc-<slug>"` 的笔记，`source="notes.rag"`、
  `tags` 含 `rag` / `doc:<doc_id>` / `summary`、`pinned=False`

#### Scenario: 重摄取幂等覆盖不增长
- **GIVEN** 同一 `doc_id` 已落过一篇摘要笔记
- **WHEN** 再次落该 `doc_id` 的新摘要
- **THEN** 命中**同一** `note_id` 并覆盖刷新正文（笔记总数不增、不产生第二篇）；派生 slug 为空时
  SHALL NOT 写盘（返回 `None`）

#### Scenario: 摘要笔记不被逐轮写回与提升覆写（来源守护）
- **GIVEN** 一篇 `source="notes.rag"` 的摘要笔记
- **WHEN** 逐轮写回（`observe_turn`）与提升（`promote_session_summary`）分别作用于同名主题
- **THEN** `observe_turn` SHALL 走 `<topic>-<n>` 回落、`promote_session_summary` SHALL 拒绝覆写
  ⇒ 摘要笔记正文**逐字不变**（`notes.rag` 不是任一路径的覆写目标）

#### Scenario: 摘要笔记进 digest 命中节选
- **GIVEN** 一篇摘要笔记，其标题 / 标签与某查询词法相关
- **WHEN** 装配 `NoteStore.digest(query)`
- **THEN** 「命中的笔记」块含其**节选**（`source="notes.rag"` 不属 `_ARCHIVE_SOURCES`）；
  `consult` / `search` / `list` 检索语义不受影响

#### Scenario: 摘要正文落盘前无条件脱敏
- **GIVEN** 一份文档摘要正文含密钥形态子串（如 `sk-…` / `AKIA…` / `…password=…`）
- **WHEN** 调用 `write_doc_summary(store, doc_id=…, summary=…)`
- **THEN** 落盘笔记正文中该子串呈 `<redacted>`、**原文形态不出现**，其余结构（工具名 / 标题 / 换行）
  保留；脱敏在**写入侧**完成，与提示词措辞、模型行为均无关
