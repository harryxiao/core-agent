# Phase 40：六能力走查缺口收口（批次 `0206`~`0214`，9 change）

> **状态**：✅ **全闭**（2026-10-11；9 条 change 逐条独立收口：各自 change 目录 / ADR / 规格 delta /
> 四门禁 / 手工归档 / 单次提交）。
> **来源**：2026-10-11 用户要求对**六能力**（长任务 / 动态压缩 / 文档总结 / SOP 技能进化 / 情景化
> 成功失败归档 / 退出重启恢复动态记忆）**全面走查**。四路 Explore 取证 ＋ 手核结论：四件**已具备并
> 缺省开**；一件**半具备**（文档总结缺「原始文档→摘要」入口）；SOP 进化**上半场通、技能→插件结晶
> 被 freeze 卡死**；另有一处**硬伤**（`memory.jsonl` 半写崩溃 ⇒ 客户端起不来）与一批「有规格无接线」
> 的**死代码**（Retention / 容错件 / InfoMap / `session_chain` 读侧）＋ **恢复扫描入口不全** ＋
> **主 loop 无检查点**。⇒ 用户裁决**全部缺口进本批**。
> **为什么是一批而非一条**：九个缺口分属**七个 capability**（`memory`／`durability`／`constraints`／
> `context`＋`rag`／`evolution`／`rag`＋`notes`／`durability`＋`loop`），实现面、规格面、消费面彼此
> **隔离**（唯二重叠：`durability` 三条、`rag` 两条 —— 但落在**不同 Requirement** 上）⇒ 沿
> **Phase 34~39 先例**：**一个批次、多条 change**，每条仍各自 change / ADR / delta / 四门禁 / 单提交。
> **执行顺序 = 编号顺序**（风险大体递增：`0206` 是健壮性修复、`0214` 触主 loop 热路径边界）。
>
> **红线（全批次）**：主方向封存 `exclude_source_prefixes=("beast.","pet")`（`src/core/runtime.py`
> **逐字不动**，phase-26）；密钥经 `CoeffectResolver` 注入、**只引用不读取**、**绝不**进日志/记忆
> （留痕**只报条目 id / 会话键 / 组键 / 计数**，**绝不回显正文或取值**）；所有写效应经
> `EffectTracker` 可回滚；**新行为缺省关 ⇒ 既有路径逐字不变**（**唯一例外 `0206`** —— 健壮性修复，
> 且是缺陷修复非新行为，ADR-0196 明写理由）；**宠物 loop 不接**容错链/轮级检查点，**子/神兽 loop
> 不接** transcript / turn_checkpoint；零三方依赖；`config*.yaml` / `.claude/settings*.json` /
> `uv.lock` **不提交**；四门禁**直连二进制**（`.venv/bin/ruff check` ／
> `.venv/bin/ruff format --check` ／ `/home/harry/.praisonai/venv/bin/pyright` **0-0-0** ／
> `.venv/bin/pytest -q`）。

---

## §0 用户裁决的四个设计岔口（AskUserQuestion，2026-10-11）

| # | 岔口 | 裁决 |
|---|---|---|
| 1 | **小修范围** | **全选** —— ① `memory.jsonl` 原子化 ＋ ⑤a 恢复扫描全覆盖 ＋ ④a 低风险三件 ＋ ④b 容错件 |
| 2 | **能力级范围** | **全选** —— ② 结晶通路 ＋ ③ 文档→摘要 ＋ ⑤b 主 loop 轮级检查点 |
| 3 | **② 的补法** | **注册面 ＋ 真 runner**（未注册仍 `freeze`，**fail-closed 保持**） |
| 4 | **③ 的落点** | **notes 结论层**（rag 保持**纯检索**，守三面边界 ADR-0148） |

