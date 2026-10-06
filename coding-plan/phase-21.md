# Phase 21 — 进化引擎「架构模块维度」归因接线（内部核心插件真实覆盖）

> **定位**：审计发现 `evolution` 的 **plugin 维度（kind="plugin"）** 整条接线未打通，导致「内部核心插件」从未被进化引擎真实覆盖——**trace 通路未接通**（冷路径拿不到证据）、**trace 无模块归因**、**提案静态绑 skill**、**结晶谎报发布**。本 Phase 只做**接线**（补回调/补字段/补常量/补映射），**不引入任何自动改架构代码的能力**，产出严格停在「kind=plugin 候选进 pending 人工队列」，与 phase-18 红线一致。
>
> **红线（phase-18 §0，本 Phase 必须遵守）**：维度 1（技能库/SOP）全自动；维度 2（架构级进化）**人工 confirm 必审**；JEV 优先、LLM 兜底。本 Phase 打通的是「归因到内部核心模块 + 产出 kind=plugin 候选进 pending」，**绝不自动发布、绝不自动晋升世代、绝不自动改架构代码**。
>
> **口径裁决（本次，选 (b)）**：**信号走既有 trace 通道，不新建、也不纳入 `PluginRegistry`**。
> 理由见 §1.3。原稿的「registry 质量信号接口 + `registry.signals` + `registry.promote`」整体**废止**——
> `PluginRegistry` 全仓只在 `PluginInstaller` 内部默认构造（`installable.py:93`），
> 组合根 `runtime.py` 里**没有 `registry` 变量**（`runtime.py:396` 连 `registry=` 都不传），
> 照原稿实现会直接 `NameError`；且它买不到本 Phase 的任何一条验收（详见 §1.3）。

---

## 1. 范围与定位

- **分层图位置**：L4（进化引擎 / evolution capability）内部，`diagnose → propose → validate → evaluate` 闭环中
  `diagnose` 与 `propose` 两段的**输入接线**缺失。
- **覆盖 capability**：`contracts_summary.md` §10 evolution（进化引擎结晶闭环）。

### 1.1 范围（5 个断裂点，全部只接线、不改决策语义）

| # | 断裂点 | 现象（一手核实） |
|---|---|---|
| **0** | **trace 通路未接通**（前置，原稿漏）　✅ `0101` | `EvolutionWorker` 的输入 `self._completed` 在**生产恒空**：`on_trace_complete` 全仓只有 `worker.py:51` 定义 + `tests/` 调用，**零生产调用方**；loop 的收尾只调 `self._cold_path()`（`default.py:302-306`），而 `ColdPath = Callable[[], None]`（`default.py:43`）**不带 trace_id** ⇒ `_collect()` 恒 `[]` ⇒ `run_cycle` 只会走到 `no_evidence`（`engine.py:92-93`） |
| **1** | **trace 无模块归因**　✅ `0101` | `worker.py:112` `plugin_id=tool or None` 绑的是**工具名**；`events.py:19` 的 `kind` 只有 `model_io/tool_call/effect/metric`，**无「架构模块失败」通道**；且 `TraceEvent` **无模块字段** |
| **2** | **诊断信号源**（订正）　✅ `0101` | 原稿说「`Diagnoser(plugin_signals)` 无来源」——现象属实（`diagnoser.py:22` + `runtime.py:448` 无参装配），但 `Diagnoser.diagnose` **本就从 trace 归因**（`diagnoser.py:37-39` 按 `t.plugin_id` 计分）⇒ **不需要新载体**，真缺口是**生产端没有带模块归因的 trace**（=断裂 0 + 断裂 1） |
| **3** | **提案 kind 静态绑定**　✅ `0102` | `proposer.py:21` `kind: Literal["skill","plugin"] = "skill"`；`runtime.py:449` `Proposer()` 无参 ⇒ `kind` 恒 `"skill"`、`risk_level` 恒 `"low"`（该行在 **`proposer.py:35`**，原稿写 `:33`） |
| **4** | **结晶谎报发布**　✅ `0102` | `engine.py:259-271` `_crystallize_plugin` 只写 L3 记忆，却返回 `EvolutionOutcome(status="published")`（`:271`）——**无世代可晋升、也没有任何架构产物被发布**，`published` 是谎报 |

### 1.2 明确不做

