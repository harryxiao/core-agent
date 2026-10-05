# Phase 26：beast/pet「专属记忆」接线收尾账本（E37 神兽独立记忆命名空间断裂 + E38 神兽记忆封存无实现 + E39 宠物偏好追踪断裂）

> **定位**：本 Phase 是「beast 神兽模式 / pet 宠物模式」两条**专属记忆链路**的系统级核查账本 —— 核查对象是 `core/beast/` ↔ `core/pet/core/` ↔ `core/loop/`（落记忆路径）↔ `core/orchestration/`（handoff 链路）↔ `core/memory/`（存储与检索）五处的**接线一致性**。三条均为**本次 review 一手复核新发现**，与已交付账本无重叠。
> **规则**：严格按依赖拓扑序推进；每 Phase 完成须 100% 通过门禁四件套；所有 spec/interface 契约以仓库原文为准。

---

## 0. 结论总览

| 编号 | 缺陷 | 现状 | 归属 | 档位 | 建议 |
|---|---|---|---|---|---|
| E37 | 神兽「独立记忆命名空间」断裂（`remember` 死代码 + `source="loop"` 污染 + `read` 无 source 过滤 + `handoff` 不传 session_id） | ✅ 已闭（change `0110`／ADR-0103） | beast-mode 独立命名空间承诺 | **高**（污染主记忆 + 承诺不可达） | 装配层注入 source + `read` 加 source 过滤 + `handoff` 传 session_id + 唤醒 `remember` |
| E38 | 神兽记忆「封存」无实现（`models.py:20` 仅注释） | ✅ 已闭（change `0110`／ADR-0103；**判据订正**见下） | beast-mode 封存/召回承诺 | 中（依赖 E37） | 实现 seal/recall（依赖 E37 独立命名空间） |
| E39 | 宠物「偏好追踪」断裂（`observe` 死代码 + `wake` 不 observe） | ✅ 已闭（change `0110`／ADR-0103；**判据订正**见下） | pet-mode 偏好追踪承诺 | 中（`source="user"` 从未落库） | 唤醒 `observe` + `wake` 后 observe |

> **共同口径**：三条同主题（beast/pet 专属记忆链路的接线收尾）—— E37/E39 **同批修**（同 change），E38 依赖 E37 的 source 过滤，建议**同批**（避免命名空间二次接线）。三条均**不挡核心回路**（非 P0 阻断），为「承诺已声明、实现未接线」的收尾类缺陷。
> **判据订正（收口时一手复核，2 条 —— 本账本 §1.2/§2.2 与 §1.3/§2.3 的表述以规格原文为准）**：
> ① E38「实现 seal/recall」→ 规格 `beast-mode/spec.md:89` 把封存定义为**效果**条款（「`source=beast.*` 不再被主 loop read 命中」），**无 API 条款**
> ⇒ 封存由 E37 的读取侧排除落地，**不新造 seal/recall API**；召回（复位）早已由 `Manual Recall` + `summon` 收尾的 `recall()` 实现。
> ② E39「在 `PetSession.wake` 调用 `observe`」→ 规格 `pet-mode/spec.md:231-234` 要求观察点落在**生产入口激活**（主人原话）
> ⇒ 接在 `activate_from_cli`/`activate_from_nl`/`PetControl.assign` 三处，**不在 `wake()`**（唤醒无主人行为可观察，且斜杠/空 `rest` 的合成 goal 会**谎报**偏好，违 R7）。
> **耦合（关键）**：E37 修复后，神兽轨迹才真正以 `source=beast.<agent_id>` 独立落库；否则当前 `source="loop"` 硬编码会让神兽的回忆/轨迹混入主记忆，`read` 检索时主 Agent 会读到神兽的中间产物（**污染**）。E38 依赖 E37 的 source 过滤（封存 = 按 source 冻结一段轨迹），故 E38 须在 E37 之后（或同批）。
> **去重边界**：不重复 phase-20（E27/B2/C7/C8）、phase-22（observability/rag/skillhub）、phase-23（缺口③）、phase-24（E30/E31/E32）、phase-25（E33/E34/E35/E36）已列/已修/已裁决项。本 Phase 三条为 beast/pet 专属记忆链路专属新发现。

---

## 1. 缺陷清单

### 1.1 E37 神兽「独立记忆命名空间」断裂

**现象**：beast-mode 规格要求神兽有「独立记忆命名空间」（`source=beast.<agent_id>`，与主 Agent 记忆隔离），但实现中 `BeastSession.remember` 是死代码（全仓库无生产调用），实际落记忆走 `LoopPlugin.remember` 且 `source="loop"` 硬编码 ⇒ 神兽轨迹混入主记忆。

