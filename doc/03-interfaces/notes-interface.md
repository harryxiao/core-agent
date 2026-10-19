# 接口设计：文档化记忆（Notes Interface）

> 模块：`02-modules/notes.md` ｜ 规格：`openspec/specs/notes/spec.md`
>
> 定位：**人类可读、可 diff、可 review 的文档化权威真相层**，与既有 RAG 语义召回层**并列互补**。
> **不引入 RAG / embedding / 向量库**。canonical 目录缺省 `$CORE_STATE_DIR/notes`（可注入 `path`）。

---

## 1. 数据模型 `NoteEntry`（`core.notes.models`）

```python
@dataclass
class NoteEntry:
    note_id: str                      # 主题标识（slug；即 canonical 文件名去扩展名）
    title: str = ""                   # 人类可读标题（H1；空则回落 note_id）
    content: str = ""                 # 正文（`## Notes` 之下）
    tags: list[str] = field(default_factory=list)
    source: str = "notes"
    updated_at: float = 0.0           # 秒级时间戳（覆盖式更新的「最新」判据）
    search_queries: list[str] = field(default_factory=list)  # 头部 `## Search Queries` 关键词（词法检索用）
    pinned: bool = False              # 常驻标记：True ⇒ 正文每轮无条件注入推理上下文（独立块，change 0149）
    pin_priority: int = 0             # 常驻优先级（高者优先在场；0 ⇒ canonical 省略该行，change 0154）

    @property
    def path(self) -> str:            # canonical 相对路径（派生）
        return f"{self.note_id}.md"
```

**canonical 文件格式**（`render_note` / `parse_note` 互为逆，单一真源）：

```markdown
# <title>

- id: <note_id>
- tags: a, b
- source: notes
- updated_at: 1759600000.0
- pinned: true

## Search Queries

- <q1>

## Notes

<正文>
```

辅助函数：

```python
def render_note(note: NoteEntry) -> str: ...
def parse_note(text: str, *, note_id: str | None = None, source: str = "notes") -> NoteEntry: ...
def slug_topic(text: str, *, max_len: int = 48) -> str: ...
    """任务/主题文本 → note_id slug：保留 `str.isalnum()` 字符（含 CJK），空白/标点折为 `-`，截断。"""
```

---

## 2. `MarkdownBackend`（`core.notes.backend`）—— 实现 `MemoryBackend` Protocol

```python
class MarkdownBackend:
    def __init__(self, root: Path) -> None: ...

    # MemoryBackend Protocol（memory/protocol.py）—— 签名不改
    def get(self, layer: Layer, entry_id: MemoryId) -> MemoryEntry | None: ...
    def put(self, entry: MemoryEntry) -> MemoryId: ...
    def search(self, query: str, layer: Layer | None = None) -> list[MemoryEntry]: ...
    def list_index(self) -> IndexEntry: ...
    def delete(self, entry_id: MemoryId) -> None: ...
```

- 映射：`MemoryEntry.content` = **canonical 全文**（自描述）⇒ `get` 用同一解析器还原 `tags`/`source`/`ts`，
  **不丢字段**。
- `put` = **覆盖式**：先写 `root/<id>.md.tmp` 再 `os.replace`（原子；替换前中断不留半截 canonical 文件）。
- `search` = 纯词法（标题 / tags / `## Search Queries` / 正文分词命中占比 > 0），**不建向量库**。
- `list_index` = 全部 `*.md` → `IndexEntry([(note_id, "L2")])`。

---

## 3. `NoteStore`（`core.notes.store`）—— Plugin 门面