- **不把 13 个内部模块纳入 `PluginRegistry`**（原稿 §5.1/§5.2/§5.5 的 registry 路线，废止）。
- **不自动晋升世代 / 不自动改架构代码**（红线；且全链路没有「新一代 `Plugin` 对象」的生产者——候选 delta 只有 `{"issue": …}`，`proposer.py:31`）。
- **不做工具级 trace**（`action_completed` 未入 trace 流，见 §1.4 转出）。
- 外部安装插件（不在覆盖范围，见 phase-18 §1.2）；JEV 决策接入（依赖真凭证，后续单独排期）。

### 1.3 为什么选 (b) 而不是 (a)（纳入 PluginRegistry）

| 维度 | (a) 纳入 PluginRegistry | **(b) 信号走 trace（选定）** |
|---|---|---|
| 验收 ①（信号接口） | 接口能加，但**无真实生产者** | ✅ 不需要新接口 |
| 验收 ②（失败记信号） | ❌ `FAULTED` 只在 `load()/unload()` 失败时产生（`registry.py:118-164`），内部模块**不经它加载** ⇒ 仍要在真实失败点插桩 | ✅ 直接在真实失败点插桩 |
| 验收 ⑥（结晶语义） | ❌ 无新一代 `Plugin` 生产者，`promote()` 仍是空转，且只改 `_generations` 会与 `_plugins[p].generation` 不一致、随后同世代 `register()` 被 `GENERATION_CONFLICT` 挡（`registry.py:52-57`） | ✅ 诚实降级为「登记批准、不谎报」 |
| 代价 | (b) 全部 **+** 给 `evolution.collector/diagnoser/evaluator/validator/worker`（5 个，零 `generation/schema/coeffects`）补 plugin 形状，`load/unload` 只能 `pass` 空转（该形态**被明确拒绝** —— **订正**：出处是 **ADR-0094 决策①**，原稿误引 ADR-0054；ADR-0054 讲冷路径驱动面）+ 与 `PluginInstaller` 私有一把注册表（`installable.py:93`）的归属裁决 | 1 个 change 的量 |

> **战略口径**：等「真的会产出新一代插件实现（模型生成代码 / 人工提交补丁 → 新 `Plugin` 对象）」那个 Phase，再做 (a)——那时 `promote(plugin: Plugin)` 才有语义。本 Phase 的使命是**打通归因与人工门**。

### 1.4 转出账本（本 Phase 不做，须登记）

1. **工具级 trace**：`_to_traces` 只认 `kind == "tool_call"`（`worker.py:97`），而工具调用的唯一生产者为 `TraceLogger.log_tool_call`（`tracer.py:69-82`），**零生产调用方**；loop 把 `action_completed` 作为 `LoopEvent` 外发却**不 `_trace`**（`default.py:235-244`）⇒ evolution 的 **skill 分支在产线无输入**（技能维度主线由 `turn_observer` → SOP/技能反馈承载，未断）。
2. **13 模块纳入注册表 + 世代晋升**：推迟到有新一代实现生产者的 Phase（见 §1.3）。

> **收口（change `0107`／ADR-0100）**：① **已关闭**（生产方接线）；② **改判为「裁决：不纳入」**（不再是待办，
> 重开条件仍为「有新一代 `Plugin` 对象生产者」，已记入 ADR-0100 与 `plugin_ids.py` docstring）。

---

## 2. 里程碑验收

对应 **M4 自进化**（Phase 5）的 plugin 维度收口。验收清单（可勾选）：

