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
- `observe_turn`：成功轮把「解决过程」覆盖式写回 `slug_topic(task)` 主题的 canonical 文件；`ok=False`
  或 slug 为空 ⇒ `None`（不写盘）。写回**原样携带**既有 `pinned` 标记（逐轮写回不抹除常驻）。
  **来源守护**（change 0151 / ADR-0143）：撞上来源**非** `notes.turn` 的既有笔记 ⇒ **不覆写**该主题，
  沉淀改写入派生主题 `<topic>-<n>`（`n` 为 2 起、取首个「不存在或来源为 `notes.turn`」者）。
  **有意义闸门 + 可读正文**（change 0171 / ADR-0162）：`steps` **为空**（纯文字回复轮 —— 无工具
  动作）⇒ `None`（不写盘，琐碎轮不成篇）；`steps` 为**人类可读**行（loop 侧 `_action_steps` 交付，
  「工具名（有界参数摘要）→ 有界结果节选」），写入正文**不含** ReAct 消息原文（JSON dump）与整篇
  工具输出、长度有界。
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
- **来源守护**（change 0151 / ADR-0143）：目标 `note_id` 撞来源**非** `notes.promote` 的既有笔记且未给
  显式 `as_note_id` ⇒ 返回 `None`、**不写盘**、CLI 非零退出；显式 `as_note_id` ⇒ 视为**显式授权**、照常覆写。
- 写入**不接** `EffectTracker`（承 canonical 文档层既有取舍，与 `pin/unpin`/`observe_turn` 一致）。

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

一次 `notes` 命令 = 一次性进程；canonical 目录是**落盘真源** ⇒ 一次写入在后续进程可见。