```python
class NoteStore(Plugin):
    plugin_id = "notes.store"
    generation = 1
    coeffects = ["filesystem:write"]

    def __init__(self, backend=None, *, path: Path | None = None, clock=None) -> None: ...

    # Plugin 生命周期
    def load(self) -> None: ...
    def unload(self) -> None: ...
    def check(self) -> bool: ...

    # 读写面
    def get(self, note_id: str) -> NoteEntry: ...                 # 缺 → NoteError(NOTE_NOT_FOUND)
    def create(self, note_id: str, *, title="", content="", tags=None) -> NoteEntry: ...  # 已存在 → TOPIC_EXISTS
    def ensure(self, note_id: str, *, title="", content="", tags=None) -> NoteEntry: ...  # 幂等 get-or-create
    def update(self, note: NoteEntry) -> NoteEntry: ...           # upsert（覆盖式写入）
    def list(self) -> list[NoteEntry]: ...                        # canonical 文件清单（目录）
    def search(self, query: str, *, top_k: int = 5) -> list[NoteEntry]: ...
    def consult(self, query: str, *, top_k: int = 3) -> list[NoteEntry]: ...

    # 循环纪律接缝
    def digest(self, query: str) -> str: ...                      # 确定性：命中笔记摘要 + 笔记清单
    def observe_turn(self, task: str, steps: list[str], *, ok: bool) -> NoteEntry | None: ...

    # 常驻（pinned）面（change 0149；优先级 / 整篇纳入 / 超限可见 change 0154）
    def pinned(self) -> list[NoteEntry]: ...                      # 常驻清单（优先级降序、同优先级 id 升序）
    def pinned_digest(self) -> str: ...                           # 常驻注入块（整篇纳入、无 query、有界）
    def pinned_overflow(self) -> list[str]: ...                   # 因超预算未进场的 note_id（只读）
    def set_pinned(self, note_id: str, *, pinned: bool = True, priority: int = 0) -> NoteEntry: ...
        # 置/清常驻并设优先级（幂等；清常驻同时归零优先级）

```

- `ensure` = 幂等 get-or-create（**不**因已存在而报 `TOPIC_EXISTS`）；`create` 是显式创建、已存在即拒。
- `digest(query)`：`consult(query)` 命中项渲染为「- 标题（note_id）：正文节选」+ `list()` 标题清单；
  总长有界（供 loop 直接注入，不自动全量注入正文）。
  **归档来源排除面**（change 0180 / ADR-0171 / 账本 E117）：命中**节选** SHALL 排除 `source ∈`
  `_ARCHIVE_SOURCES`（＝提升产物 `notes.promote`）的笔记 —— 其正文源自 memory 会话摘要、已由 loop
  「历史摘要（长期）」块每轮注入，同源内容免二次注入；此类仍以**清单标题**在场。**排除仅落在
  `digest` 注入面**：`consult` / `search` / `list` / `pinned_digest` 口径**逐字不变**。
- `observe_turn`：**非默认沉淀路径**（change 0295 / ADR-0285）—— 组合根已改走 `Sedimenter`
  两段式（见 §3.3），本方法保留为低层原语（现有单测与来源守护覆盖），成功轮直写 canonical
  **不再由 `build_runtime` 接线**。以下为原语语义：成功轮把「解决过程」覆盖式写回
  `slug_topic(task)` 主题的 canonical 文件；`ok=False`
  或 slug 为空 ⇒ `None`（不写盘）。写回**原样携带**既有 `pinned` 标记（逐轮写回不抹除常驻）。
  **来源守护**（change 0151 / ADR-0143）：撞上来源**非** `notes.turn` 的既有笔记 ⇒ **不覆写**该主题，
  沉淀改写入派生主题 `<topic>-<n>`（`n` 为 2 起、取首个「不存在或来源为 `notes.turn`」者）。
  **有意义闸门 + 可读正文**（change 0171 / ADR-0162）：`steps` **为空**（纯文字回复轮 —— 无工具
  动作）⇒ `None`（不写盘，琐碎轮不成篇）；`steps` 为**人类可读**行（loop 侧 `_action_steps` 交付，
  「工具名（有界参数摘要）→ 有界结果节选」），写入正文**不含** ReAct 消息原文（JSON dump）与整篇
  工具输出、长度有界。**正文逐行脱敏**（change 0254 / ADR-0245）：每条行动行先经 memory 侧同一份
  `redact_secrets`（命中段 → `<redacted>`）再拼接 —— 工具名 / 路径 / 动作结构保留；判据（闸门）
  仍基于未脱敏行。
  **效应闸门**（change 0176 / ADR-0167）：`steps` 非空但**不含任何成功的写效应工具动作** ⇒ 同样
  `None`（不写盘）—— 纯读型动作（`web_fetch` / `file_read` / `context_read` / `list`）产出的是**素材**
  （归 memory 侧 keyfact 抽取），不进 canonical 知识层。写效应工具集 `_WRITE_EFFECT_TOOLS` =
  `file_write` / `file_patch` / `code_run` / `gate_run` / `install` / `uninstall`；工具名从 steps 行
  **前缀解析**（行首至首个 `（`，剥 `tools.` 前缀）；行内含 `错误：`（失败观察）⇒ 不计写效应；
  非已知工具名 ⇒ 保守判为无写效应。判据**确定性**、零 LLM。
