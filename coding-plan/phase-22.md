# Phase 22 — 12 模块系统级审查缺陷修复（observability 生命周期 / rag 死代码 / skillhub 供给侧死代码）

> **定位**：对已落地交付的 12 个核心模块（mcp / rag / llm loop / orchestration / plugins / plugin registry / memory / skills / skillhub / observability / evolution / ui）做系统级功能完善性审查（**非**依赖单测门禁——单测全绿也可能存在「装配断裂 / 静态绑定 / 死代码」这类测不到的系统级漏洞）。本 Phase 收录**新发现、且 phase-20 / phase-21 均未覆盖**的 3 项缺陷，交 claude code 继续修复。
>
> **审查结论总览**：memory / skills 生产触达广泛且健康；orchestration 闭环成立（scheduler 波次内 asyncio 并发 + `router.handoff` 真 `await` 等 subagent 结果）；mcp / plugins / plugin registry / llm loop 基本可用（mcp-http 的 `build_http_transport` 抛「待接入」属 **phase-20 B2 已列**，不重复）。**真问题落在 3 处**：observability tracer 生命周期断裂 + 内存泄漏（P0）、rag 主链路死代码（P1）、skillhub 供给侧三件套死代码（P1）。
>
> **去重口径（本节必须遵守）**：下列项**已在他 Phase 覆盖，本 Phase 不写**——
> - `phase-20` 已列待办：**E27**（im 网关装配 + 宿主入口）、**B2**（mcp-http `build_http_transport` 适配器）、**C7**（ui TTS 抽象）、**C8**（ui Tauri sidecar 打包验证）。
> - `phase-20` C4 observability 已做「组合根装配 exporter」，**但未接 tracer 生命周期**（start/end/清理）——本 Phase 的 P0 恰是补这个**装配之外的**生命周期断裂，不与 C4 重复。
> - `phase-20` C5 skillhub 只关**消费侧** `SkillHubClient`（search/install，`entry.py` 已接）；本 Phase 的 P1 是**供给侧** `SkillPublisher`/`MarketIndex`/`TrustVerifier` 死代码，不与 C5 重复。
> - `phase-21` 已关 evolution plugin 维度**归因接线**（trace 通路 + `TraceEvent.module_id` + `Proposer` 动态 kind）——本 Phase 不碰 evolution 归因语义。

---

## 1. 范围与定位

- **分层图位置**：L3（运行时装配 / runtime capability）与各 capability 模块的**生产接线面**，重点盯「契约声明了、代码写好了、但组合根/CLI 没接」的断层。
- **覆盖 capability**：`contracts_summary.md` §observability（trace 采集/落盘）、§rag（检索增强生成）、§skillhub（技能发布/市场）。

### 1.1 范围（3 个缺陷）

| # | 缺陷 | 严重度 | 现象（一手核实，含行号） |
|---|---|---|---|
| **1** | **observability tracer 生命周期断裂 + 内存泄漏** | **P0** | `start_trace`/`end_trace` 全仓**零生产调用**（grep 仅命中 docstring）；loop 用 `trace_id=uuid.uuid4().hex` 自造绕过 `start_trace`（`loop/default.py:210`）；`record` 用 `setdefault(trace_id, []).append()` 累积（`tracer.py:49-52`）；`end_trace(emit)` 只 emit **不 `pop`/`del`**（`tracer.py:39-42`）→ `_events` 永久增长。因 `end_trace` 零调用 ⇒ `JSONLExporter`/`BufferedExporter` **永不 emit**（traces.jsonl 落盘死路径）。 |
| **2** | **rag 主链路死代码** | **P1** | 仅 `LLMEmbedder` 存活（`runtime.py:84/272` 供 memory embedding 用）。`RagGenerator` / `Retriever` / `IngestionPipeline` / `InMemoryVectorStore` / `Chunk` / `SearchHit` / `Document` **零生产调用、无 CLI 入口**——RAG 的「摄取→向量化→检索→生成」主链路整条未接。 |
| **3** | **skillhub 供给侧三件套死代码** | **P1** | `SkillPublisher`（publisher.py）/ `MarketIndex`（index.py）/ `TrustVerifier`（trust.py）**零生产调用**；仅消费侧 `SkillHubClient` 存活（`entry.py:77/766/771/785` 的 search/install）。「发布→索引→信任验证」供给侧整条未接。 |

