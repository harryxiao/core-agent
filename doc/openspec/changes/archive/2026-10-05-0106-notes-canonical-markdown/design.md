# 设计 — notes：canonical Markdown 真相层（change 0106）

## 1. 分层与依赖方向

```
L3 装配：runtime（组合根）── 构造 NoteStore / 构造内置 Skill / 注入两枚闭包 ──► DefaultLoop
L2 记忆：notes（NoteEntry + MarkdownBackend + NoteStore）── 依赖 core.memory（Protocol/数据类）
         注意：notes **不依赖 core.skills**（内置 Skill 的构造放在组合根）
L3 loop：只认 Callable 别名（NotesConsult），**不 import notes**（架构红线）
```

依赖实测（供 `git diff` 校验用）：

| 文件 | 是否改动 |
|---|---|
| `src/core/plugin_registry/*` | **不改**（无外部插件装载路径） |
| `src/core/memory/store.py`（`MemoryStore`） | **不改** |
| `src/core/memory/file_backend.py`（`FileBackend`） | **不改** |
| `src/core/rag/*` | **不改** |
| `src/core/memory/protocol.py`（`MemoryBackend`） | **不改**（只被实现） |

## 2. canonical Markdown 文件格式（`models.py` 单一真源）

```markdown
# <title>

- id: <note_id>
- tags: a, b
- source: notes
- updated_at: 1759600000.0

## Search Queries

- <q1>
- <q2>

## Notes

<正文>
```

- 文件**自描述**：标题、元数据、检索关键词、正文全在其中 ⇒ 人类可读、可 diff、可 review。
- `render_note` / `parse_note` 互为逆（往返测试守住）。
- `Search Queries` 缺省由 `title + tags + 正文首行` 派生（无 embedding，纯词法）。

## 3. `MarkdownBackend`（实现 `MemoryBackend`，签名不改）

| Protocol 方法 | 语义 |
|---|---|
| `put(entry)` | **覆盖式**写 `root/<entry.id>.md`：先写 `*.tmp` 再 `os.replace`（原子；半截绝不落 canonical） |
| `get(layer, entry_id)` | 读文件 → `MemoryEntry(content=全文, tags/source/ts 由同一解析器还原)`；无文件 → `None` |
| `search(query, layer=None)` | 逐文件词法匹配（标题 / tags / Search Queries / 正文），分数 = 命中词占比 > 0 者，降序 |
| `list_index()` | 全部 `*.md` → `IndexEntry([(note_id, "L2")])` |
| `delete(entry_id)` | 删 canonical 文件（幂等） |

`MemoryEntry.content` = **canonical 全文**（含头部），故 `get` 可无损还原 tags/source/ts——不丢字段。

## 4. `NoteStore`（Plugin 门面）

```
plugin_id = "notes.store"；coeffects = ["filesystem:write"]
get(note_id) -> NoteEntry            # NOTE_NOT_FOUND
create(note_id, ...) -> NoteEntry    # TOPIC_EXISTS（不覆盖既有）
ensure(note_id, ...) -> NoteEntry    # 幂等 get-or-create
update(note) -> NoteEntry            # upsert：覆盖式写回（最新最权威）
consult(query, top_k=3) -> list[NoteEntry]
list() -> list[NoteEntry]
digest(query) -> str                 # 确定性：命中笔记摘要 + 笔记清单（供 loop 钩子直接注入）
observe_turn(task, steps, *, ok) -> NoteEntry | None   # 成功轮覆盖式写回「解决过程」
```

- `observe_turn`：`ok=False` 或派生不出主题（slug 为空）⇒ 返回 `None`，不写盘。
- 失败降级与 `_notify_turn` 同口径：**调用方（组合根闭包）** 兜异常，store 自身不吞。

## 5. loop 接线（零 import）

- `loop/protocol.py`：`LoopContext.notes: str = ""`（附加字段，缺省空 ⇒ 既有行为逐字不变）。
- `loop/default.py`：
  - 新别名（含架构红线注释）`NotesConsult = Callable[[str], str]`（任务文本 → 笔记摘要文本）。
  - ctor 增 `notes_consult: NotesConsult | None = None`。
  - `astream` 中 `ctx = self.perceive(...)` **之后**：`self._consult_notes(ctx, trace_id)` 填入 `ctx.notes`。
  - 抛错 ⇒ `_trace(..., "notes_consult_failed", ...)`，`ctx.notes = ""`，**不改本轮结局**。
- `loop/planner.py`：`_system_prompt` 在「相关事实」与「可用技能」之间插入「相关笔记」块（`ctx.notes` 非空才插）。
- **Update 侧复用既有 `TurnObserver`**（`_notify_turn` 已是「任务后」钩子）：组合根的 `on_turn` 闭包在
  `sop_extractor.observe(...)` 之外追加 `note_store.observe_turn(...)`。**不新增第二个收尾钩子**——
  `_notify_turn` 本就是任务后唯一收尾点，重复接线会产生双真源。

## 6. 内置技能（组合根构造，不下沉 `notes/`）

```python
Skill(
    skill_id="skills.notes.consult_build_update",
    description="文档化记忆循环：先 Consult 相关笔记、再 Build、再 Update 写回 canonical Markdown",
    task_types=["notes", "documentation", "remember", "决策记录", "研究笔记", "解决过程"],
    instructions="1) Consult：… 2) Build：… 3) Update：…（去重、精炼、保持权威）",
    version="v1", status="active",
)
```

经既有 `_loop_hooks.hints` → `SkillRouter.match` → planner「可用技能」块触达模型（复用既有通路，不新造）。
