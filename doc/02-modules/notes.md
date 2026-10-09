# 模块设计：文档化记忆（Notes）

> 对应规格：`doc/openspec/specs/notes/spec.md` ｜ 接口：`doc/03-interfaces/notes-interface.md`
> 定位：**L2 文档化真相层**，以 canonical Markdown 承载「一篇一主题、最新即权威」的可人读知识，
> 驱动 Consult → Build → Update 循环纪律。

---

## 1. 模块定位

既有记忆链路（`MemoryStore` + `FileBackend` + RAG）提供的是**扁平切片**：按分数取片段、按层归档，
没有「一个主题一篇文档、读得到全篇、看得出最新」的载体。缺口有三：

1. **没有文档化真相层** —— 结论散在切片里，无法人读、无法 diff、无法一眼看出哪版最新；
2. **没有循环纪律载体** —— Consult（任务前先读）/ Update（任务后写回）无处落地；
3. **外部插件装不上** —— `PluginRegistry` 是**进程内注册表**，插件化「operator 记忆」没有装载面。

故 `notes` 做成**第一方能力**（ADR-0099）：`rag` 仍是检索底座（管「怎么找」），`notes` 管
「找什么、以什么为权威」。二者**不重叠、不互调**。

职责边界：`notes` 只管 canonical Markdown 真相层；**不建向量库、不做嵌入、不改 `MemoryStore` /
`FileBackend` / `rag`**。

---

## 2. 内部组成

```
notes（L2）
├── models   canonical 文档模型：NoteEntry / render_note / parse_note / slug_topic
├── backend  MarkdownBackend：MemoryBackend Protocol 的文件系统实现（覆盖式 + 原子写）
├── store    NoteStore（Plugin）：读写门面 + 两处循环纪律接缝（digest / observe_turn）
└── errors   结构化错误码：NOTE_NOT_FOUND / TOPIC_EXISTS
```

canonical 目录缺省 `$CORE_STATE_DIR/notes`（未设则 `~/.core/state/notes`）。

---

## 3. 关键设计

### 3.1 canonical Markdown 格式（单一真源）

一篇 note = 一个文件，自描述：

```markdown
# 部署流程

- id: deploy
- tags: ops, release
- source: notes
- updated_at: 1791197096.0

## Search Queries

- 部署流程
- ops

## Notes

先备份再滚动更新。
```

`render_note` / `parse_note` **互为逆**：元数据、`## Search Queries`、正文经同一解析器**全字段还原**
（`parse_note(render_note(n)) == n` 由用例守护）。`## Search Queries` 是**词法检索关键词**的落盘位，
让「关键词命中」不依赖正文措辞。缺省关键词由标题 + tags 派生。

### 3.2 后端：实现既有 Protocol、覆盖式、原子写

- `MarkdownBackend` 实现既有 `MemoryBackend` Protocol 的 `get/put/search/list_index/delete`
  —— **契约与语义均不改**（`MemoryEntry.content` = canonical 全文，自描述 ⇒ `get` 不丢字段）。
- **覆盖式**：同主题二次写 = 第二次内容，**不拼接**（「最新最权威」是**有意**语义，非 bug）。
- **原子**：先写 `*.md.tmp` 再 `os.replace` ⇒ 替换前中断不留半截 canonical 文件
  （失败时旧文件逐字保留，由用例守护）。
- 后端经构造注入 ⇒ 可换（不绑死文件系统）。

### 3.3 检索：纯词法 + 分区加权，中文按 2-gram

- 打分 = `Σ(字段权重 × 该字段命中词数) ÷ 词数`，在 `title(3×) / tags(2×) / Search Queries(2×)
  / note_id(1×) / 正文(1×)` 上匹配，降序取 top-k（**分区加权**，change `0107`）。
- 加权**只影响排序**：打分不再 ≤ 1，仅用于 `> 0` 过滤与降序排序、**不外露**；命中判据与返回结构
  （`MemoryEntry` 列表）不变 ⇒ 标题精确命中的主题排在「仅正文顺带提及」的主题之前。