> **一处计划期修正（`0209`，用户已知悉）**：④b 字面是「Retry/Fallback/Rollback/Pipeline 进工具链」，
> 但对抗验证发现 **Fallback 降级回复若进生产会**：(a) 静默抑制 `default.py` 的 **trace 回滚**
> （该回滚以 `result.failed` 为触发）；(b) **终结 loop、杀死 ReAct 自愈**（注释明写工具失败不判轮失败）；
> 且 `Pipeline`/`Fallback` 是**异常形状**、`act()` 是**结果形状**，硬接需人为翻译。⇒ `0209` 终形 =
> **Retry 进生产**（白名单 ＋ 仅可逆工具 ＋ 耗尽**原样返回失败**）＋ **Fallback/Pipeline 首次单测**
> （走出零测试状态）＋ **Rollback 维持 loop 级既有路径**（ADR 记边界）。**降级回复不上线**（见 §4）。

---

## §1 批次总览（执行顺序 = 编号顺序）

| # | change（归档目录） | capability | 一句话 | ADR | 台账 | 测试基线 |
|---|---|---|---|---|---|---|
| 1 | `0206-memory-backend-durability` | `memory` | `FileBackend` 原子写（tmp＋`os.replace`）＋ `_load` 逐行容错 —— 修「半写崩溃 ⇒ 起不来」硬伤（**唯一缺省开**） | ADR-0196 | E143 | 2327 → 2332（+5） |
| 2 | `0207-recovery-scan-coverage` | `durability` | 恢复扫描入口全覆盖：`repl`/`run`/`app`/`mcp serve` 启动**也扫也呈现**（一旗即成） | ADR-0197 | E144 | 2332 → 2338（+6） |
| 3 | `0208-retention-wiring` | `durability` | `RetentionManager` 接线（`max_count`/`time_window_s`，**缺省关**，pinned 保护） | ADR-0198 | E145 | 2338 → 2351（+13） |
| 4 | `0209-fault-wiring` | `constraints` | Retry 进生产（白名单 `{TIMEOUT,EXECUTION_FAILED}`＋仅可逆＋耗尽**原样返回**）；Fallback/Pipeline **首次单测** | ADR-0199 | E146 | 2351 → 2371（+20） |
| 5 | `0210-rag-info-map` | `context`＋`rag` | rag 库文档 build 期进 InfoMap（`index()`，**文档数上限 16**，缺省关） | ADR-0200 | E147 | 2371 → 2378（+7） |
| 6 | `0211-session-chain-diag` | `memory` | `session_chain` 读侧进 diagnostics 面（`render_chain` ＋ TUI `/chain`，**零效应**） | ADR-0201 | E148 | 2378 → 2385（+7） |
| 7 | `0212-evolution-crystallize-path` | `evolution` | 结晶通路：`evolve benchmark register/list/set-baseline` CLI ＋ **真 runner**（general 子 profile、OPT_IN 门控） | ADR-0202 | E149 | 2385 → 2395（+10） |
| 8 | `0213-rag-doc-summary-notes` | `rag`＋`notes` | `rag ingest --summarize`：摄取即摘要 → `notes.rag` 结论笔记（幂等、**双守护免费获得**） | ADR-0203 | E150 | 2395 → 2403（+8） |
| 9 | `0214-loop-turn-checkpoint` | `durability`＋`loop` | 主 loop 轮级检查点（`turn.<trace_id>`、轮首 `False`/轮末 `True`、**独立呈现不给续跑**） | ADR-0204 | E151 | 2403 → 2421（+18） |

**批次合计**：测试基线 **2327 → 2421**（**+94**，与九条预估一致）；
`openspec validate --all` **32 passed / 0 failed**（含 change）→ 归档后 **31 passed / 0 failed**（specs）；
四门禁（`ruff check` / `ruff format --check` / `pyright` **0-0-0** / `pytest -q` **2421 passed**）**逐条全绿**。

