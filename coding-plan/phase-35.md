# Phase 35：记忆面彻底完善（批次 `0181`~`0189`，9 change）

> **状态**：✅ **全闭**（2026-10-10；9 条 change `0181`~`0189` 逐条独立收口：各自 change 目录 /
> ADR / 规格 delta（或规格中性）/ 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-10 用户追问「记忆模块彻底完善了吗」⇒ 主代理据台账 + 三份 `file:line` 探索报告
> 如实列出**尚存缺口**（built-but-unwired / 契约缺口 / 结构性缺口）⇒ 用户裁决
> **「要，一次解决上面的所有问题」**。
> **为什么是一批而非一条**：一条 change 跨 `memory` / `loop` / `context` / `llm_provider` /
> `configuration` / `evolution` / 架构测试 **七个子包**，违反 **P3**（进化局部化与可归因）、
> **P4**（验证门 + 不可变世代）与「一 change 一提交」红线 ⇒ 采 **Phase 34「全修」先例**
> （`coding-plan/phase-34.md`，20 change `0126`~`0145`）：**一个批次、多条 change**，
> 每条仍各自 change / ADR / delta / 单提交 / 四门禁。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`runtime.py:603`，
> phase-26）**逐字不动** —— 本批次只**加严**排除面、**从不放宽**；密钥只引用不读取、绝不进日志/记忆；
> 零三方依赖；`config*.yaml` / `.claude/settings*.json` / `uv.lock` 等**不提交**。

---

## §0 用户裁决的四个设计岔口（AskUserQuestion，2026-10-10）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | 记忆面 → 进化诊断面桥 | **纳入**（**注入式读取**桥，依赖倒置，不新增 import 方向）⇒ change `0188` |
| 2 | 压实触发的 `rounds` 实为工具步数（E96 另注） | **诚实化 + 配置注入** ⇒ change `0182` |
| 3 | `reuse_count` 仅进程内 | **落盘持久化** ⇒ change `0187` |
| 4 | E97 余项（known-model 窗口表 / `llm.provider` 死标签） | **全做（含内置窗口表）** ⇒ change `0184` |

---

## §1 批次总览（执行顺序 = 编号顺序）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0181-importance-scorer-wiring` | `memory` | 生产接线 `importance_scorer`（`score_with` 工厂 + 内部产物豁免面 + 配置开关，缺省关） | ADR-0172 | E118 | 2125 → 2146（+21） |
| 2 | `0182-compaction-trigger-config` | `context` | 压实触发**诚实化**（`rounds`＝工具步数）＋ `compact_steps` 配置注入（缺省 6 < 上限） | ADR-0173 | E119 | 2146 → 2163（+17） |
| 3 | `0183-streaming-token-usage` | `llm_provider` | 流式携带并消费端点 `usage` ＋ 请求侧 `max_tokens` / `completion_tokens` 落地 | ADR-0174 | E120 | 2163 → 2176（+13） |
| 4 | `0184-model-window-provider-label` | `configuration` | 内置 known-model `context_window` 表 ＋ `llm.provider` 审计标签接线（**去死标签**） | ADR-0175 | E121 | 2176 → 2185（+9） |
| 5 | `0185-compression-fact-face-exclusion` | `context` | 压缩产物（`compaction.summary/mid`）退出「相关事实」注入面（已由专块每轮注入） | ADR-0176 | E122 | 2185 → 2191（+6） |
| 6 | `0186-fact-face-tag-exclusion` | `context` | 「同源排除面」惯用法一般化：原始步序 `loop.steps.<trace>` 退出事实注入面 | ADR-0177 | E123 | 2191 → 2196（+5） |
| 7 | `0187-reuse-count-persistence` | `memory` | `reuse_count` **落盘**（命中写回 + 可撤销效应；接受写放大） | ADR-0178 | E124 | 2196 → 2200（+4） |
| 8 | `0188-memory-diagnosis-bridge` | `evolution` | 记忆面 → 诊断面桥：`Diagnoser` 经**注入 reader** 关联 L2 失败条目 | ADR-0179 | E125 | 2200 → 2206（+6） |
| 9 | `0189-three-face-boundary-guard` | （架构测试） | 三面边界**另一侧**门禁：`memory` / `notes` 不得兼做知识文档检索 | ADR-0148 附 | E126 | 2206 → 2208（+2） |

**批次合计**：测试基线 **2125 → 2208**（**+83**）；`openspec validate --all` **31 passed / 0 failed**；
四门禁（`ruff check` / `ruff format --check` / `pyright` **0-0-0** / `pytest -q`）**逐条全绿**。

---