### 1.2 明确不做

- **不碰 phase-20 已列项**：E27 / B2 / C7 / C8（见上文去重口径）。
- **不碰 phase-21 已关项**：evolution plugin 归因接线（trace 通路、module_id、动态 kind、结晶语义）。
- **不改 memory / skills / orchestration / mcp(stdio) / plugins / plugin registry**：审查确认生产触达健康，无系统级缺陷。
- **不引入新的架构能力**：本 Phase 只做「接线 / 清死代码 / 诚实声明」，不新增特性。

---

## 2. 缺陷 1 — observability tracer 生命周期断裂 + 内存泄漏（P0）

### 2.1 现象与根因

- **根因链**：`Loop` 的 trace 生命周期**绕过了 tracer 的 `start_trace`/`end_trace` 语义**——
  1. `loop/default.py:210` 用 `trace_id = uuid.uuid4().hex` **自造 id**，从不调 `tracer.start_trace()`；
  2. 事件经 `_trace`（`loop/default.py:482`）→ `tracer.record`（`loop/default.py:492`）写入 `_events[trace_id]`；
  3. 但**没有任何代码调用 `end_trace(trace_id)`**（全仓零调用）⇒ `JSONLExporter.emit` 只在 `end_trace` 内部触发（`tracer.py:39-42`），永不执行 ⇒ **traces.jsonl 是死路径**；
  4. 且 `end_trace` 即便被调用，也**不清理 `_events[trace_id]`**（不 `pop`/`del`）⇒ 事件累积内存泄漏。
- **为什么单测全绿测不到**：单测直接构造 `tracer.record(...)` + 手动 `end_trace(...)` 断言 exporter 收到事件，**从未走 `Loop` 的真实生命周期**；「零生产调用」与「泄漏」都不在断言范围内。

### 2.2 修复方向

- **模块**：`src/core/observability/tracer.py` + `src/core/loop/default.py` + `src/core/evolution/worker.py`（+ 组合根 `runtime.py` 若 tracer 经其注入）。
- **⚠ 前置约束（不可违反，否则静默回退 change 0101/0102）**：`EvolutionWorker.on_trace_complete(trace_id)` **只登记 id**（`worker.py`），真正的 `Tracer.replay(trace_id)` 在**下一次冷路径** `maybe_run → _collect()`（`worker.py:85`）才发生 —— **延迟读取**。loop 收尾顺序为 `_maintain`（消费上一批）→ `loop_finished` 事件 → `_notify_trace_complete`（登记本轮，供**后续轮** replay），故本轮事件**必须存活到后续某一轮**。因此 **不得**在收尾处对 `_events[trace_id]` 直接 `pop` 而不同步快照，否则 `replay` 返回 `[]`、诊断退回 `no_evidence`、0101/0102 静默失效。
- **改动（最小闭环）**：
  1. `loop` 启动处调用 `tracer.start_trace(name)` 取回 `trace_id`（替换 `loop/default.py:210` 的自造 uuid）。
  2. **登记改快照**：`on_trace_complete` 由「追加 `trace_id`」改为「追加 `self._tracer.replay(trace_id)` 的**事件快照**」（`_completed: list[list[TraceEvent]]`），`_collect` 遍历快照。
  3. 收尾处**按序**：先 `_notify_trace_complete(trace_id)`（取快照）→ 再 `tracer.end_trace(trace_id)`（封口）。
  4. `end_trace(trace_id)` 内：`events = self._events.pop(trace_id, [])`（**取出即删**，杜绝泄漏）→ 非空则 `exporter.emit(events)`（**无需单独 flush**：协议面只有 `emit`，`BufferedExporter.emit` 内部即 flush）。快照已在步骤 2 取得，故此处 `pop` 安全。
  5. `record` 的 `setdefault().append()` 可保留，与 `end_trace` 的 `pop` 对称。
