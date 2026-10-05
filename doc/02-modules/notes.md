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
- 钩子抛错**只降级留痕**（`notes_consult_failed`），`ctx.notes` 置空，**不改本轮结局**。

### 3.5 Update：任务后写回（复用既有收尾观察者）

- **复用 `TurnObserver`**，不新增第二个收尾钩子：成功轮的（任务, 行动/结果序列）已经过该钩子，
  再开一条「笔记写回」回调会得到**两个节律、两处真源**。
- `observe_turn(task, steps, *, ok)`：`ok=False` 直接返回（**失败轮不写**，失败信号仍归技能迭代）；
  `slug_topic(task)` 为空则跳过；否则把「解决过程」**覆盖式**写回该主题，`source="notes.turn"`。
- 主题 = 任务首行 slug ⇒ 措辞不同的同一任务会**另起主题**（主题分裂优于错合并）。

### 3.6 循环技能由组合根构造

内置技能 `skills.notes.consult_build_update`（`instructions` 含 Consult / Build / Update 三段纪律）
注册进 `SkillLibrary`，**由组合根构造、不下沉 `notes` 包** —— 否则 L2 真相层**向上依赖 L3 skills**，
违反分层（架构用例固化 `loop → notes` 与 `notes ↛ skills`）。

### 3.7 装配面无开关

`notes` **恒装配**，不入 `GATABLE_MODULES`（真相层不是可选玩法）。`NoteStore` 是 `Plugin`
（`plugin_id="notes.store"`）但**未纳入 `PluginRegistry`**（同 E31 欠账）；
它已登记进 `evolution` 的归因白名单 `INTERNAL_PLUGIN_IDS`（13 → 14，ADR-0099），
使其缺陷归因为**架构级**（走人工审批）而非技能级。

---

## 4. 与相邻模块的分工

| 维度 | notes | memory（MemoryStore/FileBackend） | rag |
|---|---|---|---|
| 对象 | **主题**（一篇一文件） | 条目/切片（按层归档） | 知识文档块 |
| 读法 | 按主题读全篇（人可读、可 diff） | 按分数取片段 | 向量相似度 top-k |
| 写回 | 覆盖式（最新即权威） | 追加 + 固化/遗忘 | 摄取重建 |
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
| canonical 目录不存在 | 视为空清单（`list` 返回 `[]`），不自动建目录（首次写入才建） |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/notes-interface.md`
- 规格：`doc/openspec/specs/notes/spec.md`
- 架构：`doc/01-architecture/adr.md` ADR-0099（canonical 真相层 + 钩子接线 + 纯词法取舍）
- 变更：`doc/openspec/changes/archive/2026-10-05-0106-notes-canonical-markdown/`
- 上游：`doc/02-modules/loop.md`（Consult 钩子挂载点）、`doc/02-modules/skills.md`（循环技能路由）
- 相邻：`doc/02-modules/memory.md`、`doc/02-modules/rag.md`（分工见 §4）