## §2 账目（E118~E126，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E118** | `ImportanceScorer` 闸门齐备但生产**未接线**；且内部/派生产物**同样过闸门**（误杀风险） | `score_with(llm)` 工厂 + `_GATE_EXEMPT_SOURCES` 豁免面 + 配置键 `memory.importance_gate`（**缺省 false** ⇒ 行为逐字不变） | `0181` / ADR-0172 |
| **E119** | 压实触发的 `rounds` 实为**工具步数**（命名说谎）；`round_threshold`＝`max_rounds` ⇒ 该维度**永不触发**且无配置键 | 形参/文案诚实化为 `steps`；新配置键 `loop.compact_steps`（缺省 **6** < 上限 ⇒ 可真正触发）+ 独立访问器 | `0182` / ADR-0173 |
| **E120** | 流式（默认路径）**不携带 `usage`** ⇒ token 估算**从不被真实用量修正**；`max_tokens` 无人下发、`completion_tokens` 无人消费 | 流式请求带 `stream_options.include_usage`、末块解析 `usage` 并抬升 prompt 下界；`_build_request` 下发 `max_tokens`；`completion_tokens` 入观测面 | `0183` / ADR-0174 |
| **E121** | 无「模型 → 窗口」映射（未配置即恒 65536）；`LLMResponse.provider` **硬编码 `"stdlib"`**（死标签） | 内置 `model_windows.py` 子串匹配表（缺省仍回落 65536，逐字兼容）；`StdlibLLMProvider(provider=…)` 由配置注入真实标签 | `0184` / ADR-0175 |
| **E122** | 压缩产物正文经**两条通道**重复进场（专块 + 「相关事实」面） | 装配级排除面 `exclude_fact_sources`（缺省空 ⇒ 逐字不变），runtime 传 `("compaction.summary.","compaction.mid.")` | `0185` / ADR-0176 |
| **E123** | 声明角色为**抽取素材**的原始步序被当「相关事实」注入 prompt | 装配级 `exclude_fact_tags={"steps"}`（`read()` 召回语义不变 ⇒ 素材角色保留） | `0186` / ADR-0177 |
| **E124** | `read()` 命中只在本进程自增 `reuse_count`（**跨会话全丢**），且因 `FileBackend.search` 共享对象而**既有测试判据错位恒绿** | 只对本次选中的条目 `_backend.put` 写回 + `EffectTracker` 逐条可撤销（幂等还原前值） | `0187` / ADR-0178 |
| **E125** | 已沉淀的轮级失败摘要（`loop.failure.<trace>`）**没有任何读者** ⇒ 进化闭环起点看不到人类可读失败叙述 | `DiagnosisReport.failure_notes`（新**可选**字段，不改既有字段语义）+ `Diagnoser(failure_lookup=…)` 注入缝（**有界** 3×400 字、**fail-open**） | `0188` / ADR-0179 |
| **E126** | 三面边界只护 **rag 一侧**；`memory` / `notes` 越界「兼做知识文档检索」**无门禁**（边界全靠散文） | AST 走查两面**公开面**（名 ＋ 形参）语料词元 + 守护**链成员**断言；`src/` 零改动 | `0189` / ADR-0148 附 |

---

## §3 逐条收口（协议一致性）

每条**必走**：spec-first（或**规格中性**判定）→ ADR → 先红测试 → 实现 → 四门禁 → 手工归档
→ 台账 ＋ 记忆 → **单次提交**。**规格 delta** 落点：`0181`→`memory`、`0182`/`0185`/`0186`→`context`、
`0183`→`llm_provider`、`0184`→`configuration` ＋ `llm_provider`、`0187`→`memory`、`0188`→`evolution`；
`0189` **规格中性**（`.openspec.yaml` `skip_specs: true`，沿 change `0156` 先例 ⇒ 无 delta、无 canonical 合并）。

**归档方式**：`openspec archive` 在 symlink+WSL 下**必败** ⇒ 恒为**手工**（delta 合 canonical 时断言
**0 canonical 行丢失 / 0 Scenario 标题丢失**，再 `shutil.move` 进 `doc/openspec/changes/archive/`）。

**能力面 canonical 变化**（`doc/openspec/specs/`）：`memory` 接入重要度闸门豁免面 + 复用强化落盘；
`context` 压实触发口径 + 两条排除面；`llm_provider` 流式 usage + provider 标签真实性；
`configuration` 模型窗口推导；`evolution` 失败摘要桥。逐条 Scenario 计数见各自 change 的 delta 与
`doc/04-testing/test-cases.md` §94~§102。

---

## §4 遗留与显式不做

- **不在本批次范围**（用户已明示或本批次刻意划出）：
  - 主方向封存红线 `("beast.","pet")`：**不动**（只加严面）。
  - `key_fact`（结构化实体）vs `notes` 结论（散文）：**记为设计上非重复**（不同面），**不**引入跨模块匹配。
  - `NoteStore` 与 `MemoryStore` **两店合一**：结构性账，另议。
  - §1 其余开账 **E27**（IM 网关未接线）/ **E55** / **C7**（TTS）/ **E91** / **E97**（余 known-model
    窗口表之外的部分）/ **E100**（余运维动词）/ **E101**（hooks 实现）：**非记忆面**，**未闭**，
    仍登记于 `coding-plan/known-risk.md` §1。
- **本批次新增的已知局限**：逐条登记在 `coding-plan/known-risk.md` **§3**（按 ADR 归类：ADR-0172~0179、
  ADR-0148 附）—— 例如压缩产物排除面的**轴选择**、`failure_notes` **不进候选载荷**、语料门禁
  **不察间接路径 / 非公开面**、`vector` / `embed` **刻意**不入语料词表等。
- **记忆三面路线图 G1~G5**（`0154`/`0151`/`0153`/`0155`/`0156`）**此前已全闭**；本批次是其在
  **实现面 / 门禁面**的补齐，不改三面分工本身。

---

## §5 关联

- 前置：`coding-plan/phase-34.md`（全修，20 change `0126`~`0145`）· `coding-plan/known-risk.md`
  （§1 账目 E118~E126 已闭、§3 已知局限）。
- 逐条细节：`doc/openspec/changes/archive/2026-10-10-0181-*` … `…-0189-three-face-boundary-guard/`
  （各有 `proposal.md` / `tasks.md`（＋ `design.md` / `specs/`，`0189` 另有 `design.md`））；
  用例与红态证据：`doc/04-testing/test-cases.md` §94~§102。
- 测试锚点：`tests/test_memory.py` / `test_context_*` / `test_llm_provider*` / `test_configuration*` /
  `test_evolution_attribution.py` / `test_evolution_wiring.py` / `test_architecture.py`。