- `pinned()`：次序 = **`pin_priority` 降序、同优先级 `note_id` 升序**（确定性）—— 在场判据是**显式
  优先级**，不是 `note_id` 字典序（change 0154）。
- `pinned_digest()`：常驻笔记**完整正文**（非节选）、无 query 入参（每轮无条件）、按 `pinned()` 次序拼接，
  **整篇纳入**（超预算篇**整篇**排除、其后各篇不挤入 —— 在场集合＝优先级次序前缀；**首篇**自身超限时仍
  整篇纳入，块不为空），总长有界于 `_MAX_PINNED_CHARS`(4000)（首篇例外除外）；空正文的常驻笔记不占块、
  不计未进场；块内不含 `updated_at`（跨轮字节稳定）。注入块**超预算**（发生排除，或单篇超限）⇒ 经
  `warnings.warn` 留痕。
- `pinned_overflow()`：**只读**返回因超预算**未进场**的 `note_id`（次序同 `pinned()`；首篇超限者不在其列）。
- `set_pinned(note_id, *, pinned=True, priority=0)`：缺失 ⇒ `NOTE_NOT_FOUND`；**幂等**（`pinned` 与
  `priority` **皆**未变 ⇒ 不写盘、不 bump `updated_at`）；**清常驻同时归零优先级**；真变更走同一
  `update()` 原子覆盖写路径（不另开第二写路径）。

### 3.1 会话摘要提升（`core.notes.promote`，change 0150 / ADR-0142 / 账本 E94）

**独立工作流函数**（**非** `NoteStore` 方法 —— `NoteStore` 是存储门面，提升是工作流；独立便于不碰
存储 / CLI 即可单测）：

```python
from core.notes import promote_session_summary

def promote_session_summary(
    store: NoteStore,
    summary: MemoryEntry,       # 由调用方用 MemoryStore.summary_for(session_id) 取回
    *, session_id: str,
    as_note_id: str | None = None,
    title: str = "",
    pin: bool = True,           # 显式路径缺省 True；半自动路径传 False（不自动置常驻）
) -> NoteEntry | None: ...      # None ⇒ 派生 id 为空且未给显式 id，或撞非 promotion 来源（不写盘）
```

- 触发形态 = **显式**（CLI `notes promote` / 上层调用）**或**由 memory 压实侧「摘要首次越过滚动上界」
  半自动（经注入的提升钩子交付一次；change 0153 / ADR-0145 / 路线图 G3）；**零 LLM 调用**。
- `note_id` = `as_note_id or f"session-{slug_topic(session_id)}"`；**幂等覆盖**（同会话重复提升命中同一
  note、不增长），复用**唯一**写路径 `NoteStore.update()`。
- 产出 `source == "notes.promote"`、`tags` 含 `session:<sid>` 与 `summary`；属**全局文档层**
  （`session_id` 仅是 id 派生输入与来源标注，**不是**隔离维度）。**置常驻分路径**：显式路径 `pin=True`
  ⇒ `pinned=True`（每轮无条件注入）；半自动路径 `pin=False` ⇒ **普通** canonical 笔记（不占常驻预算、
  不以硬约束身份逐轮进场；承 ADR-0142 局限①）。
- **注入面单通道**（change 0180 / ADR-0171）：产出 `source="notes.promote"` ⇒ 其**正文不进** Consult
  命中节选（`digest` 的归档来源排除面，见 §3），只以**清单标题**在场 —— 摘要正文已由 loop
  「历史摘要（长期）」块承载（**单通道**，免同源二次注入）。**显式**路径的 `pin=True` 常驻注入**语义
  不变**（跨会话用途所需），仅其节选不再重复进命中面。检索面（`consult`/`search`/`list`）**不变**。
- **来源守护**（change 0151 / ADR-0143）：目标 `note_id` 撞来源**非** `notes.promote` 的既有笔记且未给
  显式 `as_note_id` ⇒ 返回 `None`、**不写盘**、CLI 非零退出；显式 `as_note_id` ⇒ 视为**显式授权**、照常覆写。
- 写入**不接** `EffectTracker`（承 canonical 文档层既有取舍，与 `pin/unpin`/`observe_turn` 一致）。

### 3.2 里程碑报告锚定（`core.notes.milestone`，change 0273 / ADR-0263 / 台账 E209）

**独立工作流函数**（非 `NoteStore` 方法；`NoteStore` 仍是唯一写路径入口）：

