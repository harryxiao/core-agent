# 常驻笔记预算：显式优先级 + 整篇纳入 + 超限可见 · change 0154 · 记忆三面路线图 G1

## 为什么

0149（ADR-0141 / 账本 E93）给了**常驻（pinned）笔记**——任务级硬约束锚，每轮无条件注入。但它把
「谁进场」交给了一条**任意判据**，ADR-0141 **局限②** 已自认：

> 总量有界于 `_MAX_PINNED_CHARS`(4000) 但**无 per-note 上限** —— 多篇各自很长时仍受总量约束、
> **末篇可能被截断**。

现状（`src/core/notes/store.py::pinned_digest`）：

```python
sections = [f"## {title}（{note_id}）\n{content}" for note in self.pinned() if ...]
return "\n\n".join(sections)[:_MAX_PINNED_CHARS]
```

两个缺陷，且都在**硬约束**这个语义上放大：

1. **半篇** —— `[:4000]` 是**字符切片**，可把某篇常驻笔记**从中间切断**。半截硬约束可能**语义反转**
   （「必须 A，除非 B」被切成「必须 A」），比缺席更危险。且被切的是**哪一篇**由 `note_id` 字典序决定
   ⇒ 一个 `zzz-*` 约束被系统性饿死，`aaa-*` 恒在场。
2. **静默** —— 谁没进场、谁被切半，**无留痕、无 CLI 可见面** ⇒ 操作者以为约束在生效，实际不在。

⇒ G1 = 把「谁在场」交给**显式优先级**（操作者的决定），装配改为**整篇纳入**（绝不半篇），并把
**未进场篇目**变成**可见**。这是把 0149 的**意图**（硬约束锚）**做完**，不是新增语义。

## 改什么

**canonical 格式**（`models.py`，仿 0149 `pinned` 行先例）：

- `NoteEntry` 新增 `pin_priority: int = 0`。
- `render_note`：`pin_priority != 0` 时输出 `- pin_priority: <n>`，否则**省略** ⇒ 既有文件逐字不变。
- `parse_note`：读回整数；**无法识别 ⇒ 0**（fail-closed：手误绝不意外抬高优先级）。

**存储门面**（`store.py`）：

- `set_pinned(note_id, *, pinned=True, priority=0)`：置常驻并设优先级；**清常驻同时归零优先级**；
  幂等判据由「`pinned` 未变」扩为「`pinned` 与 `priority` **皆**未变」。
- `pinned()`：次序由 `note_id` 升序改为 **`pin_priority` 降序、同优先级 `note_id` 升序**（确定性）。
- `pinned_digest()`：**整篇纳入**（超预算篇**整篇排除**，其后各篇不再挤入 —— 在场集合是优先级次序的
  **前缀**）；**唯一例外**：次序首篇自身超限时**仍整篇纳入**（块 SHALL NOT 为空）；发生排除时
  `warnings.warn` 留痕。
- `pinned_overflow() -> list[str]`：**新增只读访问器** —— 被预算排除的 `note_id` 列表。
- `observe_turn`：逐轮写回保留 `pin_priority`（与既有保留 `pinned` 同口径）。

**CLI**（`entry.py`）：`notes pin <id> [--priority <n>]`；**新增** `notes pinned`（列出常驻笔记的
`note_id` / 标题 / 优先级 / **是否在场**）——「未进场篇目」的报出面。`notes list` 输出**逐字不变**。

### 设计原则（与架构同向）

- **显式优于隐式** —— 「谁在预算内」是**操作者的显式决定**（`--priority`），不是 `note_id` 字典序的
  副作用。与 0151「来源守护 = 显式授权」同取向。
- **完整性优于填满** —— 硬约束**要么整篇、要么不在场**；半篇是最坏的中间态。
- **失败可见** —— 超限**留痕 + CLI 可查**，不静默。
- **零回归** —— `pin_priority` 缺省 `0` 且**省略按 0 排序** ⇒ 未设优先级的既有常驻笔记行为**逐字不变**
  （仅当多篇合计超预算且未设优先级时，「在场集合」由「4 000 字切片」变为「优先次序前缀」——这正是修复）。

## 规格

- `notes` **MODIFIED Requirement「常驻（pinned）笔记（任务级硬约束锚）」**：追加 `pin_priority`
  字段 / canonical 行 / fail-closed 解析、`set_pinned` 的 `priority` 形参、`pinned()` 优先级次序、
  `pinned_digest()` 整篇纳入 + 超限可见 + 首篇例外、`pinned_overflow()` 访问器、CLI
  `notes pin --priority` 与 `notes pinned`；Scenario **保留全部 5 个既有场景名**，新增 4 个
  （优先级往返+幂等+逐轮写回不抹除 / 优先级决定在场 / 整篇纳入绝不半篇 / 超限可见 / 单篇超限仍整篇纳入）。
- 其余 Requirement / Scenario **逐字不变**。

本项**非** `skip_specs`（行为与 canonical 格式变更、可见契约）⇒ 走规格先行、**不写** `.openspec.yaml`。

## 非目标（明确不做）

- **不**加 per-note 上限 / **不**改 `_MAX_PINNED_CHARS` 数值（4000）。
- **不**在 pin 时**拒绝**超预算的置位（超限是**告警 + 可见**，非硬失败；承 plan 既定）。
- **不**新增 `notes` 错误码；**不**接 `EffectTracker`（承 ADR-0099 canonical 层取舍）。
- **不**做 G4（结构化实体抽取）/ G5（rag 定位）——**不夹带**。
- **不**引三方库。

## 风险与红线

- **密钥红线**：本 change 只搬运既有 canonical 正文与**整数字段**，不触密钥面、不读配置值。
- **canonical 格式**：`pin_priority` 行为**可选追加行**，缺省省略 ⇒ 既有文件渲染输出**逐字不变**
  （`render_note` / `parse_note` 仍互为逆）。
- **行为变更面**：仅当多篇常驻合计超预算时，在场集合由「4 000 字切片」变为「优先级次序前缀」，
  且**留痕**；单篇 / 未超限场景**逐字不变**。
- **零回归**：`tests/test_notes.py` 既有用例除 `test_store_pinned_digest_is_deterministic_and_capped`
  （**正是**编码被修缺陷的用例，按新契约改写）外逐字不动、全绿。

## 影响面

改动 `src/core/notes/models.py`（`pin_priority` 字段 + 渲染 / 解析）、`src/core/notes/store.py`
（次序 + 整篇装配 + 超限留痕 + `pinned_overflow` + `set_pinned` 签名 + `observe_turn` 保留）、
`src/core/entry.py`（`notes pin --priority` + `notes pinned`）。测试
`tests/test_notes_pinned_budget.py`（新增）、`tests/test_notes.py`（1 条用例按新契约改写）。
文档 `doc/02-modules/notes.md`、`doc/03-interfaces/notes-interface.md`、
`doc/04-testing/test-cases.md`（新 `## 70.`）、`doc/01-architecture/adr.md`（ADR-0146）、
`coding-plan/known-risk.md`（G1 行 + §3 ADR-0146 局限行）。