**共同形态**：九条里**七条是「有规格/有库能力、无生产接线」的接线类**（`0207`~`0212`），**两条是
能力级新增**（`0213` 文档→摘要、`0214` 轮级检查点），**一条是健壮性缺陷修复**（`0206`）。
接线类的共同纪律：**缺省关 ⇒ 既有路径逐字不变**（`0206` 是唯一例外）；能力级新增同样缺省关
（`0213` 则以**显式每命令旗**作 opt-in —— 是「显式参数」非「隐藏缺省行为」）。

---

## §2 账目（E143~E151，逐条根因 → 修法）

| 台账 | 根因（一句话） | 修法（一句话） | 归档 |
|---|---|---|---|
| **E143** | **`memory.jsonl` 半写崩溃 ⇒ 下次启动起不来**：`FileBackend._persist` 的 `write_text` **全量重写非原子**、`_load` 对 `json.loads` **无容错** ⇒ 全仓唯一「写非原子 ＋ 读不容错」双无防护面，却恰是**动态记忆主库** | `_persist` 改 **tmp ＋ `os.replace`**（镜像 `persistence.py`；JSONL 是拼接串、不复用 `write_state` 本体）；`_load` 逐行 `try/except` **跳坏行 + warn 只报坏行数**（对齐 `CheckpointStore` 口径）。**缺省开**（本批**唯一例外**：完好文件行为逐字不变、损坏文件从「启动崩溃」变「跳过坏行」⇒ **缺陷修复非新行为**） | `0206` / ADR-0196 |
| **E144** | **恢复扫描只接了 `serve` / `task` fresh 两个入口**（`0207` 前）⇒ `repl`/`run`/`app`/`mcp serve` 启动**不扫不呈现**，用户在日常入口**看不到**有未完成任务 | 三处 `_build_ui(..., surface_recovery=True)`（`_build_ui` **已有**该机制 ⇒ 一旗即成）＋ `mcp serve` 持真 Runtime ⇒ 直调 `_surface_incomplete`（**只打 stderr** —— stdio 的 stdout 是协议）。**仍不自动重执行**（守 P2） | `0207` / ADR-0197 |
| **E145** | **`RetentionManager` 三通道 ＋ `pin/unpin` API 齐备、规格已写，但生产零调用** ⇒ `checkpoints.jsonl` **无限增长**（`0214` 轮级检查点会放大） | 接线点 = `_write_checkpoint` **落盘之后**按已配置通道 `apply`。**只接两通道**（`max_count` / `time_window_s`）；`storage_quota` 有 `RETENTION_QUOTA_EXCEEDED` 启动风险 ⇒ **留库能力、不接热路径**；`strategy` 字段无消费者（不接、登记）。**两键皆缺省 ⇒ 零清理、逐字不变** | `0208` / ADR-0198 |
| **E146** | **`RetryPolicy`/`Fallback`/`Rollback`/`Pipeline` 生产零调用、`Fallback`/`Pipeline` 零测试**（规格已点名四件） | **Retry 进生产**（新 `loop/fault_adapter.py`，镜像 `constraints_adapter`；loop→constraints **合法**）：**显式白名单** `{TIMEOUT, EXECUTION_FAILED}`（未来错误码 **fail-closed 不重试**）＋ **仅可逆工具**（**惰性**从 `provider.active_tools()` 建集）＋ 耗尽**原样返回最后失败结果**（**不降级**）；`DefaultLoop` 新可选参 `act_wrapper`（`None` ⇒ 逐字不变）；组合根**三 loop（主/子/神兽）注入、宠物不接**；**Fallback/Pipeline 首次单测**；**Rollback 维持 loop 级既有路径**。键 `constraints.retry_attempts`（int ≥0，**0=关=缺省**） | `0209` / ADR-0199 |
| **E147** | **`InfoMap` 生产只接了一处**（Core.md 项目信息段）⇒ context spec「信息地图」的**千页级业务文档**场景**未接线**：目录层答不出「有哪些文档」 | `VectorStore` ABC 补两个 **fail-soft** 访问器（缺省实现返 `[]` ⇒ 第三方实现零改动即静默 no-op）：`document_ids()` / `chunk_texts(doc_id)`；`SqliteVectorStore` 实现（chunks 按**数字后缀序**拼回原文 —— `#10`＞`#2` 字典序陷阱）；组合根 `_index_rag_docs` 在 build 期 `info_map.index(...)`（**index 非 register**）。**文档数上限 16 必须有**（pointers 块不受预算裁剪 ⇒ N 文档暴露 8N 行无界注入）。键 `context.rag_info_map`（bool 缺省 False） | `0210` / ADR-0200 |
| **E148** | **`session_chain` 零生产消费者** —— `0202` 立的**写侧**（`after:` 标注）通了、**读侧不通** ⇒ 链**只在测试里可读**，运维面看不到「哪些轮失败、链条怎么接」 | 落 `core.diagnostics`（`0162` 立的**只读诊断源**，**不**落 `memory` —— 会多一个消费面）：新增 view `render_chain`（`_sealed` **不抛**）＋ `Deps` 加 callable 句柄 `chain`（**不 import runtime/ui**）；`_diag_deps` 侧**裸店**（`_memory_summary` 先例，**零效应**）；TUI `_COMMANDS` **只读块**加 `/chain`。规格 ADD Scenario **×2**、**零效应断言保留** | `0211` / ADR-0201 |
| **E149** | **「技能→插件」生产不可达**：`BenchmarkScorer` **接收** `runners` 但由组合根注入、**构造时未传** ⇒ 恒在「无绑定基准/无样本/无 runner」三态返 `None` ⇒ `Evaluator` 判 **`freeze`** ⇒ `crystallize` 抛 `EVAL_FROZEN`；且**全仓无**生产 `register`/`set_baseline` 面 | **硬门控 = OPT_IN（缺省关）** —— 判据「**注册基准 ≠ 同意执行**」（跑基准烧 token ⇒ 执行面须**单独显式**开）；runner **挂 `general` 兜底子 profile**（**非主 loop** —— 主 loop 会 `_maintain→_cold_path→scorer→runner→主 loop.arun` **递归**，今日仅靠 900s 节拍闸挡、脆；子 loop 无 `cold_path`/`trace_observer` ⇒ 无递归）；**闭包晚绑定** ＋ 拆 `_run_bench_sample`（可单测）/ `_bench_runner`；**CLI 注册面** `evolve benchmark {register\|set-baseline\|list}`（**数据面免 runtime**、`--plugin-id` **必填**） | `0212` / ADR-0202 |
| **E150** | **「原始文档 → 可持久化摘要」没有入口**：`rag ingest` 只做「分块 → embedding」，`rag ask` 是**一次性**问答、**不落盘** ⇒ 系统里的「总结」**全是会话结晶**；目录层答「有哪些文档」、检索层答「哪段相关」，唯独「**这份文档讲了什么**」的**结论层**缺失 | **落点 = notes 结论层**（用户裁决；rag 是**检索**面、塞回 chunk 会**污染检索语料**）；**显式旗即 opt-in**（`rag ingest --summarize`，**无配置键、无环境行为**）；摘要调用 = **入口侧复刻 `_llm_text` 4 行接缝**（**不复用** `summarize.py` —— 那是**会话压实**形状）；**双守护免费获得**（`observe_turn` 只覆写 `notes.turn`、`promote` 只覆写 `notes.promote`）；**进 digest 命中节选**（**不**入 `_ARCHIVE_SOURCES`） | `0213` / ADR-0203 |
| **E151** | **长时单轮被杀，整轮无痕**：`create_checkpoint` 生产**唯一调用链**是编排器波次回调 ⇒ 一个**非编排的长时单轮**中途被杀**整轮无落盘痕迹**、重启**无呈现** | **两写点**（轮首 `done=False` / 轮末 `done=True`，**不**逐步刷新 —— `_persist` 每 `put` 全量重写 ⇒ 逐步 O(n²)，增长由 `0208` 兜）；**`turn.<trace_id>` 命名空间 ＋ `kind="turn"` 双判据**（防 `task --resume` 误接**不可重放**的续跑）；**闭包注入**（loop **不** import durability）＋ `except DurabilityError → warn`；**分流不重构**（既有任务面语义**逐字不变**，换为 `turn_tasks` 集合 ＋ 守卫）；**呈现独立一段**（报数量与会话、**不含** `task --resume`、**不回显轮目标正文**）；**缺省关** | `0214` / ADR-0204 |