- **中文按 2-gram 切词**（CJK 无词界）：Consult 的查询是**任务句**（如「部署流程怎么走」），
  整词包含会让它几乎永不命中；2-gram 使长句仍能命中「部署 / 流程」。
  英文与非 CJK 段保持整词包含。
- **不建向量库**：语义检索归 `rag`；此处只要确定性、零依赖、可解释。
- 切词只在 `MarkdownBackend` 内，**不影响 `skills` 的路由口径**（skills 用空白切分）。

### 3.4 Consult：任务前只读注入（loop 钩子）

- `NotesConsult = Callable[[str], str]`：loop 定义、**不 import notes**（架构红线），
  生产侧由组合根注入闭包（内部调 `NoteStore.digest`）。
- 摘要在**任务前**写入 `LoopContext.notes`（加法字段，缺省空串 ⇒ 不注入），
  `LLMPlanner._system_prompt` 渲染为「相关笔记」块（排在宪法/事实之后、技能/工具之前）。
- **不自动全量注入正文**：digest = 命中笔记节选（每篇 ≤200 字符）+ 全量**标题清单**，
  总量 ≤1200 字符 ⇒ token 有界。
- **归档来源排除面**（change 0180／ADR-0171／账本 E117）：命中**节选** SHALL 排除**归档来源**笔记
  （`source ∈ _ARCHIVE_SOURCES`，即提升产物 `notes.promote`）—— 其正文**源自 memory 会话摘要**、
  已由 loop「历史摘要（长期）」块每轮注入 ⇒ 同源内容免二次注入；此类笔记仍以**清单标题**在场
  （存在性可见）。**排除仅落在 `digest` 注入面**：`consult` / `search` / `list`（检索语义）与
  `pinned_digest`（常驻通道）**逐字不变** ⇒ CLI `notes search` 仍搜得到提升产物。
- 钩子抛错**只降级留痕**（`notes_consult_failed`），`ctx.notes` 置空，**不改本轮结局**。

### 3.4.1 常驻（pinned）：任务级硬约束锚（与 Consult **分列**的两条通道）

- 动机（账本 `E93`）：Consult 只在 query **命中**时注入正文，未命中只剩 ≤1200 字标题清单
  ⇒ 长任务中期的硬约束（「对外接口必须 HTTPS」）**不保证每轮在场**；每轮恒注入的此前只有 L0 宪法
  （**全局、非任务级**）。常驻语义补上「**任务级、每轮无条件**」这一维。
- 标记面：`NoteEntry.pinned` ＋ canonical 元数据行 `- pinned: true`（未置位**不输出** ⇒ 既有文件逐字不变）
  ＋ CLI `notes pin/unpin`。解析**宽容**（`true/yes/1/on`，大小写不敏感；其余一律 False，fail-closed）。
- **在场判据＝显式优先级**（change `0154`／ADR-0146／路线图 G1）：`NoteEntry.pin_priority`（缺省 0）
  ＋ canonical 行 `- pin_priority: <n>`（**仅非 0 输出** ⇒ 既有文件逐字不变；解析失败 ⇒ 0，fail-closed）
  ＋ CLI `notes pin <id> --priority N`。`pinned()` 次序＝**优先级降序、同优先级 `note_id` 升序**
  （确定性）。清常驻（`unpin`）同时归零优先级；逐轮写回**保留** `pinned` 与 `pin_priority`。
- 注入面：`PinnedNotesConsult = Callable[[], str]`（**零参** ⇒ 与当轮任务无关，签名即契约）
  → `LoopContext.pinned_notes` → planner **独立块**「常驻笔记」，紧随宪法规则、**先于**相关事实/文档目录/
  相关笔记。**正文全文**（非节选）、无 query 判据、总量有界于 `_MAX_PINNED_CHARS`(4000)。
