## ADDED Requirements

### Requirement: 常驻（pinned）笔记（任务级硬约束锚）

系统 SHALL 在 `NoteEntry` 提供布尔字段 `pinned`（缺省 `False`）；canonical 元数据行 SHALL 为
`- pinned: true`，且 `pinned` 为 `False` 时该行 SHALL **省略** ⇒ 既有 canonical 文件的渲染输出
**逐字不变**（`render_note` / `parse_note` 仍互为逆）。`parse_note` SHALL 读回该行（大小写不敏感、
接受 `true` / `yes` / `1` / `on` 等真值拼写）；**无法识别**的取值 SHALL 视为 `False`（fail-closed：
手误**绝不**意外把一个主题变成常驻）。

`NoteStore` SHALL 提供 `set_pinned(note_id, *, pinned=True)`、`pinned() -> list[NoteEntry]` 与
`pinned_digest() -> str`。目标 note 不存在 ⇒ SHALL 返回 `NOTE_NOT_FOUND`；标记值**未变化** ⇒
SHALL NOT 写盘、SHALL NOT 变更 `updated_at`（幂等，不搅动「最新即权威」判据）。既有逐轮写回
（`observe_turn`）SHALL NOT 抹除既有 `pinned` 标记。

`pinned_digest()` SHALL 返回常驻笔记的**完整正文**（SHALL NOT 截为节选），按 `note_id` 升序
**确定性**拼接，总长 SHALL **有界**（模块常量，缺省 4000 字符）；无常驻笔记或正文全空 ⇒ SHALL 返回空串。

loop SHALL 提供**任务前常驻注入钩子**（**无 query 入参**）——其产出 SHALL 写入
`LoopContext.pinned_notes`；`LLMPlanner` 在该字段非空时 SHALL 渲染为**独立块**，位置 SHALL
**紧随「宪法规则」块之后、「相关事实」块之前**。常驻注入 SHALL **逐轮无条件生效**，SHALL NOT
以 query 命中为条件。该语义 SHALL NOT 改变 Requirement「Consult → Build → Update 循环纪律」的口径：
`digest`（Consult）SHALL NOT 自动全量注入正文，且常驻笔记 SHALL NOT 折入「相关笔记」块——常驻注入是
**仅对显式标记 `pinned: true` 的笔记**开启的**独立通道**，不是对未标记笔记的全量注入。loop SHALL NOT
import `notes`（架构红线），钩子 SHALL 由组合根注入，且 SHALL 同时注入主 Agent、子 Agent 与神兽 loop。

常驻笔记 SHALL 属**全局文档层**，SHALL NOT 参与会话隔离：`pinned` / `pinned_digest` / `set_pinned`
SHALL NOT 接受会话维度。

常驻注入钩子抛错 SHALL 降级留痕（`pinned_notes_consult_failed`）、置空该块，且 SHALL NOT 改变本轮
结果与终止语义。

CLI SHALL 提供 `notes pin <note_id>` 与 `notes unpin <note_id>`；缺失 id ⇒ SHALL 报 `NOTE_NOT_FOUND`
且退出码非零。`notes list` SHALL 以**追加列**标记常驻笔记，非常驻行输出 SHALL NOT 改变。

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