---

## §3 逐 change 收口要点

### `0206` 记忆后端落盘耐久（`memory` / ADR-0196 / E143）
- **规格**：`memory` **ADDED**「记忆后端落盘耐久（backend durability）」＋ 4 Scenario ⇒ canonical
  **15 → 16** req / **111 → 115** scen（0 Requirement-header / 0 Scenario-title 丢失）。
- **实现**：`src/core/memory/backend.py`（`_persist` tmp＋`os.replace`、`_load` 逐行容错＋坏行计数 warn）。
- **测试**：新 `tests/test_memory_backend_durability.py`（**+5**）—— 完好往返逐字节不变 / 人为半行 ⇒
  重载不炸好行俱在 / **SIGKILL 子进程**镜像 `test_durability_crash.py`。
- **反证**：**3 组红**（实现前：半写丢库 / 坏行炸启动 ×2）；复原即绿。
- **豁免说明**：本批**唯一缺省开** —— 完好文件行为逐字不变、损坏文件从「启动崩溃」变「跳过坏行」
  ⇒ **缺陷修复非新行为**（ADR-0196 明写）。**局限**见 §3 ADR-0196 行。

### `0207` 恢复扫描入口全覆盖（`durability` / ADR-0197 / E144）
- **规格**：`durability` **MODIFIED**「崩溃恢复」（全量替换 narrative ＋ **ADD** Scenario「全部交互
  入口启动扫描呈现」）⇒ canonical **4 → 4** req（MODIFIED 不增）/ **13 → 14** scen。
