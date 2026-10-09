# Tasks: 语义记忆去重 —— 提升产物退出 Consult 命中面（promotion injection dedup）

**测试先行**：每层先写测试（红），再实现（绿）。四门禁直连二进制、**禁** `uv run`。

## Layer A —— 命中面排除 `src/core/notes/store.py`

- [x] A1. 测试：追加 `tests/test_notes.py`（红：提升产物仍进命中节选）——
  ① 提升产物词法命中 ⇒ `digest()` 无其节选、标题仍在「笔记清单」；② 普通笔记命中 ⇒ 节选照常（回归锚）；
  ③ `consult` / `search` / `list` 对提升产物**逐字不变**（排除只在 `digest`）—— pin「Consult → Build → Update
  循环纪律」新增 Scenario
- [x] A2. 实现：`PROMOTE_SOURCE`（公开常量）+ `_ARCHIVE_SOURCES = frozenset({PROMOTE_SOURCE})` +
  `digest()` 命中集合一行来源过滤

## Layer B —— 来源标记单一真源 `src/core/notes/promote.py`

- [x] B1. 测试：追加 `tests/test_notes_loop.py`（红：`ctx.notes` 含提升正文）——
  ④ 端到端 loop（真实 `NoteStore` + consult 闭包）⇒ `ctx.notes` 不含提升正文、含普通命中；
  ⑤ 提升产物 `pinned=True` ⇒ `ctx.notes` 无其节选 **且** `ctx.pinned_notes` 含完整正文（通道分列）
  —— pin「会话摘要提升」新增 Scenario ②
- [x] B2. 实现：`from .store import PROMOTE_SOURCE, NoteStore`；删本地 `_PROMOTE_SOURCE`（2 处引用替换：
  来源守护比较 / 写入 `source=`）；`_PROMOTE_PREFIX` 不动

## Layer C —— 真实链路联动

- [x] C1. 测试：追加 `tests/test_memory_summary_promotion.py`（红）—— ⑥ 半自动提升落地后，以命中 query
  取 `store.digest()` ⇒ 不含提升正文、含 `session-*` 标题 —— pin「会话摘要提升」新增 Scenario ①
- [x] C2. 无需实现（由 A2/B2 覆盖；本层只作端到端守门）

## Layer D —— 收尾

- [x] D1. 规格 delta：`specs/notes/spec.md`（MODIFIED「Consult → Build → Update 循环纪律」+
  MODIFIED「会话摘要提升（promotion）」；既有 39 Scenario 逐字保留 ⇒ 42）—— 已完成
- [x] D2. `doc/01-architecture/adr.md`：**ADR-0171** + 追踪行
- [x] D3. 模块文档：`doc/02-modules/notes.md` §3.4（Consult 口径加排除面）+ §3.5.1/§3.5.2（半自动产物定位＝留档）
- [x] D4. 接口文档：`doc/03-interfaces/notes-interface.md`（`digest` 契约加排除面；§3.1 提升产物注入面单通道）
- [x] D5. `doc/04-testing/test-cases.md`：新增 `## 93. …（TC-ARCHIVE-DEDUP）` + 基线 bump（2119 → 2125）
- [x] D6. `coding-plan/known-risk.md`：§1 新 **E117** 行 + §3 ADR-0171 局限行
- [x] D7. 四门禁 + `openspec validate <全目录名>` + 手工归档 + `openspec validate --all`
- [x] D8. 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）+ **单次提交**
