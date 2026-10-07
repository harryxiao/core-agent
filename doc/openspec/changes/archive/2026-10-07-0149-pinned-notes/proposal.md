# 常驻笔记（pinned notes）· change 0149 · 账本 E93

## 为什么

审查外部参考件 `Agent-Memory-LongTask.md`（跨月级超长期研发任务记忆方案）后**取精华弃糟粕**，立账
`E93`/`E94`（`coding-plan/known-risk.md` §1）。`E93` 是**真实能力缺口**：参考件的核心机制之一是
「高保真硬约束报告**永久置顶** System Prompt 最前端、永不被压缩」。我们的 `notes`（canonical Markdown
真相层，change `0106` / ADR-0099）**恰是天然载体**，但 **Consult 只在 query 命中时注入正文**，未命中
仅进 ≤1200 字**标题清单** ⇒ 长任务中期的硬约束（「对外接口必须 HTTPS」「Python ≥3.9」）**不保证每轮
在场**。每轮**恒注入**的只有 L0 宪法（**全局、非任务级**）。

## 改什么

为 `notes` 增**「常驻（pinned）」语义**：被标记的 note **每轮无条件注入正文**（不受 query 命中限制），
作为**任务级硬约束锚**，注入为**独立块**、置于 system prompt **最前（紧随宪法规则）**。

- **标记面**：canonical 元数据 `- pinned: true` ＋ CLI `notes pin <note_id>` / `notes unpin <note_id>`。
- **注入面**：`NoteStore.pinned_digest()` → 组合根零参闭包 → `LoopContext.pinned_notes` →
  `LLMPlanner` 新增「常驻笔记」块。

## 规格

`notes` **ADDED Requirement「常驻（pinned）笔记（任务级硬约束锚）」**（纯新增，**不**重述既有
Requirement「Consult → Build → Update 循环纪律」的 5 条 Scenario）。该 Requirement 含**消歧条文**：
本条 SHALL NOT 改变既有「**不自动全量注入**」口径 —— 后者只约束 Consult 命中路径；常驻是**仅对显式标记
`pinned: true` 的笔记**开启的**独立通道**。

## 非目标（明确不做）

- **`E94`**（摘要 → canonical 提升**触发**）：change `0150` / ADR-0142，**依赖**本 change ⇒ 后置。
- **`E91` / `E92` / `M8` / `M2`**：已立账另议。
- **给 notes 写操作接 `EffectTracker`**：notes 是 canonical 文档层，**既有设计即不入可逆效应面**
  （change `0106` 取舍），pin/unpin 走同一条 `update()` 路径 ⇒ **一致**；记入 ADR 已知局限。
- **每篇上限 / 自动置顶启发式 / 面向模型的 pin 工具 / 配置面**：不做（YAGNI）。
- **参考件红线项照搬**（永久删除、单库无隔离、三方依赖 langchain/openai/chromadb/tiktoken/numpy）。

## 风险与红线

- **⚠️ 密钥红线**：常驻笔记正文**每轮进模型上下文** ⇒ **绝不**把密钥 / 凭据写进常驻笔记（对齐仓库红线
  「密钥只引用不读取、绝不进日志 / 记忆」）。此暴露面比 Consult **更宽**（无条件），故在本提案与 ADR
  双重告示。
- **token 有界（P5）**：`pinned_digest()` 总长受 `_MAX_PINNED_CHARS = 4000` 约束（≈1000 tokens ≈ 默认
  budget 65536 的 1.5%）。截断按 `note_id` 序位 ⇒ 超大首篇可能饿死后续（登记已知局限；`notes pin`
  在超界时 stderr 告警）。
- **不改既有渲染**：`pinned=False` 时 `- pinned` 行**省略** ⇒ 既有 canonical 文件字节逐字不变、全量
  既有测试零回归。

## 影响面

`src/core/notes/{models,store}.py`、`src/core/loop/{protocol,default,planner}.py`、`src/core/runtime.py`、
`src/core/entry.py`；测试 `tests/test_notes.py`、`tests/test_notes_loop.py`、`tests/test_session_isolation.py`、
`tests/test_entry.py`；文档 `doc/03-interfaces/{notes,loop}-interface.md`、`doc/02-modules/notes.md`、
`doc/04-testing/test-cases.md`、`doc/01-architecture/adr.md`（ADR-0141）、`coding-plan/known-risk.md`（E93 → 已修）。