**证据**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `doc/openspec/specs/beast-mode/spec.md:53-55` | 「独立命名空间」/「按 source 隔离」 | 规格明文要求 |
| `src/core/beast/session.py:76` | `def remember(self, content, trace_id="")` | 专属落记忆方法 |
| `src/core/beast/session.py:77` | docstring「source=beast.<agent_id> 落 L2」 | 声明独立命名空间 |
| `src/core/beast/session.py:88` | `source=self.beast.agent_id` | 唯一正确 source 写法，但方法全仓库无生产调用 |
| `src/core/beast/manager.py:70` | `result = await self._router.handoff(...)` | summon 只做 handoff，不落记忆 |
| `src/core/orchestration/router.py:49-56` | `async def handoff`：只 `loop.arun(task)` | 不传 session_id、不调用 remember |
| `src/core/loop/default.py:466` | `def remember(...)`：`session_id=""` 空串 | 落记忆不归组 |
| `src/core/loop/default.py:485` | `source="loop"` 硬编码 | 神兽轨迹以 "loop" 源混入主记忆 |
| `src/core/loop/default.py:114` | `LoopPlugin.__init__` 无 source 注入面 | 装配层无法指定 source |
| `src/core/orchestration/models.py:62` | `TaskHandoff` 无 session_id 字段 | handoff 无法传 session 归组 |
| `src/core/memory/protocol.py:49` | `read` 无 source 过滤参数 | 检索无法按 source 隔离 |
| `src/core/memory/store.py:90` | 存储/查询未按 source 过滤 | 同上 |

**根因**：beast 模式落地时（M7 神兽召唤）只实现了 `summon → handoff → 子 loop 执行` 的「召唤执行链」，而「独立记忆命名空间」这条规格承诺只写了 `BeastSession.remember` 方法骨架（含正确的 `source=agent_id` 写法），却从未把它接进落记忆路径 —— 子 loop 实际复用 `LoopPlugin.remember`，其 `source="loop"` 硬编码、`session_id` 空串，且 `handoff` 不传 session_id、`read` 不支持 source 过滤，导致「独立命名空间」整条链路四处断裂。

**后果**：神兽的回忆/轨迹以 `source="loop"` 混入主记忆，主 Agent 检索时会读到神兽的中间产物（**污染**）；beast-mode 的「独立命名空间」承诺在生产不可达。档位 **高**。

**登记源**：本 Phase review 新发现（beast-mode spec ↔ `beast/session.py` ↔ `loop/default.py` ↔ `orchestration/router.py` ↔ `memory/protocol.py` 对照）。

### 1.2 E38 神兽记忆「封存」无实现

**现象**：beast-mode 规格要求神兽支持「封存/召回」（把一段轨迹冻结为独立命名空间的持久记忆），但实现中仅 `models.py` 一行注释，无任何代码。

**证据**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `doc/openspec/specs/beast-mode/spec.md:88-89` | 「封存/召回」 | 规格明文要求 |
| `src/core/beast/models.py:20` | 仅注释「封存…」 | 无实现 |

**根因**：封存能力依赖 E37 的独立命名空间（按 source 冻结轨迹），而 E37 本身断裂，封存遂停在注释层。

**后果**：神兽无法把历史轨迹封存为独立持久记忆。档位 **中**（依赖 E37）。

**登记源**：本 Phase review 新发现。

### 1.3 E39 宠物「偏好追踪」断裂

**现象**：pet-mode 规格要求宠物追踪用户偏好（`source="user"` 落库，用于 surprise/偏好驱动），但实现中 `PetSession.observe` 是死代码（全仓库无生产调用），`_preferences` 仅 observe 写 ⇒ 恒空，`surprise` 恒 None。

**证据**：

| 位置 | 原文 | 问题 |
|---|---|---|
| `doc/openspec/specs/pet-mode/spec.md:74-76` | 偏好追踪 | 规格明文要求 |
| `doc/openspec/specs/pet-mode/spec.md:221-225` | surprise/偏好驱动 | 规格明文要求 |
| `src/core/pet/core/session.py:187` | `def observe(...)` | 专属偏好写入方法 |
| `src/core/pet/core/session.py:196` | `source="user"` | 唯一正确 source，但方法全仓库无生产调用 |
| `src/core/pet/core/session.py:201` | `_preferences` 仅 observe 写 | 恒空 |
| `src/core/pet/core/session.py:232` | `surprise` 依赖 `_preferences` | 恒 None |
| `src/core/pet/core/session.py:249` | `_notify_owner` 只通知 | 不落偏好 |
| `src/core/pet/core/session.py:146/149` | `wake` 不 observe | 唤醒不追踪偏好 |