```python
from core.notes import close_milestone

def close_milestone(
    store: NoteStore,
    *, milestone: str,                  # 里程碑名（派生 note_id）
    session_id: str = "",
    summary: MemoryEntry | None = None, # 调用方用 MemoryStore.summary_for(session_id) 取回
    key_facts: Iterable[MemoryEntry] = (),  # 该会话 keyfact（按 id 升序装配）
    conclusions: Sequence[str] = (),
    decisions: Sequence[str] = (),
    constraints: Sequence[str] = (),
    as_note_id: str | None = None,
    title: str = "",
    priority: int = 100,                # MILESTONE_PIN_PRIORITY
) -> NoteEntry | None: ...              # None ⇒ 无内容 / 派生 id 为空 / 来源冲突（不写盘）
```

- 正文固定节次序：**结论 → 关键决策 → 硬约束 → 关键事实**（空节省略）；摘要正文并入结论节，
  keyfact 按条目 `id` 升序 ⇒ 确定性、零 LLM。
- `note_id = as_note_id or "milestone-" + slug_topic(milestone)`；**幂等覆盖**（同一里程碑重复收口
  命中同一 note、不增长），复用唯一写路径 `NoteStore.update()`。
- 产出 `source == "notes.milestone"`、`pinned=True`、`pin_priority=priority`（缺省 **100**，
  高于人工 `notes pin` 的缺省 0）⇒ 经既有「常驻笔记」块注入（**不新增注入块**）。
- **来源守护**（与 promotion 同构）：撞来源非 `notes.milestone` 的既有笔记且未给 `as_note_id`
  ⇒ 返回 `None`、不写盘；显式 `as_note_id` 视为授权。既有 tags 并入、标题缺省沿用既有。
- **有界与脱敏**：装配内容统一 `redact_secrets`；正文 ≤ `MAX_MILESTONE_CHARS`（3000）——
  **保留头部** + 含被截字符数的标记（`…[truncated N chars]…`）。
- 写入**不接** `EffectTracker`（承文档层既有取舍）；属全局文档层，`session_id` 只是内容来源与
  派生输入，不是隔离维度。
- **显式触发**：不自动置常驻（ADR-0263 D7；方案 C 维持否决）。

### 3.3 沉淀候选区与晋升（`core.notes.sediment`，change 0295 / ADR-0285 / 台账 E231）

**两段式沉淀**：成功轮只产**候选**，显式晋升后才写 canonical。notes 包**不 import LLM/skills/loop**；
模型调用经 `CandidateWriter = Callable[[str], str]` 由组合根注入。

```python
from core.notes import (
    CANDIDATE_LIMIT, AUTO_PROMOTE_MIN_SUPPORT, SEDIMENT_SOURCE,
    Candidate, CandidateStore, Sedimenter, candidate_writer_with,
)

@dataclass
class Candidate:
    candidate_id: str            # = topic slug
    title: str = ""
    content: str = ""            # Markdown（≤4000）
    tags: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    kind: str = "fact"           # decision|procedure|fact|preference|pitfall
    support: int = 1
    first_seen: float = 0.0
    last_seen: float = 0.0
    trace_digests: list[str] = field(default_factory=list)   # ≤8
    evidence: str = ""           # 任务首行（≤120）

class CandidateStore:
    def __init__(self, path: Path | None = None, *, limit: int = CANDIDATE_LIMIT,
                 clock: Callable[[], float] | None = None) -> None: ...
    def list(self) -> list[Candidate]: ...          # 按 (-last_seen, candidate_id)
    def get(self, candidate_id: str) -> Candidate: ...
    def upsert(self, candidate: Candidate, *, trace_digest: str = "") -> Candidate: ...
    def remove(self, candidate_id: str) -> bool: ...

class Sedimenter:
    def __init__(self, note_store, *, writer: CandidateWriter | None = None,
                 path: Path | None = None, store: CandidateStore | None = None,
                 clock: Callable[[], float] | None = None,
                 auto_promote: bool = False,
                 min_support: int = AUTO_PROMOTE_MIN_SUPPORT) -> None: ...

    def observe_turn(self, task: str, steps: list[str], *, ok: bool,
                     reply: str = "") -> Candidate | None: ...
    def promote(self, candidate_id: str, *, as_topic: str | None = None,
                title: str = "") -> NoteEntry: ...
    def reject(self, candidate_id: str) -> bool: ...
    def list_candidates(self) -> list[Candidate]: ...
    def get_candidate(self, candidate_id: str) -> Candidate: ...
```