- **留存取舍（实现前二选一，须在 `tasks.md` 写明并对应验收）**：
  - **(A) 回调取快照（推荐）**：`on_trace_complete` 登记事件副本。热路径仍**不阻塞**（`replay` 仅内存排序），代价是 `_completed` 驻留**事件列表**而非 id —— 冷路径间隔（缺省 900s）内每轮多驻留一批列表；间隔越大、单轮事件越多，峰值占用越高。
  - **(B) 显式回收口（更省内存）**：仍登记 id，`end_trace` 只 emit 不 `pop`，由 `EvolutionWorker._collect()` 读完某 trace 后调新增的 `Tracer.discard(trace_id)`（`Tracer` 多一个显式回收口 → 冷路径消费即释放，且「谁读谁负责回收」语义更紧）—— 代价是**有界性依赖调用方纪律**（若消费者忘记 `discard`，泄漏复原）。
  - **共同禁令**：无论 (A)/(B)，都**不得**只在收尾处 `pop` 而不同步留存 —— 那正是会回退 0101/0102 的错误方案。若消费者不是 `EvolutionWorker`（未来接其他 trace 消费者），(B) 的回收责任须随之移交。
- **验收**：
  - 一条集成测试：驱动 `Loop` 跑一个含 tool/effect 事件的回合 → 断言 **该 `trace_id` 在该轮收尾后已不在 `_events`**（逐 id 断言，**不用全局 `len(_events) == 0`**——多会话下有在途 trace）且 exporter 收到了本轮事件（trace 落盘真路径打通）。
  - **回归守护**：断言 `on_trace_complete` 取到的**事件快照非空**，且进化冷路径仍能产出归因证据（**不得因 `pop` 破坏 0101/0102**）。
  - 跑 N 轮（N≥10）→ 断言 `_events` 不随轮次增长（**无内存泄漏**）。
  - `start_trace`/`end_trace` 在生产代码中的调用方**不再为 0**（grep 可证）。

**落地状态**：**已闭**（change `0103` / ADR-0096，2026-10-05）。按 **(A) 回调取快照** 实施：`Tracer` 只保**在途**链路（`end_trace` = `emit` + `pop`），已完成留存归**消费者**（`EvolutionWorker._completed: list[list[TraceEvent]]`，回调时刻取 `replay` 快照、`_collect` 遍历快照）；`replay` 口径随之收窄为「在途」，**已完成任务回溯以落盘遥测（JSONL）为真源**（不留双真源，同 E19 裁决）；loop 收尾顺序（记录本轮遥测 → trace 完成回调 → `end_trace` 封口）写进 **loop 规格**并加**回归守护**用例（`test_loop_seals_after_trace_observer_snapshot`）；`EvolutionTrigger` 批语义**不动**，仅加**有界断言**（`test_completed_batch_window_is_bounded`）。步骤 4 原「→ flush」措辞已订正（`Exporter` 协议无 `flush`）。

---

## 3. 缺陷 2 — rag 主链路死代码（P1）

### 3.1 现象与根因

- `rag` 模块除 `LLMEmbedder`（供 memory 语义 embedding，`runtime.py:84/272`）外，**主链路 7 个类全部零生产调用、零 CLI 入口**：`RagGenerator` / `Retriever` / `IngestionPipeline` / `InMemoryVectorStore` / `Chunk` / `SearchHit` / `Document`。
- **根因**：契约声明了 RAG 能力（检索增强生成），代码骨架也写好了，但**组合根 `runtime.py` 未装配、`entry.py` 无 rag 命令**——摄取（ingest）与检索（retrieve/generate）两端都没有生产入口，是「写了没接」的断层。

### 3.2 修复方向（二选一，推荐 a）

- **(a) 接线（推荐）**：补 CLI 入口（如 `rag ingest <path>` / `rag search <query>`）+ `runtime.py` 装配，把 `IngestionPipeline → InMemoryVectorStore → Retriever → RagGenerator` 串成可用的检索增强链路；文档/契约同步声明入口。
  - **理由**：memory 已在用 `LLMEmbedder`（基础设施在场），RAG 是契约声明的能力，且对「长期记忆之外的知识检索」有真实价值。