- [x] ① **trace 通路接通**（change `0101`）：loop 收尾按**轮**回调 trace 完成（`on_trace_complete` 语义，**不受维护节拍节流**），组合根在主 loop 注入 `EvolutionWorker.on_trace_complete`；回调异常降级留痕、不中断本轮；evolution 关闭时**不注入**（不造空转闭包）。
- [x] ② **模块归因字段**（change `0101`）：`TraceEvent` 可携带可选 `module_id`（缺省 `None`，序列化向后兼容）；loop 的**自身失败**事件（`loop_finished{failed:true}`）带 `module_id="loop.default"`。
- [x] ③ **采集层可归因架构模块**（change `0101`）：`_to_traces` 把**带 `module_id`** 的事件适配为 `Trace(plugin_id=module_id, ...)`；既有 `tool_call` 路径行为不变（端到端已证：loop 预算耗尽 ⇒ 归因 `loop.default`）。
- [x] ④ **诊断落白名单**（change `0101`）：`Diagnoser.diagnose` 能把对比诊断归因到 13 个内部核心模块 id 之一；无模块级归因时按契约「人工介入」（既有语义，**不改 Diagnoser**）。
- [x] ⑤ **提案动态 kind**（change `0102`）：`Proposer` 按 `diagnosis.target_plugin` 是否命中 13 白名单决定——命中 → `kind="plugin"` + `risk_level="high"` + `status="pending"`；否则 `kind="skill"` + `risk_level="low"`；**显式传入 kind 仍覆盖**（既有调用面不破）。
- [x] ⑥ **结晶不谎报**（change `0102`）：`kind="plugin"` 走 `crystallize` 返回**新结局 `accepted`**（已批准、待人工实施），**不再返回 `published`**；L3 记忆留痕与观察期开窗保留；技能分支仍为 `published`（确实入库 `SkillLibrary`）。
- [x] ⑦ **红线验证**：`kind="plugin"` 候选默认 `pending`，无 `confirm` 绝不 `published`/`accepted`；`risk_level="high"` 必带**已批准且目标一致**的审批单（既有 `confirm` 语义，加守护测试）。

---

## 3. 依赖与前置

- **上游 Phase**：Phase 15（Validator/Evaluator/Sandbox/HITL）、Phase 18（进化双维度 + confirm 收口 + auto-dissolve）。
- **上游 capability**：`evolution`（诊断→提案→验证→评测闭环）、`observability`（trace 事件模型）、`loop`（收尾节拍与回调注入面）。
- **13 个内部核心模块 id**（**归因白名单常量**，单一真源；⚠️ 它们是**带 `plugin_id` 类属性的普通类**，**不是注册表成员**——这个区别必须写进常量文档串）：

  `composition.engine`、`composition.packager`、`composition.resolver`、`evolution.collector`、`evolution.diagnoser`、`evolution.engine`、`evolution.evaluator`、`evolution.proposer`、`evolution.validator`、`evolution.worker`、`im.gateway`、`loop.default`、`memory.store`。

- **前置证据（精确行号，已逐行核实）**：
  - `src/core/loop/default.py:43` → `ColdPath = Callable[[], None]`（**不带 trace_id**）。
  - `src/core/loop/default.py:302-306` → 收尾维护节拍里只调 `self._cold_path()`。
  - `src/core/loop/default.py:203/205/251/264` → loop 自产 trace 事件仅 `loop_started`/`step_completed`/`loop_finished`（**无 `tool_call`**）。
  - `src/core/evolution/worker.py:51` → `on_trace_complete`（**全仓零生产调用方**）；`:97` → `if event.kind != "tool_call": continue`；`:112` → `plugin_id=tool or None`。
  - `src/core/observability/events.py:19` → `kind` 仅 `model_io/tool_call/effect/metric`；`:13-20` → `TraceEvent` 无模块字段。
  - `src/core/evolution/diagnoser.py:22` → `__init__(self, plugin_signals: dict[str, float] | None = None)`；`:37-39` → 按 `t.plugin_id` 逐条计分（归因已可用）。
  - `src/core/runtime.py:446-461` → evolution 装配块（`Diagnoser()`/`Proposer()` 无参，`:448`/`:449`）；`:479-489` → 主 loop 装配（`cold_path=cold_path`，`:489`）。
  - `src/core/evolution/proposer.py:21` → 静态 `kind`；`:35` → `risk_level` 三目。
  - `src/core/evolution/engine.py:259-271` → `_crystallize_plugin`（只写 L3 + 返回 `published`）。
  - `src/core/plugin_registry/registry.py:39-40` → 仅 `_generations`/`_states`；`:46-62` → `register()`（`_generations` 赋值在 `:60`）；**无质量信号字段、无世代晋升方法**。

---

## 4. 首步任务（规格先行 / 单一真源 / 命名空间口径）

1. **补规格（先改规格再改代码）**：
   - `evolution/spec.md`：MODIFIED「经验采集」（补**模块归因的失败证据**可被采集）；
     MODIFIED「模块级提案」（补 **kind 由归因驱动**：命中内部核心模块 ⇒ `plugin` + `high`，否则 `skill` + `low`）；
     MODIFIED「结晶为技能/SOP」/「架构级候选强制人工审批」（补 **`accepted` 结局语义**：架构级候选批准后**不谎报发布**）。
   - `observability/spec.md`：MODIFIED「全链路日志」（事件 SHALL 可携带**模块归因**字段）。
   - `loop/spec.md`：MODIFIED「执行循环」（收尾 SHALL 按轮调用**可选的 trace 完成回调**，异常降级）。
