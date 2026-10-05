# 提案 — 新增 `notes` 能力：canonical Markdown 真相层 + Consult→Build→Update 循环（change 0106）

## 背景与缺陷

`coding-plan/phase-23.md` §1.1 一手核实的三个缺口：

1. **无「文档化真相层」（P1）**：记忆只有 RAG 扁平片段（`MemoryStore` + `FileBackend`，
   `MemoryEntry` = `id/layer/content/tags/...` 扁平条目），**没有「一个主题一个权威 Markdown 文件、
   覆盖式更新」的形态**。决策/研究/解决过程散落在 embedding 里，既不能人类直接读，也不能 diff 追溯。
2. **无 Consult→Build→Update 循环指令载体（P1）**：loop 主循环（`loop/default.py`）有 `_trace`/`_maintain`
   等生命周期，**没有「任务前先读相关笔记、任务后把新发现写回笔记」的纪律注入点**。缺它，笔记层建起来
   也不会被 Agent 自觉 Consult/Update。
3. **外部插件不可装载（P0 决策前置）**：`plugin_registry` 是进程内注册表，**无外部插件加载路径**；
   operator-memory 是 TS + npm 分发、适配外部 harness 的 MCP/CLI 协议，与本仓 Python 运行时 +
   进程内插件契约不兼容 ⇒ **不硬塞外部插件，改为第一方 capability**。

## 变更目标

新增第 30 个 capability `notes`（文档化记忆 / canonical Markdown 真相层）：

1. **`src/core/notes/`**（新建）：`NoteEntry` 数据模型 + canonical Markdown 渲染/解析（`models.py`）、
   `MarkdownBackend`（实现既有 `MemoryBackend` Protocol，覆盖式 `put` + 原子写 + 关键词 `search`）、
   `NoteStore`（Plugin，`consult/update/ensure/create/get/list`）、结构化错误码。
2. **循环纪律接线**：内置技能 `skills.notes.consult_build_update` + loop **任务前 Consult 钩子**
   （确定性读命中笔记 + 清单 → 注入推理上下文，**不自动全量注入**）+ **任务后 Update 钩子**
   （成功轮覆盖式写回 canonical 文件）。**loop 不 import `notes`**（架构红线），钩子由组合根注入。
3. **契约**：新增 `doc/openspec/specs/notes/spec.md` + `doc/03-interfaces/notes-interface.md` +
   `contracts_summary.md` 追加行 + ADR-0099。

## 非目标 / 已否决

- **不安装 / 不包装 operator-memory 本体**（TS 运行时、外部 harness 协议均不引入；不做进程桥接）。
- **不改现有 RAG 语义**：`MemoryStore` / `FileBackend` / `LLMEmbedder` 照旧；`notes` 与之**并列**。
- **不向 notes 层引入 RAG / embedding / 向量库**：走 Markdown 文件 + 关键词匹配。
- **不改 `plugin_registry`**：不引入外部插件装载路径（那是另一个更大议题）。
- **不做多分区（user/private/shared）+ 权威层级**：MVP 为**单一 canonical 目录**（单 Agent 单工作区）；
  多分区列为后续扩展点（对齐 phase-23 §0.3 映射）。
- **不碰 phase-20/21/22 已列项**。
- **`workflow.py` 不入 `notes/`**：内置循环技能的 `Skill` 构造放在**组合根**（`runtime.py`）——
  `notes` 是 L2 文档化真相层，**不得向上依赖 L3 `skills`**；技能装配与注入属 L3 装配职责。

## 风险

| 风险 | 缓解 |
|---|---|
| 每次成功轮都写回笔记 ⇒ 噪音 / 覆盖掉旧结论 | 覆盖式是**有意语义**（最新最权威，对齐 §0.3 Failure Visible）；`observe_turn` 仅在 `ok=True` 且能派生主题时写 |
| 主题派生（slug）对中文任务失配 | slug 保留 `str.isalnum()` 字符（含 CJK），仅把空白/标点折为 `-` |
| 钩子写盘失败污染 loop 结局 | Consult / Update 钩子**各自失败降级**（`_trace` 留痕，不改本轮结果），与 `_notify_turn` 同口径 |