- **(b) 诚实降级（⚠ 前置：须先改规格）**：rag 主链路（「本地向量库存储 / 文档摄取与分块 / 本地 Embedding / 检索」）**本就是 `doc/openspec/specs/rag/spec.md` 的明文 Requirement**，故 (b) 属**撤回已承诺能力**，按 SDD「先改规格再改代码」**必须先出 spec delta（MODIFIED 相关 Requirement）**，再移除死代码（仅保留 `LLMEmbedder`），最后同步 `contracts_summary.md`（速查表，非真源）。**删除面含** `src/core/rag/__init__.py` 的 `__all__`（`Chunk`/`Document`/`SearchHit`/`InMemoryVectorStore`/`IngestionPipeline`/`RagGenerator`/`Retriever`）**与** `tests/test_rag.py` 的对应用例——不得只删源码。
  - **口径澄清**：原「若契约确不要求」的假设**不成立**（一手核实：契约要求）⇒ 实际是「a，或者先改规格撤回」。
- **验收（以 a 为准）**：一条端到端测试：ingest 若干文档 → search 命中相关 chunk → generate 返回带来源的答案；CLI 命令可运行；`ruff`/`pyright`/`pytest` 全绿。

**落地状态**：**已闭**（change `0104` / ADR-0097，2026-10-05；用户裁决 **(a) 接线**）。实施中相对原方案的三处**必须偏离**（均因一手核实推翻原假设）：
1. **落盘存储不是 `InMemoryVectorStore`**：原方案「串 `IngestionPipeline → InMemoryVectorStore → …`」跨进程即丢 —— 而 CLI 每次调用都是**新进程**（`rag ingest` 与 `rag search` 是两次进程调用）。改用 **stdlib `sqlite3`**（`SqliteVectorStore`，`$CORE_STATE_DIR/rag-index.db`）：零三方依赖（`sqlite-vec` 离线不可得、JSON 全量重写退化），行级写入天然支持增量重建。
2. **索引记维度、不一致即拒绝**：`_cosine_similarity` 用 `zip(..., strict=False)` ⇒ 换 embedding 后端后沿用旧索引会**静默按短边截断**算出无意义相似度（可达路径：先离线 ingest 后配 `llm.embedding_model`）⇒ 首个 `put` 定档维度，此后不符抛 `INDEX_CORRUPT` 并提示重建索引。
3. **文档指纹须落盘**：原 `IngestionPipeline._hashes` 是**进程内 dict** ⇒ 新进程里 `refresh` 永远判「有变更」（增量判定形同不存在）⇒ 抽象补 `record_document` / `document_hash`（落 `documents` 表），`ingest` 合并为 upsert（返回写入块数，无变更 ⇒ 0），`refresh` 退化为布尔外壳。

**另订正两处失真**（原方案未列，一手核实发现）：① 规格与 `02-modules/rag.md` 称「与既有 SQLite 生态统一」——全仓 `src/` 无 sqlite 使用，前提为假；② 规格「默认实现 sentence-transformers + BGE」「默认 sqlite-vec」**均未落地** ⇒ 本 change 同步 MODIFIED rag 三条 Requirement（本地向量库存储 / 本地 Embedding / 存储与 Embedding 依赖注入隔离）与 cli-ops「运维命令集」，并订正 `00-product/requirements.md`（CORE-RAG-R1/R3）、`11-rag/rag-architecture.md`、`04-testing/test-cases.md`（TC-RAG-01/04/10）、`doc/README.md`。**「未配 LLM 的 `rag ask` 报错」在装配链上不可达**（`llm.*` 四项为必需配置 ⇒ 空配置必然 `ConfigurationError`）⇒ 该 fail-closed 面由**服务层**承载（新错误码 `GENERATION_UNAVAILABLE`），CLI 只做「结构化错误 → stderr + 退出码 1」的统一收口。

