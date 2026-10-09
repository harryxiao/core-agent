# Proposal: 语义记忆去重 —— 提升产物退出 Consult 命中面

> 规格：`notes`（**MODIFIED × 2**）

## Why

用户 2026-10-10 复盘「语义记忆--笔记提取重要内容归档，这个和哪一个重复了?」，选定 ① 立账：
**同一份会话摘要，在同一次请求里经两条通道重复注入**。逐行取证（两份探索代理，全部 `file:line` 已核）：

1. **通道 A（记忆侧，全文）**：`loop/default.py:885` `summary_for(session_id)` → L2 条目
   `compaction.summary.<sid>`（`source="compaction"`）→ `ctx.summary_long` → `planner.py:298`
   「历史摘要（长期）」块 —— **滚动最新**（≤`MAX_SUMMARY_CHARS`=2000，越界后开始不可逆稀释）。
2. **通道 B（笔记侧，节选）**：`runtime.py:379-381` `_promote_summary` →
   `promote_session_summary(..., pin=False)`（`notes/promote.py:56`：正文 = 摘要内容）→ canonical 笔记
   `session-<slug>`（`source="notes.promote"`）→ `NoteStore.digest()`（`notes/store.py:166-183`：
   `consult()` 命中节选 ≤200 字符 + `list()` 全量清单标题）→ `ctx.notes` → `planner.py:311`「相关笔记」块。

⇒ 提升产物是**会话摘要的副本**（同一份内容的派生），半自动路径（唯一生产接线，`pin=False`）把它当作
「知识条目」注入 prompt：既重复 token，又让**陈旧冻结快照**与**最新滚动摘要**并列同场（语义噪声）。

**用户已裁决**（AskUserQuestion，2026-10-10，均「推荐」）：
① **让位方向** = 提升产物退出 Consult 命中面（记忆侧长期摘要块留任：每轮在场 + 持续滚动最新；
notes 侧让位：词法命中才在场 + 冻结旧快照）；
② **退出粒度** = 只退「命中的笔记」**节选**，**笔记清单标题保留**（存在性可见，digest 契约最小改）。

**架构边界**（决定了不得走的路）：notes 层不得接受会话维度（红线 +
`tests/test_session_isolation.py:379` 参数化盖住 `digest`）⇒「仅在本会话内去重」在架构上不可行
⇒ 去重只能按**类别**（来源）而非按会话。

## What Changes

1. **命中面排除归档来源**（`src/core/notes/store.py`）：新增模块常量
   `_ARCHIVE_SOURCES = frozenset({"notes.promote"})`；`digest()` 的命中集合加一行来源过滤
   （`consult/search/list/pinned_digest` 口径**逐字不变**）。
2. **来源标记单一真源**（`notes/promote.py`）：字面量 `"notes.promote"` 上移为 `store.py` 的公开常量
   `PROMOTE_SOURCE`，`promote.py` 改为 import（删本地 `_PROMOTE_SOURCE`；`store` 不 import `promote`，
   **无环**）。
3. **loop / memory 零改动**：长期摘要块与「相关笔记」块装配次序、提升钩子契约、`summary_for`、
   压实口径**全部不变**；显式提升路径（CLI，缺省 `pin=True`）语义不变（正文仍经「常驻笔记」块每轮在场）。

## Impact

- **specs**：
  - `notes/spec.md`——**MODIFIED**「Consult → Build → Update 循环纪律」（追加归档来源排除面句 + 1 Scenario）、
    **MODIFIED**「会话摘要提升（promotion）」（改写半自动路径定位句 + 追加单通道句 + 2 Scenario）；
    既有 39 条 Scenario 逐字保留 ⇒ **42**。
  - `memory/spec.md` / `loop/spec.md` **不动**（契约无变化）。
- **src**：`notes/store.py`（常量 + `digest` 一行过滤）、`notes/promote.py`（import 替换）。
  **无新增依赖、无配置键、无跨域依赖**。
- **风险**：低。命中面排除**只**影响 `digest`（注入面）；`consult/search/list` 不变 ⇒ CLI 检索面不变；
  非提升笔记路径**零扰动**；loop/memory 未触碰 ⇒ 会话连续性（长期摘要块）结构性保持。
- **已知局限**（详见 `design.md` / `coding-plan/known-risk.md`）：显式提升的常驻全文与同类会话的长期摘要块
  在**本会话内**仍并存（跨会话语义所需，规格明文授权）；提升产物仍以标题占 `_MAX_DIGEST_CHARS` 预算；
  判据依赖 canonical 内 `- source:` 行（人工删行即失效）。

## Non-goals

- ② `key_fact` 抽取 vs 笔记结论（同一功能按 `_has_write_effect` 分家）—— 另账。
- ③ `notes.observe_turn` 写回 vs `loop.<trace>` / `loop.steps.<trace>` 沉淀 —— 另账。
- `NoteStore` 与 `MemoryStore` 两店合一 —— 结构性账，另议。
- 显式提升路径的正文去重（见局限①）。