2. **单一真源常量**：新建 `INTERNAL_PLUGIN_IDS`（13 个 id 的 `frozenset`），供 Proposer kind 判定与 trace 归因口径两处共用——避免硬编码漂移。
3. **命名空间口径**：在 `events.py` / `worker.py` 的数据类型注释里写明 `plugin_id` / `module_id` 的语义是
   **「归因对象 id」**（工具 id 形如 `tools.file_read`，或 13 个内部核心模块 id 之一），避免两套命名空间继续混用。

---

## 5. 实现顺序（模块级拓扑序 + 关键接口）

### 5.1 断裂 0 — trace 通路接通（先行，其余依赖它）　✅ change `0101`

- **模块**：`src/core/loop/default.py` + `src/core/runtime.py`。
- **改动**：
  ```python
  # loop/default.py（与 ColdPath 并列的新注入面）
  # trace 完成回调：每轮收尾提交 trace_id（供冷路径登记，不返回值）；
  # loop 不 import evolution（架构红线），生产侧注入组合根闭包。
  TraceObserver = Callable[[str], None]
  ```
  构造参数 `trace_observer: TraceObserver | None = None`；在 `astream` 收尾（与 `_maintain(trace_id)` 相邻、
  **在其之前**）调用，异常降级为 `self._trace(trace_id, "trace_observer_failed", {...})`（对齐
  `turn_observer_failed` / `action_observer_failed` 既有手法）。
- **装配**：`runtime.py` 在 evolution 装配块内取 `trace_observer = evolution_worker.on_trace_complete`，
  主 loop（`:479`）传 `trace_observer=trace_observer`；`evolution` 关闭时保持 `None`（不造空转闭包）。
- **为什么不在维护节拍内**：节拍被 `maintenance_interval` 节流 ⇒ 每 interval 只登记 1 条，`EvolutionTrigger`
  的「累计 N 条」语义会退化成「累计 N 个 interval」。热路径**只登记、不触发、不阻塞**（`worker.py:51` 的既定语义），
  冷路径机会仍由节拍给（`cold_path` 不动）。
- **测试**：回调被调用且收到 trace_id；回调抛错 ⇒ 本轮回复/终止语义不变且留痕；未注入 ⇒ 不调用；
  `build_runtime` 装配后主 loop 的该回调**确为** `worker.on_trace_complete`（fake planner，不出网）。

### 5.2 断裂 1 — trace 模块归因　✅ change `0101`

- **模块**：`src/core/observability/events.py` + `src/core/loop/default.py` + `src/core/evolution/worker.py`。
- **改动**：
  - `TraceEvent` 增 `module_id: str | None = None`（dataclass 默认值 ⇒ 既有构造/序列化不动）。
  - loop 把**自身失败**的可观测结局标上模块：`loop_finished` 事件（`default.py:264`）在 `failed` 为真时带
    `module_id="loop.default"`。
  - `worker._to_traces` 增一条通道：**带 `module_id`** 的事件 ⇒
    `Trace(plugin_id=module_id, task_type="module_health", action={"event": kind}, result=payload, success=<由 payload.failed 判定>)`；
    既有 `tool_call` 通道**逐字不变**。
- **验收**：一个 `loop.default` 失败事件 → trace 的 `plugin_id == "loop.default"`（非空 tool 名）。
- **注**：原稿 §5.3 的「`tool` 命中 `INTERNAL_PLUGIN_IDS` 时 `plugin_id=tool`」**删除**——tool id 命名空间是
  `tools.*`（`builtin.py:88/118/147/187/222`、`install_tools.py:78/98/117`），与 13 个模块 id **永不相交**，是**不可达逻辑**。

### 5.3 单一真源常量　✅ change `0102`

- **模块**：新建 `src/core/evolution/plugin_ids.py`（或就近置于 `evolution/models.py` 旁）。
  ```python
  INTERNAL_PLUGIN_IDS: frozenset[str] = frozenset({...13 个 id...})
  ```
  文档串须写明：**归因白名单**，非注册表成员（本仓内部模块未纳入 `PluginRegistry`）。