**入口**：CLI `rag ingest <path> --doc-id ID` / `rag search <query> [--top-k N]` / `rag ask <query> [--top-k N]`；组合根装配挂 `runtime.rag`（`RagService` 门面）。embedding 语义优先（配 `llm.embedding_model` ⇒ `LLMEmbedder`，与 memory 通路共用 `embed_provider`）、未配则离线 `HashEmbedder` 降级 + CLI 提示。

**验收证据**：`tests/test_rag_wiring.py`（组合根装配 / 端到端 ingest→search→ask 不出网 / CLI 三子命令 / 结构化错误面）；`tests/test_rag.py` 追加落盘库与门面用例；真机 CLI 冒烟（两进程 ingest→search→再 ingest 判无变更，索引落盘）。四门：`ruff check` / `ruff format --check` / `pyright 0-0-0` / `pytest` **1201 passed**。

---

## 4. 缺陷 3 — skillhub 供给侧三件套死代码（P1）

### 4.1 现象与根因

- `skillhub` 供给侧三件套 **`SkillPublisher`（publisher.py）/ `MarketIndex`（index.py）/ `TrustVerifier`（trust.py）零生产调用**；仅消费侧 `SkillHubClient`（search/install，`entry.py:77/766/771/785`）存活。
- **根因**：phase-20 C5 只把「从市场**拉取/安装**技能」的消费侧接上了，**「发布/索引/信任验证」供给侧从未接**——技能只能进不能出，市场只有消费没有供给。

### 4.2 修复方向（二选一，推荐 a）

- **(a) 接线（推荐）**：补 CLI 入口（如 `skillhub publish <skill>`）接通 `SkillPublisher`（打包/发布）+ `MarketIndex`（索引上架）+ `TrustVerifier`（签名/信任验证），使「本地技能 → 发布 → 索引 → 可被消费侧 search/install」闭环；契约同步声明入口。
- **(b) 诚实降级（⚠ 前置：须先改规格）**：供给侧（`SkillPublisher` 发布 / `MarketIndex` 索引 / `TrustVerifier` 信任）是 `doc/openspec/specs/skillhub/spec.md` 的明文覆盖（Purpose 含「**发布审核流**」，场景点名 `MarketIndex.list` / `MarketIndex 健康探测` / `TrustVerifier`）⇒ (b) 属**撤回已承诺能力**，**必须先出 spec delta（MODIFIED）**，再移除死代码（publisher/index/trust），最后同步 `contracts_summary.md`。**删除面含** `src/core/skillhub/__init__.py` 的 `__all__`（`MarketIndex`/`SkillPublisher`/`TrustVerifier`）**与** `tests/test_skillhub.py` / `tests/test_skillhub_cli.py` 的对应用例。
- **验收（以 a 为准）**：一条端到端测试：publish 一个本地技能 → 断言 `MarketIndex` 可检索到 → 消费侧 `search` 能命中 → `install` 成功；CLI 可运行；三件套门禁全绿。

**落地状态**：**已闭**（change `0105` / ADR-0098，2026-10-05；用户裁决 **(a) 接线**）。实施中相对原方案的两处**必须偏离**（均因一手核实推翻原假设）：

1. **只补 CLI 入口不成立 ⇒ 两处进程内状态须落盘**：CLI 每次调用都是**新进程**，而供给侧状态两处都在进程内 —— `MarketIndex._sources`（内存 dict）与 `SkillPublisher._published`（`skill_id → source` 内存 dict）⇒ 上个进程 `publish` 的条目下个进程 `search` 看不到、下个进程 `review` 判「未发布」，链路「看似闭环、实则每步空转」。改法：`MarketIndex(path=…)` 目录落盘（`put()` 为唯一写路径）+ **删 `_published`**（「发布到哪个源」已写在目录里，第二真源跨进程必失效）⇒ `review` 经 `locate(skill_id)` 定位并回写。
2. **发布 ≠ 只上架元数据**：目录按规格只存元数据（「不拉取完整技能体」），而消费侧 `download` 需要 fetcher 给技能体 ⇒ `publish` 同时把**技能体副本**（`replace(skill)`）入本地市场制品库，缺省 `fetcher` 指向该库（离线、零凭据）。顺序：先 `index.put`（源不存在即 `SOURCE_NOT_FOUND`，不留半份制品）再 `artifacts.register`；`review approved` 时制品本体同步提升到市场版本并**重新签名**（否则市场签名与制品内容不一致，末端验签失败）。