- **整篇纳入，绝不半篇**（change `0154`）：一篇要么整篇在场、要么整篇不在场（半截硬约束可能语义反转）；
  超预算篇整篇排除、其后各篇不挤入（在场集合＝优先级次序的**前缀**）；**唯一例外**是次序首篇自身超限时
  仍整篇纳入（块不因单篇超限而空）。超预算**可见**：`pinned_digest()` 经 `warnings.warn` 留痕、
  `pinned_overflow()` 报未进场 id、CLI `notes pinned` 报「在场 / 未进场」。
- **与 Consult 的边界**：常驻走**另一条**显式路径，**不改变**「Consult → Build → Update 循环纪律」对
  **未标记**笔记的「不自动全量注入」口径（该口径只管 Consult 命中路径）。
- 全局层：`pinned()/pinned_digest()/pinned_overflow()/set_pinned()` **不接受**会话维度（承 §4 的「刻意知识不参与隔离」）。
- 三 loop 同注入（主 / 子任务 / 神兽）—— 子任务与神兽同须遵守任务级硬约束。

### 3.5 Update：任务后写回（复用既有收尾观察者）

- **复用 `TurnObserver`**，不新增第二个收尾钩子：成功轮的（任务, 行动/结果序列）已经过该钩子，
  再开一条「笔记写回」回调会得到**两个节律、两处真源**。
- `observe_turn(task, steps, *, ok)`：`ok=False` 直接返回（**失败轮不写**，失败信号仍归技能迭代）；
  `slug_topic(task)` 为空则跳过；否则把「解决过程」**覆盖式**写回该主题，`source="notes.turn"`。
- 主题 = 任务首行 slug ⇒ 措辞不同的同一任务会**另起主题**（主题分裂优于错合并）。
- **来源守护**（change 0151／ADR-0143／账本 E95）：一条主题只应由**产生它的那条写路径**覆写。
  若 `slug_topic(task)` 撞上来源**非** `notes.turn` 的既有笔记（人工撰写 / promotion 产出），
  **不改写**该主题 —— 本轮沉淀改写入首个不冲突的派生主题 `<topic>-<n>`（`n` 为 2 起、取首个
  「不存在或来源为 `notes.turn`」者）；同一派生主题后续轮次**复用**（覆盖式，不无谓增长）。
  来源为 `notes.turn` 的既有行为**逐字不变**（含保留 `tags` / `pinned`）。⇒ 外来源正文与标题**绝不**
  被静默替换（堵住「常驻笔记被步骤列表污染」的真缺陷）。
- **有意义闸门**（change 0171／ADR-0162／账本 E108）：`steps` **为空**（纯文字回复轮）⇒ 不落盘。
- **效应闸门**（change 0176／ADR-0167／账本 E113）：`steps` 非空但**不含成功的写效应工具动作**
  （仅纯读型如 `web_fetch`/`file_read`，或写效应动作失败）⇒ **不落盘**。写效应工具集
  `file_write`/`file_patch`/`code_run`/`gate_run`/`install`/`uninstall`；工具名从 steps 行前缀解析
  （行首至首个 `（`，剥 `tools.` 前缀）—— `loop._action_steps` 行格式**不改**（红线：loop 不 import
  notes），非已知工具名 ⇒ 保守判为无写效应。纯读产出的内容是**素材**，归 memory 侧 keyfact 抽取沉淀，
  不进 canonical 知识层（「无行动不记忆：只沉淀行动与结果」——「行动」须有**持久化效应**）。

### 3.5.1 会话摘要提升（promotion，change 0150／ADR-0142／账本 E94；半自动 change 0153／ADR-0145／路线图 G3）

