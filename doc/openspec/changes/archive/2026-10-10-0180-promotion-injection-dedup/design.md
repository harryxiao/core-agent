# Design: 语义记忆去重 —— 提升产物退出 Consult 命中面（change 0180 / ADR-0171 / 台账 E117）

## 背景取证（全部 `file:line` 已核）

| 通道 | 生产者 | 消费者（注入面） | 内容 | 在场条件 |
|---|---|---|---|---|
| A 记忆侧 | `memory.summary_for(sid)`（`store.py:362`）→ L2 `compaction.summary.<sid>` | `loop/default.py:885` → `ctx.summary_long` → `planner.py:298`「历史摘要（长期）」 | **全文**（≤`MAX_SUMMARY_CHARS`=2000，滚动最新） | 本会话有摘要即注入 |
| B 笔记侧 | `promote_session_summary(..., pin=False)`（`runtime.py:379-381`，`promote.py:56`）→ canonical `session-<slug>`（`source="notes.promote"`） | `NoteStore.digest()`（`store.py:166-183`）→ `ctx.notes` → `planner.py:311`「相关笔记」 | 命中**节选** ≤200 字符（`consult` top_k=3）+ 全量清单标题 | 词法命中 ⇒ 节选；否则仅清单标题 |
| B' 笔记侧（显式） | `promote_session_summary(..., pin=True)`（CLI 缺省） | `pinned_digest()` → `ctx.pinned_notes` → `planner.py:292`「常驻笔记」 | **完整正文** | `pinned=True` 每轮 |

⇒ A 与 B 为**同一份内容**（B 正文即 A 的摘要），B 是**陈旧冻结快照**（首次越界时），A 是**滚动最新**。

## 裁决与理由

### D1 让位方向：记忆侧留任、notes 侧让位

- 记忆侧「历史摘要（长期）」块：**每轮无条件**在场（有摘要即注入）+ **持续滚动最新** ⇒ 会话连续性的
  可靠承载者，且 0178 三层滑窗（短/中/长）按比例压缩依赖它**无条件在场**。
- notes 侧提升产物：**词法命中才**给节选、且内容是**冻结旧快照** ⇒ 让位代价最小的那一侧。

反向（让记忆侧退位、由 notes 独家承担）会：① 反转 0153 的 `pin=False`（半自动产物不占常驻预算）；
② 使会话连续性退化为「命中才有」，与 0178 的**无条件**注入相冲；③ 让 prompt 只看到**更旧**的冻结快照。
⇒ 不取。

### D2 退出粒度：只退「命中的笔记」节选，清单标题保留

`digest()` 形如「命中的笔记：<每篇 ≤200 节选>」+「笔记清单：<全量标题 + id>」两段。本 change 只动前者：
① 「清单 = 全量标题」是既有契约（`test_notes.py:244` 断言无关笔记也在清单），不动它 ⇒ 回归面最小；
② 模型仍可从清单看到该提升笔记的**存在**（`session-<slug>` 标题），只是不再重复拿到同源正文。

### D3 判据落 `source`，不落 `tags` / 不落会话

- `render_note` 写 `- source:` 行、`parse_note` 读回（`models.py:69,120`）⇒ `consult()` 返回的
  `NoteEntry.source` **确实是** `notes.promote`（`search()` 不传 `source=` 也不影响，因为**文件里有该行**）。
- `tags` 是 canonical front-matter 的**人工可编辑**面（可被手改抹掉）⇒ 判据更弱；`source` 同时是
  来源守护（`promote.py:58` / `observe_turn` 守护）的既有维度 ⇒ 选它。
- **不做会话级去重**：notes API 不得接受会话维度（红线 + `tests/test_session_isolation.py:379`
  参数化盖住 `digest`）⇒ 去重只能按**类别**（来源集合）而非「本会话」。

### D4 单通道化（承 D1 + 显式路径不变）