**已否决**（明示不做）：① **install 仅限 `published` 的消费闸门** —— 本 Phase §4.2 验收序列 publish → search → install **中间无审核**，加闸门是新增契约而非「接线」；② `skill market list` 子命令（`MarketIndex.list` 已在 `SkillHubClient.search` 生产路径上）；③ 新错误码（既有四个已足）；④ **远端市场 fetcher**（网络 + 凭据，仍为凭证半）。

**入口**：CLI `skill publish <skill_id> [--source S]`（本地技能未注册 ⇒ stderr + 退出码 1）与 `skill review <skill_id> <approved|rejected>`（驳回亦退出码 1 且状态落盘 rejected）；三件套经 `entry._build_market_index()` / `_build_market_artifacts()` / `_build_publisher()` 同源装配，落盘于 `$CORE_STATE_DIR/skillhub-{index,artifacts}.json`，版本提升落 `skill-versions.json`（与组合根同源）。

**验收证据**：`tests/test_skillhub_cli.py::test_supply_chain_publish_search_review_install`（全程走 CLI、每步重开落盘对象断言跨进程可见）+ 反例三组（未注册技能 / 源不存在 / 未发布技能 / rejected）；`tests/test_skillhub.py` 8 例（目录落盘 / 损坏降级 / `locate` / 制品入库 / 跨实例审核 / 重签名 / 驳回落盘）。真机四进程冒烟：`skill publish` → `skill search` → `skill review approved` → `skill install` 全 rc=0，市场 `published v2`、本地 `draft`。四门：`ruff check` / `ruff format --check` / `pyright 0-0-0` / `pytest` **1215 passed**。

---

## 5. 契约对齐

引用 `contracts_summary.md`（速查表原文）：
- **observability**：trace 采集 + 落盘（JSONL 持久化）。本 Phase 的 P0 修复确保「**采集到的事件真能落盘**」（当前 `end_trace` 零调用 ⇒ 落盘死路径，契约未兑现）。
- **rag**：检索增强生成（摄取→向量化→检索→生成）。原仅 `LLMEmbedder` 存活、主链路契约**未兑现** ⇒ 已按 (a) 接线补齐（change `0104`）。
- **skillhub**：技能发布 / 市场检索 / 安装。原仅消费侧（检索/安装）兑现、供给侧（发布/索引/信任）**未兑现** ⇒ 已按 (a) 接线补齐（change `0105`）。

> **口径**：凡选择 (b) 诚实降级者，**先改规格**（`doc/openspec/specs/rag/spec.md` / `doc/openspec/specs/skillhub/spec.md` 出 MODIFIED delta 撤回对应能力）**→ 再删代码**（含各模块 `__init__.__all__` 与既有测试）**→ 最后同步 `contracts_summary.md`**（速查表非真源）。顺序为「规格 → 代码 → 速查表」，**不得只删代码或只改速查表**。

---

## 6. 门禁验收

- [x] `ruff check` 全绿。
- [x] `pyright` 0 errors。
- [x] `pytest` 全绿（新增用例覆盖 §2.2 / §3.2 / §4.2 各验收点）；**1215 passed**（change 0105 收口时点）。
- [x] **本 Phase 专属校验**：
  - P0：集成测试证明「exporter 收到本轮事件 + 多轮 `_events` **有界**（无泄漏）」（§2.2）；释放时机按 §2.2 选定方案断言 —— (A) 收尾后该 trace 已出 `_events`；(B) 冷路径 `_collect` 后该 trace 已 `discard`。
  - P1（若选 a）：rag 端到端 ingest→search→generate 可用（change `0104`）；skillhub publish→search→install 闭环可用（change `0105`，跨进程验证据 §4.2）。（§3.2 / §4.2）
  - 若任一项选 (b)：（**未触发** —— rag 与 skillhub 均裁决 (a) 接线，故本行不适用；留下作以后同类裁决的清单。）