### 5.4 断裂 3 — Proposer 动态 kind　✅ change `0102`

- **模块**：`src/core/evolution/proposer.py`。
- **改动**：构造参数降级为**显式覆盖**——`kind: Literal["skill", "plugin"] | None = None`；
  `None`（缺省）⇒ `propose(diagnosis)` 内按 `diagnosis.target_plugin in INTERNAL_PLUGIN_IDS` 判定
  （命中 → `plugin`/`high`；否则 → `skill`/`low`）；显式传入仍**覆盖**（**既有 13 处 `Proposer(kind=…)` 调用与测试逐字不变**）。
  `runtime.py:449` 保持 `Proposer()` 无参即可。
- **验收**：`DiagnosisReport(target_plugin="loop.default")` → `Proposer().propose(...)` 产出
  `GenerationCandidate(kind="plugin", risk_level="high", status="pending")`；
  `target_plugin="tools.file_read"` → `skill`/`low`。

### 5.5 断裂 4 — 结晶不谎报发布　✅ change `0102`

- **模块**：`src/core/evolution/engine.py`（`_crystallize_plugin`）+ `src/core/entry.py`（CLI 文案）。
- **改动**：`kind="plugin"` 的结晶结局由 `published` 改为 **`accepted`**（「已批准、待人工实施」）：
  架构级候选批准后**没有**任何架构产物被发布（也无世代可晋升），`published` 是谎报。
  L3 记忆留痕（`engine.py:260-270`）与观察期开窗（`engine.py:178`）**保留**。
  技能分支（`_crystallize_skill`）**保持 `published`**（确实 `SkillLibrary.register`）。
- **红线守护**：`run_cycle`/`maybe_run` 全链路默认 `status="pending"`；测试断言「未 confirm ⇒ 无 `accepted`/`published` 结局」。
- **规格先行**：`accepted` 须先写进 `evolution/spec.md`（「结晶为技能/SOP」+「架构级候选强制人工审批」）。

---

## 6. 契约对齐

引用 `contracts_summary.md` §10 evolution（L115-119）：
- **能力**：结晶闭环（经验采集→结晶→溶解→诊断→提案→验证门→留出评测）。
- **契约**（本 Phase 对齐的 3 条）：
  - 「对比诊断归因到插件、无插件级归因则人工介入」→ §5.2 的模块归因 + 既有 `Diagnoser` 归因（不改）。
  - 「生成技能候选待人工确认」+「模块级提案过验证门才发布」→ §5.4 的 kind 由归因驱动 + `status="pending"`。
  - 「退化检测溶解回收」→ 与 auto-dissolve（phase-18 已落地）不冲突，本 Phase 不改。
- **接口签名（**订正**，原稿字段名/返回值有误）**：
  - `Diagnoser.diagnose(traces, *, prior=None) -> DiagnosisReport`；归因字段是 **`target_plugin`**（`models.py:42`，**非 `plugin_id`**）。
  - `Proposer.propose(diagnosis: DiagnosisReport) -> GenerationCandidate`（**单个**，非 `list[...]`）。
  - `Proposer(kind: Literal["skill","plugin"] | None = None)`（显式覆盖；缺省由归因驱动）。
  - `GenerationCandidate.status: str = "pending"`（`pending | confirmed | rejected`）；`risk_level: Literal["low","high"]`。
  - `Trace.plugin_id: str | None`（归因对象 id）；`TraceEvent.module_id: str | None`（新增）。
  - `EvolutionOutcome.status` 词表 **+ `accepted`**（架构级批准、未实施）。
  - `Loop.TraceObserver = Callable[[str], None]`（新增注入面）。

---

## 7. 门禁验收

- [x] `ruff check` 全绿（change `0102` 收尾时：317 files）。
- [x] `pyright` 0 errors（`0 errors, 0 warnings, 0 informations`）。
- [x] `pytest` 全绿（新增用例覆盖 §5.1~§5.5 各验收点；change `0102` 收尾时 **1176 passed**）。
- [x] **本 Phase 专属校验**：一条集成测试模拟「`loop.default` 故障 → 事件带 `module_id` → 采集适配为 `Trace`
      → `Diagnose` 归因到 `loop.default` → `Propose` 产出 `kind="plugin"`/`risk_level="high"`/`status="pending"`
      → 未 confirm 断言无 `accepted` → 带审批单 confirm → crystallize 断言 `accepted`」（fake planner，**不出网**）。
      落地：`tests/test_evolution_attribution.py`（7 例，覆盖归因驱动 kind / 显式覆盖 / 白名单逐元素一致性 /
      架构级 `accepted` / 技能级 `published` / 未确认 `CANDIDATE_PENDING`）。