- **触发形态 = 显式，或由 memory 压实侧「首次越界」半自动**：`core.notes.promote.promote_session_summary(...)`，
  由 CLI `notes promote <session-id>` 或上层**显式**调用触发；**半自动**路径则由 memory 压实发现某会话
  摘要**首次越过**滚动上界（`MAX_SUMMARY_CHARS`）时，经注入的提升钩子交付**一次**（见 §3.5.2）。
  **不**依赖模型自觉（对比仅靠技能纪律 `skills.notes.consult_build_update` 的路径）—— 与 §1「笔记是被
  有意文档化的**刻意知识**，不是某一轮对话的残留」哲学一致。该路径**零 LLM 调用**。
- **幂等覆盖**：`note_id = --as 或 f"session-{slug_topic(session_id)}"` ⇒ 同会话重复提升命中**同一** note、
  **不增长**；写回复用**唯一**写路径 `NoteStore.update()`（不另开第二写路径）。
- **置常驻分路径**：**显式**提升产出 `pinned=True`（承 §3.4.1）⇒ 摘要正文**每轮无条件注入**（受
  `_MAX_PINNED_CHARS` 与既有常驻笔记共享的预算约束）；**半自动**提升以 `pin=False`（承 ADR-0142 局限①）
  产出**普通** canonical 笔记 —— 定位＝**归档留档物**（canonical 真相层、人工可读/可编辑），
  **不**占常驻预算、**不**以硬约束身份逐轮进场。⚠️ **红线**：显式提升正文每轮进模型上下文 ⇒ 操作者须在
  提升前 **review 摘要**，**绝不**提升含密钥 / 凭据的摘要。
- **正文不进 prompt 命中节选**（change 0180／ADR-0171／账本 E117）：提升产物的正文**源自 memory 会话摘要**，
  该摘要已由 loop「历史摘要（长期）」块每轮承载 ⇒ 其**节选** SHALL NOT 再进 Consult 命中面（同源内容免二次
  注入，见 §3.4 归档来源排除面）。**只退节选、清单标题保留**（存在性可见）。**显式**路径的 `pin=True`
  每轮常驻注入**语义不变**（跨会话用途所需），仅其**节选**不再重复进命中面（局限①：本会话内正文仍双在场
  ——常驻块＋长期摘要块，去重不及正文）。
- `session_id` 仅是 `note_id` 的**派生输入**与来源标注（`tags` 含 `session:<sid>`），**不是**隔离维度 ——
  产出属**全局文档层**（承「刻意知识不参与会话隔离」）。空 slug 且未给显式 id ⇒ 返回 `None`、不写盘。
- **来源守护**（change 0151／ADR-0143）：目标 `note_id` 撞上来源**非** `notes.promote` 的既有笔记
  （如人工撰写）且**未**显式给 `--as` ⇒ 返回 `None`、**不写盘**、CLI **非零退出**（与「空 slug」同口径，
  **不新增**错误码）；显式 `--as` ⇒ 视为**显式授权**、照常覆写。⇒ 提升**绝不**静默毁人工笔记。
- 写入**不接** `EffectTracker`（承 §1 文档层既有取舍，与 `pin/unpin`/`observe_turn` 同一条路径一致）。

### 3.5.2 半自动提升的接入（change 0153／ADR-0145／路线图 G3）

- **判据与频次严格限定**：半自动提升**仅**由「memory 压实发现某会话摘要**首次越过**滚动上界
  （既有摘要长度 ≤ 上界「或尚无摘要」而本次产出 > 上界）」触发，且每会话**至多一次**；**已越界**
  不再交付（免以已稀释的后继摘要覆写完整内容）。触发点是 `MemoryStore._summarize_sessions` 于
  `_commit_summary` **之后**、取**本次产出的**摘要条目交付注入的 `summary_promoter` 钩子。
- **接线（组合根）**：`runtime` 把 `NoteStore` 构造**上移**至 `MemoryStore` 之前，注入闭包
  `_promote_summary(session_id, summary) -> promote_session_summary(note_store, summary, session_id, pin=False)`。
  ⇒ 依赖方向 `notes → core.memory` 维持，memory **不** import notes。半自动产出的 note **不**置常驻
  （§3.5.1），属全局文档层，定位＝**归档留档物**：**正文不进** Consult 命中面（§3.4 归档来源排除面 /
  change 0180／ADR-0171），仅以**清单标题**在场；`consult`/`search`/`list` 检索面**不变**。