**根因**：pet 模式落地时 `observe` 方法骨架（含 `source="user"`）写好但未接进交互路径，`wake`/交互后不调用 `observe`，`_preferences` 恒空。

**后果**：`source="user"` 从未落库，宠物无用户偏好记忆，`surprise` 恒 None。档位 **中**。

**登记源**：本 Phase review 新发现。

---

## 2. 修复方案

### 2.1 E37：装配层注入 source + read 加 source 过滤 + handoff 传 session_id + 唤醒 remember

**目标**：神兽轨迹以 `source=beast.<agent_id>` 独立落库，与主记忆隔离。

**方案**：
1. 唤醒 `BeastSession.remember`：在 beast 子 loop 的落记忆路径调用它（或让 `LoopPlugin` 支持注入 source，由装配层传 `source=beast.agent_id`）。
2. `LoopPlugin.__init__`（`default.py:114`）加 `source` 注入面（缺省 `"loop"` 保持向后兼容），`remember`（`default.py:485`）用注入的 source 替代硬编码 `"loop"`。
3. `TaskHandoff`（`orchestration/models.py:62`）加 `session_id` 字段；`router.handoff`（`router.py:49-56`）在子 loop 落记忆时传 session_id 归组。
4. `memory.read`（`protocol.py:49`）加 source 过滤参数；`store.py:90` 查询按 source 过滤。
5. 装配层 `_beast_loop` 注入 `source=beast.agent_id`（与 `BeastSession.remember` 的 source 一致）。

**红线**：不改 beast-mode spec（已声明）；不破坏主 loop 的 `"loop"` 缺省行为；source 过滤仅加参数、不改默认检索语义。

### 2.2 E38：实现封存/召回（依赖 E37）

**目标**：神兽支持把轨迹封存为独立持久记忆。

**方案**：
1. 在 E37 独立命名空间落地后，实现 seal（按 source 冻结一段轨迹）/ recall（召回封存记忆）。
2. 具体形状照 `beast-mode/spec.md:88-89`。

**红线**：E37 未落地前不动 E38（封存依赖 source 过滤）。

### 2.3 E39：唤醒 observe + wake 后 observe

**目标**：宠物偏好以 `source="user"` 落库，surprise/偏好驱动生效。

**方案**：
1. 在 `PetSession.wake`（`session.py:146/149`）及交互反馈路径调用 `observe`（`source="user"`）。
2. 确保 `_preferences` 有写入来源，`surprise`（`session.py:232`）有数据。

**红线**：不改 pet-mode spec；不扩大 `observe` 的语义。

---

## 3. 验收清单

- [x] ① 神兽轨迹落库 `source == "beast.<agent_id>"`（非 `"loop"`），主 Agent 检索不含神兽轨迹（source 过滤生效）
      —— 端到端 `tests/test_memory_namespace.py::test_production_summon_writes_beast_namespace_through_real_loop` /
      `::test_main_loop_context_excludes_sealed_beast_partition`。
- [x] ② `router.handoff` 传 session_id，子 loop 落记忆带 session_id 归组 —— `::test_handoff_forwards_session_id_to_sub_loop`。
- [x] ③ `memory.read` 支持 source 过滤，`store` 查询按 source 过滤 —— `::test_read_excludes_source_prefixes_but_default_is_unchanged` /
      `::test_excluded_entries_do_not_consume_budget_or_reinforce`（排除在排名与预算**之前**）。
- [x] ④ 封存/召回有生产路径 —— **判据订正**：封存 = 读取侧排除的**效果**（E37 落地，`::test_main_loop_context_excludes_sealed_beast_partition`）；
      召回 = `BeastManager.summon` 收尾 `session.recall()`（早已在位）；**未新造 seal/recall API**（规格无此条款）。
- [x] ⑤ 宠物 `_preferences` 非空，`surprise` 非恒 None，`source="user"` 落库
      —— `::test_production_pet_activation_observes_owner_and_enables_surprise` / `::test_pet_control_assign_observes_owner`；
      反例（不谎报）`::test_slash_activation_does_not_fabricate_preference` / `::test_cli_without_owner_text_does_not_observe`。
- [x] ⑥ 未改 beast-mode / pet-mode 规格（本 change 规格中性）—— `.openspec.yaml` 置 `schema` + `skip_specs: true`。
- [x] ⑦ 门禁四件套全绿：`ruff check`（All checks passed）/ `ruff format --check`（330 files already formatted）/
      `pyright`（**0 errors, 0 warnings, 0 informations**）/ `pytest`（**1288 passed**）。
- [x] ⑧ `openspec validate --all` 全绿（**30 passed, 0 failed**）。

---

## 4. 契约对齐