---

## 8. 提交规范

- **两个 change 交付**（每 change 一个 commit，格式 `feat(<capability>): ...`）：
  1. **change 0101 — trace 通路与模块归因**（断裂 0 + 断裂 1）：`observability` + `loop` + `evolution` 三处 delta。
     `feat(observability): trace 收尾回调与模块归因（change 0101）`
  2. **change 0102 — 归因驱动提案与结晶语义诚实化**（断裂 3 + 断裂 4 + 白名单常量）：
     `feat(evolution): 归因驱动提案与结晶语义诚实化（change 0102）`
- 每 change 走完：规格 delta → 测试（红）→ 实现（绿）→ 四门 → **手工归档**（本仓 `openspec archive` 因 symlink+WSL 必失败）
  → `openspec validate --all` → 账本回填（`phase-19.md` / `phase-20.md` / `README.md`）→ 记忆 → commit。
- 更新 `README.md` §2 总览表与状态列，追加 phase-21 行（状态：🚧 施工中 → ✅ 完成）。
- 涉及文件清单：`doc/openspec/specs/{evolution,observability,loop}/spec.md`、
  `src/core/observability/events.py`、`src/core/loop/default.py`、`src/core/evolution/{worker,proposer,engine,plugin_ids}.py`、
  `src/core/runtime.py`、`src/core/entry.py` + 对应测试。
- **不**提交：`phase-21-findings.md`（审计工作底稿，仅本地参考）。（**2026-10-06 订正**：**已提交入库** —— 归档 change `0101` 的 proposal 以本文件为审计出处，不入库该引用即悬空；同上 §9 末补记。）
- **转出账本**（§1.4 两项）须在 `phase-19.md` §5 或 `phase-20.md` 登记为待办行。

---

## 9. 收口状态（2026-10-05）

本 Phase **两个 change 全部交付并归档**，5 个断裂点全闭：

| 断裂点 | change | 归档目录 |
|---|---|---|
| 0 trace 通路未接通 / 1 trace 无模块归因 / 2 诊断信号源 | `0101` | `doc/openspec/changes/archive/2026-10-05-0101-trace-module-attribution/` |
| 3 提案 kind 静态绑定 / 4 结晶谎报发布 / 白名单常量 | `0102` | `doc/openspec/changes/archive/2026-10-05-0102-attribution-driven-proposal/` |

- **新增 ADR**：ADR-0094（trace 通道 + 模块归因，不纳入 `PluginRegistry`）、ADR-0095（归因驱动 `kind` +
  结晶结局诚实化 `accepted`）。
- **新增错误码**：无（`accepted` 是**结局词**，不是错误码）。
- **规格**：`observability` / `loop` / `evolution` 三处 MODIFIED（`evolution` 含「模块级提案」
  「架构级候选强制人工审批」「观察期回归自动溶解」三条）。
- **转出账本（§1.4）**：① 工具级 trace 缺失（= `phase-19.md` **E30**）—— ✅ **已关闭**（change `0107`／
  ADR-0100：生产方接线到 loop 非终止动作分支）；② 13（后为 14）模块纳入注册表 + 世代晋升（= `phase-19.md`
  **E31**）—— ⚖️ **改判为「裁决：不纳入」**（change `0107`／ADR-0100：零消费者 / 形态即空转 / 前置条件更远；
  重开条件 = 有新一代 `Plugin` 对象生产者，已记入 ADR-0100 与 `plugin_ids.py` docstring）。
- **未提交**：`coding-plan/phase-21-findings.md`（审计工作底稿，仅本地参考）。（**2026-10-06 补记**：**已提交入库** —— 原判「仅本地参考」作废，理由同上：`doc/openspec/changes/archive/2026-10-05-0101-trace-module-attribution/proposal.md` 正文以「审计（`coding-plan/phase-21-findings.md`）」为证据出处，底稿不入库则该引用不可达。历史正文不改写，仅追加此条。）
