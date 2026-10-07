## MODIFIED Requirements

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
