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
```

- `ensure` = 幂等 get-or-create（**不**因已存在而报 `TOPIC_EXISTS`）；`create` 是显式创建、已存在即拒。
- `digest(query)`：`consult(query)` 命中项渲染为「- 标题（note_id）：正文节选」+ `list()` 标题清单；
  总长有界（供 loop 直接注入，不自动全量注入正文）。
- `observe_turn`：成功轮把「解决过程」覆盖式写回 `slug_topic(task)` 主题的 canonical 文件；`ok=False`
  或 slug 为空 ⇒ `None`（不写盘）。

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

- `core.loop.protocol.LoopContext` 新增附加字段 `notes: str = ""`（缺省空 ⇒ 既有行为逐字不变）。
- `core.loop.default` 新增钩子别名（**纯 Callable，不含 notes 类型**）：

```python
NotesConsult = Callable[[str], str]   # 任务文本 → 笔记摘要文本（loop 不 import notes，组合根注入）
```

  `DefaultLoop(..., notes_consult=...)`：`astream` 中 `perceive` 之后调用，写入 `ctx.notes`；抛错降级留痕、
  不改本轮结局。**Update 侧复用既有 `TurnObserver`**（`_notify_turn` 即任务后唯一收尾点）。
- `core.loop.planner.LLMPlanner._system_prompt`：`ctx.notes` 非空时插入「相关笔记」块。

---

## 6. CLI 触达点（`entry.py`）

| 命令 | 语义 |
|---|---|
| `notes list` | 列出 canonical 笔记清单（id / 标题 / 更新时间） |
| `notes show <note_id>` | 打印一篇 canonical 笔记（`NOTE_NOT_FOUND` ⇒ 退出码非零） |
| `notes search <query>` | 词法检索（标题 / tags / Search Queries），打印命中 note 摘要 |

一次 `notes` 命令 = 一次性进程；canonical 目录是**落盘真源** ⇒ 一次写入在后续进程可见。