提升产出的注入面 = **单通道**：
- `pinned=True`（显式路径）：只经「常驻笔记」块（完整正文，跨会话语义所需；规格明文授权，操作者须先 review）。
  ⇒ 其**节选**也不再进命中面（同一篇不在两条通道重复）。
- `pinned=False`（半自动路径）：正文**不进** prompt，只以清单标题在场 —— 定位＝**归档留档物**
  （canonical 真相层，人工可读/可编辑；需要时操作者**显式** `pin` 后由常驻通道在场）。

### D5 loop / memory 零改动

去重完全落在 notes 的注入面 ⇒ `loop/`（`default.py` / `planner.py` / `protocol.py`）与 `memory/`
**一行不动**：长期/中期摘要块、「相关笔记」块装配次序、提升钩子契约（返回值丢弃）、`summary_for`、
压实口径全部逐字不变。⇒ 会话连续性（I6）由**结构**保证，而非靠新判据。

### D6 来源标记单一真源

`_ARCHIVE_SOURCES` 的字面量不得复制：`promote.py` 已 `from .store import NoteStore`，而 `store.py`
**不** import `promote`（无环）⇒ 把 `"notes.promote"` 上移为 `store.py` 的公开常量 `PROMOTE_SOURCE`,
`promote.py` 改用 import（删本地 `_PROMOTE_SOURCE`）。canonical 文件内的值**不变** ⇒ **零数据迁移**。

## 契约不变量（must-hold，逐条对应测试）

| # | 条件 | 必须成立 |
|---|---|---|
| I1 | 提升产物词法命中 | `digest()` 不含其正文节选；含其标题在「笔记清单」 |
| I2 | 普通笔记（`source="notes"`）词法命中 | 节选照常在（回归锚） |
| I3 | 提升产物 `pinned=True` | 命中节选仍不给；正文经 `pinned_digest()` 完整在场 |
| I4 | `consult` / `search` / `list` | 对提升产物逐字不变（CLI `notes search` 仍搜得到） |
| I5 | 语料无提升笔记 | `digest()` 输出逐字不变 |
| I6 | 会话连续性 | 「历史摘要（长期）」块仍是该会话摘要的唯一 prompt 正文通道（loop 零改动 ⇒ 结构保证） |
| I7 | 判据 | 落 `source`（canonical 内持久 + 来源守护维度），不用 tag、不用会话维度 |

## 已知局限

① **显式**提升在**本会话内**仍双在场：「常驻笔记」（冻结全文，跨会话语义所需、规格授权）与
「历史摘要（长期）」（滚动最新）并列 —— 本 change 只去掉其**节选**重复；去掉正文等于拆掉显式路径的
跨会话用途。
② 提升产物仍以**标题**占 `_MAX_DIGEST_CHARS`(1200) 预算（用户裁决②：存在性保留）。
③ 判据依赖 canonical 内 `- source:` 行：操作者手工删该行即排除失效（canonical 可编辑的固有面）。
④ 未做同源去重的一般化：`key_fact` vs 笔记结论（账目 ②）、`observe_turn` 写回 vs `loop.<trace>`
条目（账目 ③）仍属另账。

## 落点

- `src/core/notes/store.py`：`PROMOTE_SOURCE` 常量 + `_ARCHIVE_SOURCES` 排除面 + `digest()` 一行过滤。
- `src/core/notes/promote.py`：`from .store import PROMOTE_SOURCE, NoteStore`；删 `_PROMOTE_SOURCE`。
- 测试：`tests/test_notes.py`(+3) / `tests/test_notes_loop.py`(+2) / `tests/test_memory_summary_promotion.py`(+1)。
- 规格：`notes/spec.md` MODIFIED × 2（既有 39 Scenario 逐字保留 ⇒ 42）。
- 文档：`doc/01-architecture/adr.md`（ADR-0171）、`doc/02-modules/notes.md`、`doc/03-interfaces/notes-interface.md`、
  `doc/04-testing/test-cases.md`、`coding-plan/known-risk.md`（E117）。