- **E37/E39 属既有契约的接线收尾**：`beast-mode` spec 已声明独立命名空间（`:53-55`）、`pet-mode` spec 已声明偏好追踪（`:74-76`）⇒ **无需 spec delta**，仅补实现与集成测试。
- **E38 属回归契约**：`beast-mode` spec `:88-89` 已声明封存/召回 ⇒ 无需 delta，仅补实现。
- 三条均**不触发 spec 变更**（规格已先行声明）。

---

## 5. 门禁与红线

- **红线**：E37 注入的 source 缺省值保持 `"loop"`（向后兼容）；`read` 的 source 过滤仅加参数、不改默认检索语义；E38 须在 E37 落地后做（封存依赖 source 过滤）。
- **红线**：不重复 phase-20（E27/B2/C7/C8）、phase-22（observability/rag/skillhub）、phase-23（缺口③）、phase-24（E30/E31/E32）、phase-25（E33/E34/E35/E36）已列/已修/已裁决项。
- **门禁**：提交前四件套全绿（`ruff check` / `ruff format --check` / `pyright` 0/0/0 / `pytest` 全绿）+ `openspec validate --all` 全绿；一个 Phase 一个 commit；更新 `README.md` §1 文档清单与 §2 Phase 总览表。

---

## 6. 收口（已执行：change `0110`／ADR-0103；三条同批修，规格中性）

**交付**：`doc/openspec/changes/archive/2026-10-05-0110-beast-pet-memory-wiring/`（**规格中性** `.openspec.yaml` 置
`schema: spec-driven` + `skip_specs: true`）—— `beast-mode` / `pet-mode` 两 spec **零改动**（本 change 是实现回归既有契约）。
**决策见 ADR-0103**（命名空间 = 写入侧 `source` 注入 + 读取侧来源排除；两条判据订正；两条已知局限）。

| 缺陷 | 落地 | 证据 |
|---|---|---|
| E37 | ① `DefaultLoop(source="loop")` 注入面（`remember` 用之，缺省逐字不变）；② `MemoryStore.read(..., *, exclude_source_prefixes=())` 在排名/预算**之前**排除；③ `DynamicAssembler` 同形参数 + 组合根为主 loop 装配器传 `("beast.",)`；④ `TaskHandoff.session_id` + `handoff` 转交；⑤ `BeastManager.summon` 传 `beast.agent_id`；⑥ `runtime._beast_loop` 注入 `source=beast.agent_id` | `tests/test_memory_namespace.py`（TC-NS-01…09；含生产端到端「神兽轨迹 `source`/`session_id` == `beast.qinglong`」与「主 loop 装配不含 `beast.*`、不误伤 `loop`」） |
| E38 | **判据订正**：封存 = E37 读取侧排除的**效果**（`source=beast.*` 不再被主 loop read 命中）；召回 = `summon` 收尾 `recall()`（在位）。**未新造 API** | `::test_main_loop_context_excludes_sealed_beast_partition`（封存效果）+ 既有 `test_beast_wiring` 回归（召回/自动回归） |
| E39 | `PetSession.observe_owner`（fail-soft）接在**主人原话**三入口：`activate_from_cli`（`rest`）／`activate_from_nl`／`PetControl.assign` | `::test_production_pet_activation_observes_owner_and_enables_surprise`（TC-NS-11）/ `::test_pet_control_assign_observes_owner`（TC-NS-12）+ 反例 TC-NS-13 |

**判据订正（2 条，见 §0 脚注与 ADR-0103）**：E38 封存是**效果**条款非 API 条款；E39 观察点是**主人原话入口**非 `wake()`。

**已知局限（明示，登记待议）**：① 主 loop 与神兽 loop **共享同一** `DynamicAssembler` 实例 ⇒ 神兽自身装配亦不命中 `beast.*`
（规格只要求主 loop 不命中）；② 压实摘要 `source` 恒为 `"compaction"`（`tests/test_memory.py:275` 已断言）⇒ 神兽分区被压实后的**摘要**
仍可被主 loop 读到 —— 按 source 命名空间隔离的残留缺口，修它要动该断言，属另一口径决定。

**未做（明示）**：**不**改 `BeastSession.remember`（会话级 API 保留；生产轨迹由 loop 写入，同口径不互相代笔）；
**不**改 `observe` 的异常面（`PET_PREFERENCE_WRITE_FAILED` 不变，供库层直接调用）；**不**在 `wake()` 内 observe；
**不**新造 seal/recall API；**不**新增 capability、**不**改任何 Requirement。

**门禁**：四件套全绿（`ruff check` / `ruff format --check` / `pyright` 0/0/0 / `pytest` **1288 passed**）
+ `openspec validate --all` **30 passed, 0 failed**；一个 Phase 一个 commit。