- **实现**：`src/core/entry.py`（`repl`/`run`/`app` 三处 `_build_ui(..., surface_recovery=True)` ＋
  `mcp serve` 显式调 `_surface_incomplete`，**只打 stderr**）。
- **测试**：`tests/test_entry.py` 增补（**+6**，`_patch_fake_runtime`/`_FakeBridge` 模式）。
- **反证**：**4 参例红**（摘旗 3 处 ＋ 摘 `mcp serve` 显式调用）。**局限**见 §3 ADR-0197 行。

### `0208` 保留策略接线（`durability` / ADR-0198 / E145）
- **规格**：`durability` **MODIFIED**「生命周期与保留策略」（全量替换 ＋ **ADD** Scenario ×3）⇒
  canonical **4 → 4** req / **14 → 17** scen。
- **实现**：`src/core/runtime.py`（`_write_checkpoint` 落盘后 `retention.apply`）、
  `src/core/configuration/manager.py`（`durability.retention.max_count`（int ≥1）＋
  `durability.retention.time_window_s`（float ≥0），`map_to` 前缀自动进段白名单；校验镜像
  `_circuit_breaker_errors`）。
- **测试**：新 `tests/test_retention_wiring.py`（**+13**：4 接线 ＋ 1 声明 ＋ 2 三面 ＋ 1 缺省访问器
  ＋ 5 非法参例）。
- **反证**：**3 例红**（摘 `retention.apply` 调用）。**局限**见 §3 ADR-0198 行。

### `0209` 容错件接线（`constraints` / ADR-0199 / E146）
- **规格**：`constraints` **MODIFIED**「容错中间件」（全量替换 7 Scenario 逐字 ＋ **ADD** Scenario ×5
  ＋ 库能力边界段）⇒ canonical **3 → 3** req（MODIFIED 不增）/ **11 → 16** scen。
