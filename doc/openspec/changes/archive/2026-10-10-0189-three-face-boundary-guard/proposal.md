# 三面边界**另一侧**门禁：memory / notes 不得兼做知识文档检索（ADR-0148 局限②③）

## Why

- **缺口（守护不对称）**：change `0156` / ADR-0148 把「`rag` 不注入主链路」固化为**可执行不变量**
  （`tests/test_architecture.py::test_rag_not_imported_by_reference_chain`：`loop` / `context` /
  `memory` / `notes` SHALL NOT `import core.rag`）。但那只护**rag 一侧** —— ADR-0148「已知局限」
  ②明示：「**定位另一侧无守护** —— `memory` / `notes` 是否越界『兼做知识文档检索』无自动门禁」；
  ③明示：「**门槛靠人守**」。
- **风险是真实的**：三面分工（ADR-0148 决策①：`rag` 知识文档语义检索 / `memory` 经验轨迹 + 关键
  事实 / `notes` 主题文档）目前**只由散文**钉住。任何一次「顺手给 `notes` 加个 `ingest_document`」
  或「给 `memory` 加个 `chunks` 形参」都能**无声**把三面合并成两面 —— 而这恰恰是记忆三面路线图
  （G1~G5）划界时要防的退化。
- **同时记录一条既成事实**：局限② 里「另一侧」的**会话维度**锚（`NoteStore` 公开面无 `session`
  形参）在 change `0148` 期已由 `tests/test_session_isolation.py::test_notes_api_has_no_session_dimension`
  钉住 ⇒ 本 change **不重复**断言它，只把**语料维度**这一侧补上门禁（见 design.md D2）。

## What Changes

- `tests/test_architecture.py`：
  - 抽出门禁常量 `_REFERENCE_CHAIN = frozenset({"loop","context","memory","notes"})`（既有 rag 守护
    由局部字面量改用该常量，**逐字不变**其断言）；新增 `_CORPUS_FREE_FACES = frozenset({"memory","notes"})`。
  - 新增守护 ①**链成员**：`_CORPUS_FREE_FACES ⊆ _REFERENCE_CHAIN` —— 防「摘掉一个面即让两侧守护
    同时失效」。
  - 新增守护 ②**语料维度**：`memory` / `notes` 的**公开面**（公开函数 / 方法 / 类名 + 其形参名）
    经 AST 走查（复用既有 `_parse`）后，**不得**含「外部文档语料」词元
    （`document(s)` / `doc(s)` / `chunk(s)` / `corpus` / `ingest` / `pdf` / `retrieve` / `rag`；
    `snake_case` / `camelCase` 均切分）；同时断言走查**非空**（防空过）。
- `doc/01-architecture/adr.md`：**ADR-0148 附记**（扩写其「已知局限」②③：② 收窄为「间接路径
  与共享工具转发」、③ 由「靠人守」改为「靠人守 + 本门禁的最小绊线」）＋ 变更追踪行补注。
- `doc/04-testing/test-cases.md`：新增 `## 102.` 三面越界门禁 TC 节。
- `coding-plan/known-risk.md`：§1 关 **E126** 行（ADR-0148 局限②③）+ §3 ADR-0148 行局限②③改注。

## 规格中性（`.openspec.yaml: schema: spec-driven + skip_specs: true`）

**不改任何行为、不加任何 SHALL**：本变更只**加门禁**（测试）与**改文档口径**（ADR 附记），
**零 `src/` 改动** ⇒ **无规格 delta**（沿 change `0156` 先例）。三面分工的**行为规格**若未来真要
变更（memory 加向量 / notes 加实体 / rag 参与 loop），仍按 ADR-0148 决策③：**先改 ADR，再开规格变更**。

## 明确不做

- **不改三面分工本身**（不剥夺 / 不扩增任何一面能力）：本 change 只把**边界**变成可执行断言。
- **不重复**既有两条守护：`test_rag_not_imported_by_reference_chain`（rag 侧）与
  `test_notes_api_has_no_session_dimension`（会话维度侧）**逐字不动**。
- **不做形式化隔离**（ADR-0148 局限① 的既有裁决）：间接路径（共享工具转发、动态 `importlib`）
  **刻意不察** —— 本次只把「另一侧的直接退化」也纳入门禁，不放宽任何既有面。
- **零 `src/` 改动、零三方依赖**（守护用 stdlib `ast` / `re`，沿 `test_architecture.py` 既有实现）。