- **预滤**（确定性、零模型调用）：`ok` 为真、`steps` 非空、含**写效应**动作（复用
  `store.has_write_effect`）、任务去空白 ≥6 字符、writer 非空 —— 任一不满足即返回 `None`。
- **候选区**：`$CORE_STATE_DIR/notes-candidates.json`（runtime/CLI 传路径）；0600 原子写、
  `RLock` 串行化；上限 **128**（`CANDIDATE_LIMIT`，按 `last_seen/first_seen/id` 淘汰最旧）；
  损坏/结构不符 ⇒ warn（只报条数）并空态启动。候选**不进入** `digest/list/search`。
- **提炼与解析**：prompt 含任务/轨迹/最终回复（**先脱敏、再有界**：task≤500、≤20 步×300、
  reply≤1500）与已有 topic/note id（≤40）；要求严格 JSON（容忍围栏，取首 `{` 至末 `}`）。
  `durable is not True`、topic 非 str / slug 为空、正文空 ⇒ 丢弃（fail-closed）。
- **支持度**：`blake2b(脱敏 steps)` 已在候选 `trace_digests` 中 ⇒ 只刷新内容与 `last_seen`，
  support 不增；否则 +1（列表最多保留 8 个 digest）。
- **晋升**：`promote()` 复用 `NoteStore.update()`（唯一 canonical 写路径），产出
  `source="notes.sediment"`；既有主题来源非 sediment ⇒ `NoteError(TOPIC_EXISTS)`；既有
  `sediment:<other>` 标签 ⇒ 同样拒绝（候选保留，CLI 提示 `--as`）；既有的 `pinned/pin_priority`
  保留，tags 取并集并追加 `sediment:<candidate_id>`；成功后移除候选。
- **自动晋升**：`auto_promote` 缺省 `False`；开启后当 `support >= min_support`（缺省 2）
  尝试晋升，冲突只 warn、候选保留。
- `candidate_writer_with(llm)`：把「prompt → 文本」模型调用适配为 `CandidateWriter`。

### 3.4 存量清理：回收目录（`core.notes.prune`，change 0295 / ADR-0285）

```python
from core.notes import PruneResult, prune_notes

def prune_notes(store: NoteStore, *, source: str, trash_dir: Path,
                dry_run: bool = False, include_pinned: bool = False,
                clock: Callable[[], float] | None = None) -> PruneResult: ...

@dataclass
class PruneResult:
    moved: list[str]
    kept_pinned: list[str]
    trash_path: Path | None = None
    manifest_path: Path | None = None
```

- 过滤 `store.list()` 中 `source` 匹配者；缺省跳过 `pinned` 并计入 `kept_pinned`。
- 逐篇 `store.raw(note_id)`（**原字节**）写入 `trash_dir/<UTC stamp>/<note_id>.md`（0600），
  再 `store.remove(note_id)`；全部完成后原子写 `manifest.json`（0600，含 source/timestamp/
  moved/kept_pinned）。`dry_run` 只返回 `moved`、不建目录。
- **恢复** = 把回收文件复制回 canonical 笔记目录。0 篇移动 ⇒ CLI 退出 1（dry-run 除外）。

---

## 4. 错误码（`core.notes.errors`）

| 码 | 触发 |
|---|---|
| `NOTE_NOT_FOUND` | `get` 指定 note 不存在 |
| `TOPIC_EXISTS` | 显式 `create` 一个已存在的主题（不覆盖既有内容） |

```python
class NoteErrorCode(StrEnum):
    NOTE_NOT_FOUND = "NOTE_NOT_FOUND"
    TOPIC_EXISTS = "TOPIC_EXISTS"

class NoteError(Exception):
    code: NoteErrorCode
    message: str
```

---

## 5. loop 接线（loop **不 import notes**）

- `core.loop.protocol.LoopContext` 新增附加字段 `notes: str = ""`（缺省空 ⇒ 既有行为逐字不变）与
  `pinned_notes: str = ""`（**独立字段** —— 常驻面与命中面分列成块，不得折入 `notes`；change 0149）。
- **Update 侧（change 0295 / ADR-0285）**：`TurnObserver = Callable[[str, list[str], bool, str], object]`
  —— 第 4 参为 `ctx.reply`（模型最终回复，**不可信文本**，由 `Sedimenter` 先脱敏再截断）；
  组合根 `_loop_hooks` 把它交给 `Sedimenter.observe_turn`，不再调用 `NoteStore.observe_turn`。