- **实现**：新 `src/core/loop/fault_adapter.py`（`FaultChain`）；`src/core/loop/default.py`
  （`act_wrapper` 可选参）；`src/core/runtime.py`（三 loop 注入、宠物不接）；
  `src/core/configuration/manager.py`（`constraints.retry_attempts` ＋ `retry_policy()`）。
- **测试**：新 `tests/test_fault_wiring.py`（**+20**：12 重试/配置 ＋ 3 库能力单测 ＋ 2 组合根注入）
  ＋ `tests/test_constraints.py` 增补（Fallback/Pipeline **首次单测**）。
- **反证**：**3 例红**（摘重试循环）；**摘可逆门 ⇒ 不可逆用例红**。**已验证**：效应只在成功后记
  ⇒ 重试**不双记账**。**局限**见 §3 ADR-0199 行（telemetry `duration_ms` 含退避；
  「TIMEOUT 部分外写」的既有风险被重试**放大** —— 只对可逆工具重试即缓解；`RETRY_EXHAUSTED` 码
  仍**不用**（原样返回语义））。

### `0210` rag 文档进信息地图（`context`＋`rag` / ADR-0200 / E147）
- **规格**：`context` **MODIFIED**「信息地图」＋ **ADD** Scenario ×3、`rag` **MODIFIED**「本地向量库
  存储」＋ **ADD** Scenario ×1 ⇒ canonical context **8 → 8** req / **33 → 36** scen、
  rag **7 → 7** req / **14 → 15** scen。
- **实现**：`src/core/rag/vector_store.py`（fail-soft 访问器）、`src/core/runtime.py`
  （`_index_rag_docs` ＋ `vector_store` 局部引用）、`src/core/configuration/manager.py`
  （`context.rag_info_map`）。
- **测试**：`tests/test_rag_wiring.py` 增补（**+7**）。
- **反证**：**2 例红**（摘上限切片 / 摘旗守卫，各 `1 failed, 13 passed`）。**ADR 必引 ADR-0097⑥**：
  组合根注入是 RAG 参与 loop 上下文的**唯一合法路径**（`test_architecture.py` 守护，零改动即过）。
  **局限**见 §3 ADR-0200 行。

### `0211` 情景链读侧进只读诊断面（`memory` / ADR-0201 / E148）
- **规格**：`memory` **MODIFIED**「情景链（时序相邻标注）」（全量替换 (a)–(f) 逐字 ＋ **ADD** (g)
  只读呈现面）＋ **ADD** Scenario ×2 ⇒ canonical **16 → 16** req / **115 → 117** scen。
- **实现**：`src/core/diagnostics/views.py`（`render_chain`）、`deps.py`（callable `chain` 句柄）、
  `src/core/ui/repl.py`（`/chain` ＋ `_show_chain`）、`src/core/entry.py`（`_diag_deps` 注入**裸店**）。
- **测试**：`tests/test_diagnostics.py` / `tests/test_repl.py` / `tests/test_entry.py` 增补（**+7**）。
- **反证**：**3 组红**（摘 `/chain` 登记 ＋ palette ×2 ⇒ `3 failed, 22 passed`；摘 `_diag_deps` 的
  `chain=` 注入 ⇒ `1 failed, 96 deselected`；把 `render_chain` 句柄分支短路 ⇒ `6 failed, 104 deselected`）。
  **局限**见 §3 ADR-0201 行。

### `0212` 结晶通路（`evolution` / ADR-0202 / E149）
- **规格**：`evolution` **MODIFIED**「评测基建」（全量替换 ＋ 3 bullets ＋ **ADD** Scenario ×3）⇒
  canonical **16 → 16** req / **84 → 87** scen（条内 6 → 9）。