### 3.6 循环技能由组合根构造

内置技能 `skills.notes.consult_build_update`（`instructions` 含 Consult / Build / Update 三段纪律）
注册进 `SkillLibrary`，**由组合根构造、不下沉 `notes` 包** —— 否则 L2 真相层**向上依赖 L3 skills**，
违反分层（架构用例固化 `loop → notes` 与 `notes ↛ skills`）。

### 3.7 装配面无开关

`notes` **恒装配**，不入 `GATABLE_MODULES`（真相层不是可选玩法）。`NoteStore` 是 `Plugin`
（`plugin_id="notes.store"`）但**未纳入 `PluginRegistry`**（同 E31 欠账）；
它已登记进 `evolution` 的归因白名单 `INTERNAL_PLUGIN_IDS`（13 → 14，ADR-0099），
使其缺陷归因为**架构级**（走人工审批）而非技能级。常驻注入（§3.4.1）同属**组合根注入闭包**
（`Runtime.build_runtime` 的 `_pinned_notes`）⇒ notes 仍恒装配、仍不入 `GATABLE_MODULES`。

---

## 4. 与相邻模块的分工

| 维度 | notes | memory（MemoryStore/FileBackend） | rag |
|---|---|---|---|
| 对象 | **主题**（一篇一文件） | 条目/切片（按层归档） | 知识文档块 |
| 读法 | 按主题读全篇（人可读、可 diff） | 按分数取片段 | 向量相似度 top-k |
| 写回 | 覆盖式（最新即权威）＋**来源守护**（只被产生它的写路径覆写，§3.5／§3.5.1）；**可选**由会话摘要**显式提升**（§3.5.1） | 追加 + 固化/遗忘 | 摄取重建 |
| 检索 | 纯词法（CJK 2-gram） | 词法/打分 | embedding 语义 |

三者在写入端**互不调用**：`notes` 不落 `MemoryStore`，`memory` 不读 canonical 目录。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 读取不存在的主题（`get`） | `NOTE_NOT_FOUND`，不返回空对象 |
| 显式创建已存在主题（`create`） | `TOPIC_EXISTS`，**不覆盖**既有内容（`ensure` 幂等，不报错） |
| Consult 钩子抛错 | 置空摘要 + `notes_consult_failed` 留痕，**不改本轮结局** |
| 任务文本无可保留字符（slug 为空） | `observe_turn` 返回 `None`，不写盘、不报错 |
| 逐轮写回撞来源**非** `notes.turn` 的既有笔记 | **不覆写**该主题（正文/标题逐字不变），沉淀改道派生主题 `<topic>-<n>`（**不丢**本轮沉淀） |
| 提升时会话无摘要 / 派生 `note_id` 为空（且未给 `--as`） | **不写盘**，CLI 退出码非零（**不新增** `notes` 错误码） |
| 提升撞来源**非** `notes.promote` 的既有笔记（未给 `--as`） | **不写盘**，CLI 退出码非零；给 `--as` 即显式授权覆写（**不新增** `notes` 错误码） |
| canonical 目录不存在 | 视为空清单（`list` 返回 `[]`），不自动建目录（首次写入才建） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/notes-interface.md`
- 规格：`doc/openspec/specs/notes/spec.md`
- 架构：`doc/01-architecture/adr.md` ADR-0099（canonical 真相层 + 钩子接线 + 纯词法取舍）
- 变更：`doc/openspec/changes/archive/2026-10-05-0106-notes-canonical-markdown/`
- 上游：`doc/02-modules/loop.md`（Consult 钩子挂载点）、`doc/02-modules/skills.md`（循环技能路由）
- 相邻：`doc/02-modules/memory.md`、`doc/02-modules/rag.md`（分工见 §4）