- `core.loop.default` 新增钩子别名（**纯 Callable，不含 notes 类型**）：

```python
NotesConsult = Callable[[str], str]      # 任务文本 → 笔记摘要文本（loop 不 import notes，组合根注入）
PinnedNotesConsult = Callable[[], str]   # **零参** → 常驻注入块（签名即契约：与当轮任务无关）
```

  `DefaultLoop(..., notes_consult=...)`：`astream` 中 `perceive` 之后调用，写入 `ctx.notes`；抛错降级留痕、
  不改本轮结局。`DefaultLoop(..., pinned_notes_consult=...)`：同处调用（`_load_pinned_notes`），写入
  `ctx.pinned_notes`；抛错降级留痕 `pinned_notes_consult_failed`、不改本轮结局。
  **Update 侧复用既有 `TurnObserver`**（`_notify_turn` 即任务后唯一收尾点）。
- `core.loop.planner.LLMPlanner._system_prompt`：`ctx.notes` 非空时插入「相关笔记」块；`ctx.pinned_notes`
  非空时插入**独立**「常驻笔记（任务级硬约束，逐轮生效，勿违背）」块，位置**紧随宪法规则、先于相关事实**。

---

## 6. CLI 触达点（`entry.py`）

| 命令 | 语义 |
|---|---|
| `notes list` | 列出 canonical 笔记清单（id / 标题 / 更新时间；常驻条目行尾追加 `\t[pinned]`） |
| `notes show <note_id>` | 打印一篇 canonical 笔记（`NOTE_NOT_FOUND` ⇒ 退出码非零） |
| `notes search <query>` | 词法检索（标题 / tags / Search Queries），打印命中 note 摘要 |
| `notes pin <note_id> [--priority N]` | 置常驻并设优先级（高者优先在场；幂等；缺失 ⇒ `NOTE_NOT_FOUND` 非零退出） |
| `notes unpin <note_id>` | 清常驻标记（优先级一并归零） |
| `notes pinned` | 列出常驻笔记：`note_id` / 标题 / 优先级 / **是否进场**（超预算篇目报为未进场，change 0154） |
| `notes promote <session-id> [--as NOTE_ID] [--title TITLE]` | 会话摘要 → canonical 常驻笔记（显式提升；幂等覆盖；会话无摘要 / 派生 id 为空 / 撞非 promotion 来源且未给 `--as` ⇒ 非零退出、不写盘） |
| `notes milestone <name> [--session SID] [--as NOTE_ID] [--title TITLE] [--priority N] [--conclusion T]... [--decision T]... [--constraint T]...` | 里程碑收口 → 结构化报告并置常驻（确定性装配；缺省优先级 100；幂等覆盖；无内容 / 派生 id 为空 / 撞非 milestone 来源且未给 `--as` ⇒ 非零退出、不写盘） |
| `notes candidates` | 列出沉淀候选（id / 支持度 / 标题 / 最后出现时间；零模型调用） |
| `notes candidate-show <id>` | 打印一条候选全文（未知 id ⇒ 非零退出） |
| `notes candidate-promote <id> [--as NOTE_ID] [--title TITLE]` | 候选 → canonical（`source=notes.sediment`；来源/异候选冲突 ⇒ 非零退出、候选保留） |
| `notes candidate-reject <id>` | 丢弃一条候选（未知 id ⇒ 非零退出） |
| `notes prune [--source S] [--dry-run] [--include-pinned] [--trash-dir DIR]` | 按来源把 canonical 笔记移入回收目录（缺省 `notes.turn`；跳过 pinned；写 manifest；0 篇移动退出 1） |

**入口侧写路径（非 `notes` 命令）**：`rag ingest <path> --doc-id ID --summarize`（change `0213`／
ADR-0203）⇒ 文档摘要落 `doc-<slug(doc_id)>`、`source="notes.rag"`、**恒非 pinned**（幂等覆盖；
受双守护：不被逐轮写回 / 提升覆写；**进 digest 命中节选**）。桥在 `entry._doc_summary_note`（调
**公开** `NoteStore.update`）—— **`notes` 包公开面无改动**（ADR-0148 边界；详见 ADR-0203 D4）。

一次 `notes` 命令 = 一次性进程；canonical 目录是**落盘真源** ⇒ 一次写入在后续进程可见。