- **实现**：`src/core/runtime.py`（`OPT_IN_MODULES += ("evolution_benchmark_runner",)`、
  `runners={...}` 注入、`_run_coro` / `_run_bench_sample` / `_bench_runner`（**晚绑定**））、
  `src/core/entry.py`（嵌套 `evolve benchmark {register|set-baseline|list}`）。
- **测试**：新 `tests/test_benchmark_runner.py`（**+10**，含 `test_opt_in_whitelist_members` 重命名扩断言）。
- **反证**：**2 组红**（门控强制为开 ⇒ `2 failed, 8 passed`；摘 `runners=runners` ⇒ `2 failed, 8 passed`）。
  **局限**见 §3 ADR-0202 行（注册后**重启才见**；样本**串行**跑在维护线程；测的是**子 profile 形状**；
  `_crystallize_plugin` 仍**只登记不产真插件**）。

### `0213` 文档→摘要（`rag`＋`notes` / ADR-0203 / E150）
- **规格**：`rag` **MODIFIED**「文档摄取与分块」＋ 2 bullets ＋ **ADD** Scenario ×1、
  `notes` **ADDED**「文档摘要笔记（notes.rag）」＋ Scenario ×4 ⇒ canonical rag **7 → 7** req /
  **15 → 16** scen、notes **5 → 6** req / **42 → 46** scen。
- **实现**：`src/core/entry.py`（`--summarize` 旗 ＋ 4 行 `_llm_text` 接缝复刻 ＋
  `_write_doc_summary_note`）。**实施期落点订正**：初版拟落 `notes/rag_summary.py`，被 **ADR-0148
  三面边界**结构门禁判红（offender `write_doc_summary -> ['doc']`）⇒ **不退门禁、改落点**到 `entry`
  （`test_rag_not_imported_by_reference_chain` 明列的 rag 例外）⇒ **`notes` 包零改动**、行为逐字相同。
- **测试**：新 `tests/test_rag_summary.py`（**+8**）。
- **反证**：**2 组红**（摘摘要分支 ⇒ `1 failed, 7 passed`；`_ARCHIVE_SOURCES` 加 `notes.rag` ⇒
  `1 failed, 7 passed`；两次 md5 复原逐字节相同）。**局限**见 §3 ADR-0203 行。

### `0214` 主循环轮级检查点（`durability`＋`loop` / ADR-0204 / E151）
- **规格**：`durability` **ADDED**「会话轮级检查点」＋ Scenario ×5；**既有 4 Requirement 逐字保留**
  （本 change **不** MODIFY）⇒ canonical **4 → 5** req / **17 → 22** scen。
- **实现**：`src/core/loop/default.py`（`TurnCheckpoint` 别名 / `turn_checkpoint` 参 / `_mark_turn` /
  两写点）、`src/core/runtime.py`（`_TURN_TASK_PREFIX` / `_TURN_KIND` / `_turn_checkpoint` 闭包 /
  `_is_turn_task` / `_turn_incomplete` / `_recover_incomplete` 分流守卫 / `Runtime.recover_turns()`）、
  `src/core/entry.py`（`_surface_incomplete` 轮面段）、`src/core/configuration/manager.py`
  （`loop.turn_checkpoint`）。
- **测试**：新 `tests/test_turn_checkpoint.py`（**+18**）＋ `tests/test_entry.py` / `tests/test_phase13.py`
  既有桩补 `recover_turns` 协作方。
- **反证**：**四组** —— (A) 摘轮末 `done=True` ⇒ `3 failed, 15 passed`；(B) 摘轮首写 ⇒
  `4 failed, 14 passed`；(C) 摘**第一环** `kind` 分类 ⇒ `18 passed`（被**第二环**前缀守卫**遮蔽 ⇒
  冗余**，记录为「冗余已验证」而非失败）；(C') 摘**第二环续跑面守卫** ⇒ `4 failed, 14 passed`；
  四次复原 ⇒ md5／`diff -q` **逐字节相同**。
- **局限**：见 §3 ADR-0204 行（**不含撤销账本** —— `EffectTracker` 的 `undo` 是闭包不可序列化；
  快照**仅供呈现不供重放**；**仅主 loop 接线**；**轮内不刷新**）。

---

## §4 显式不做（全批次）

- **不**做降级回复上线（`0209` §0 修正；Fallback 的降级回复会静默抑制 trace 回滚 ＋ 终结 loop
  杀死 ReAct 自愈 ⇒ 如需另立 change）。
- **不**接 `storage_quota` 通道与 `strategy` 字段（`0208`；库能力保留）。
- **不**让 `_crystallize_plugin` 产真插件（`0212`；`plugin_ids.py` 有意裁决，不在本批）。
- **不**做摘要质量门 / 分段摘要（`0213`）。
- **不**给轮级检查点接重放 / 撤销账本（`0214`，恢复语义仍**显式**）。
- **不**改 `BudgetManager` 记 pointers（`0210` 用**文档数上限**替代）。
- **不**改 `src/core/notes/` 与 `src/core/rag/`（`0213` 落点订正后**零改动**）。

---

## §5 收口与验证

- **四门禁（直连二进制，不用 `uv run`）**：`.venv/bin/ruff check src tests` ·
  `.venv/bin/ruff format --check src tests` · `/home/harry/.praisonai/venv/bin/pyright`（**0-0-0**）·
  `.venv/bin/pytest -q`（**2421 passed**）。
- `openspec validate --all` ⇒ **32 passed / 0 failed**（含 change）→ 归档后 **31 passed / 0 failed**（specs）；
  九条 change 各经
  `python3 /tmp/openspec_archive.py <change-NAME>` 手工归档（断言 0 Requirement-header 丢失 /
  0 Scenario-title 丢失）后落 `doc/openspec/changes/archive/`。
- 每条**单次提交**（尾 `Co-Authored-By: Claude Code <noreply@anthropic.com>`）：
  - `0206` → `679879a feat(memory): 记忆后端原子写 + 逐行容错（change 0206 / ADR-0196 / 台账 E143）`
  - `0207` → `4779574 feat(durability): 恢复扫描入口全覆盖（change 0207 / ADR-0197 / 台账 E144）`
  - `0208` → `c50a235 feat(durability): 保留策略接线（change 0208 / ADR-0198 / 台账 E145）`
  - `0209` → `5baf419 feat(constraints): 容错件接线（change 0209 / ADR-0199 / 台账 E146）`
  - `0210` → `107296a feat(context): rag 文档进信息地图（change 0210 / ADR-0200 / 台账 E147）`
  - `0211` → `fe0cc92 feat(memory): session_chain 读侧进诊断面（change 0211 / ADR-0201 / 台账 E148）`
  - `0212` → `3d484c3 feat(evolution): 结晶通路 runner 注入 + 基准注册操作面（change 0212 / ADR-0202 / 台账 E149）`
  - `0213` → `5977071 feat(rag): 文档→摘要落 notes 结论笔记（change 0213 / ADR-0203 / 台账 E150）`
  - `0214` → `5830174 feat(durability): 主循环会话轮级检查点（change 0214 / ADR-0204 / 台账 E151）`
- 文档面：`doc/04-testing/test-cases.md` §119~§127 · `coding-plan/known-risk.md` §1（E143~E151）/
  §3（ADR-0196~ADR-0204）· `doc/02-modules/`（memory / durability / constraints / context /
  evolution / rag / notes / loop / configuration 各一节）· `doc/03-interfaces/`
  （memory / durability / ui / evolution / notes 各一节）· ADR 变更追踪表九行 · 记忆更新。
- **未闭（本批账外、仍挂）**：E27（IM 网关未接线）、E55、C7（TTS）、E91、E100（余运维动词）、
  E101（hooks 实现）。
