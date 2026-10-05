# Phase 27：进化引擎「原生执行器」—— RSI 能力扩展**提案**（非缺陷账本）

> **改判定性（2026-10-06 复核）**：本文件初稿以「缺陷账本」形态登记 E40/E41/E42/E43，并计划以 `skip_specs`（规格中性）实施。
> 一手复核后**改判**：这四条**不是缺陷**，其中 E40/E41 触及的是进化规格**明文写定的边界**（`accepted` = 「已批准、待人工实施」），
> E42 的「门禁工具缺位」**不成立**（执行器早已存在），E43 只剩一半。
> 因此本 Phase 的定性由「原生执行器缺陷修复」改为「**RSI 能力扩展提案**」：须**用户裁决 → 规格先行 → ADR** 之后才能拆 change，**不得**以缺陷修复名义静默实施。

## 0. 结论总览

| 编号 | 初稿断言 | 复核判定 | 档位（初稿→复核） |
|---|---|---|---|
| E40 | 无原生执行器 ⇒ 闭环断头 | **非缺陷**：规格明文把架构级分支定为「已批准、待人工实施」 | 高 → **已裁决：允许，缺省关闭**（DS1，见 §5.1） |
| E41 | 执行器与 loop 无接线 | **依附 E40**：无执行器自然无接线；非独立缺陷 | 高 → **依附**（随 E40 一道开工） |
| E42 | 门禁工具缺位 | **判据不实**：执行器已存在，缺的是**工具面**；且提案的「白名单免审批」= E34 同类声明不实 | 高 → 中 → ✅ **已闭**（change `0111` / ADR-0104：`tools.gate_run`） |
| E43 | proposer delta 信息量不足 | **部分不实**：`module_id` 已由 `target_plugin` 承载；余 `suggested_patch`/`acceptance` | 中 → 低 |

> **共同口径**：四条共同指向一件**真问题**——`core_harness_architecture.md:150-151/158` 承诺「验证通过 ⇒ 产出不可变世代」「记忆结晶成插件」，
> 而 `evolution/spec.md:203/215` 把这个分支**明文否掉**（「SHALL NOT 在该分支报告 `published`」「无世代被晋升」「已批准、**待人工实施**」）。
> **架构总纲与进化规格自相矛盾**。修哪一头（改规格让系统自实施 / 改总纲承认人工实施）是**产品方向裁决**，不是缺陷修复。
> **去重边界**：不复述 phase-21/24 的归因接线与 plugin 维度结论；不重复 phase-19 §5 的 E31（已裁决不纳入，其**重开条件正以「待人工实施」为前提**）。

---

## 1. 一手核实（逐条对照原始码，2026-10-06）

| 初稿断言 | 核实结果 | 判定 |
|---|---|---|
| `evolution/` 14 文件无 `executor.py` | ✅ 14 个 `.py`，确无 | 属实 |
| `engine.py:153` `crystallize` / `:259` `_crystallize_plugin` | ✅ 行号逐字对上 | 属实 |
| `_crystallize_plugin` 只回写 `status="accepted"` | ✅ `engine.py:271-272` + 注释「架构级候选只「批准登记」，不产出任何可发布产物 ⇒ 不谎报 published」 | 属实 |
| `runtime.py` 无 executor 装配 | ✅ `:552` 引擎 / `:564` worker / `:586` 主 loop，无桥接面 | 属实（但见 §2） |
| `entry.py:1145`「批准已登记，但无产物落地（待人工实施）」 | ✅ 逐字 | 属实 |
| `code_run`「不可逆高风险需审批」 | ✅ `builtin.py:190` `coeffects=["process:spawn","filesystem:write"]` + `reversible=False` ⇒ `planner._is_irreversible`（`:250-256`）判真 ⇒ `permission/guard.py:61-65` 非 auto-approve 档落 `confirm` | 属实 |
| proposer delta 仅 `{issue, schema}` | ⚠️ 实为 `delta={"issue": diagnosis.issue}`（`proposer.py:38`），**无 `schema` 键** | **订正** |
| E43「无 `module_id`（改哪个模块）」 | ⚠️ `GenerationCandidate.target_plugin`（`models.py:53`）**即模块身份**，且为独立字段（非 delta） | **订正** |

---

## 2. 两条硬伤（为何不能当作缺陷修）

### 2.1 E40 是规格明文的边界，不是断头路

- `evolution/spec.md:195`「**显式**人工 `confirm()`——系统 SHALL NOT 提供低风险自动结晶」
- `evolution/spec.md:203`「系统 SHALL NOT 在该分支报告 `published`（**无架构产物被发布、无世代被晋升**）」
- `evolution/spec.md:215`「结晶结局为 `accepted`（**已批准、待人工实施**）」

且 **ADR-0100（change `0107`，2026-10-05）恰以这句为前提**：`phase-19.md:115` 记 E31「不纳入」的重开条件为
「有新一代 `Plugin` 生产者，**而 change `0102` 把架构级结晶裁决为 `accepted` 待人工实施**」。
E40 要做的正是搬掉该前提 ⇒ 须同步复核 E31 裁决。

> 现下的「人工实施」并非无人执行：**外部 Agent（claude code）读台账动手**，phase 19→26 全 Phase 均如此闭合。这是既定分工，非断头。

### 2.2 「规格中性 / `skip_specs`」不成立

实施原生执行器 = 架构产物落地 + 世代晋升 ⇒ 与 `:203/215` 直接冲突。宣称「不改 spec」是**规格虚报**，
违反仓规「规格先行：实现偏离规格时先改规格再改代码」。E33/E37 的「规格中性」成立是因为规格**早已写明**该行为；此处规格写的是**相反**行为。

---

## 3. 两条判据订正

### 3.1 E42：门禁执行器早已存在，缺的是「工具面」

| 已有件 | 位置 |
|---|---|
| 四门命令单一真源 | `ci_cd/pipeline.py:25` `GATE_COMMANDS`（lint/typecheck/test/build） |
| 生产门禁执行器 | `ci_cd/pipeline.py:47` `SubprocessGateExecutor`（stdlib subprocess、不经 shell、失败归一）＋ `:90` `build_gate_executor`（ADR-0086 / change `0091`） |
| 结构化返回形状 | `evolution/models.py:63` `GateReport(passed, review, test_results)`（`Validator` 已产出，`validator.py:37-42`） |

**另起一套 `gate_run` 会造出第二个门禁真源** —— 正是 change `0105` 删 `_published`、`0103` 收窄 `replay` 时反复钉的「双真源」反模式（仓规 §10 DRY 同旨）。

**且「白名单命令 ⇒ 只读可逆、免审批」与 E34 同类**：跑 `pytest` = 执行仓库**任意**代码（本仓测试即任意 Python）并写 `.pytest_cache`/`__pycache__`；
白名单的是**命令名**而非**被执行的代码**。声明「只读可逆、不进确认门」即 change `0108`（E34）刚修掉的「声明不实」。

### 3.2 E43：只剩 `suggested_patch` / `acceptance`

`module_id` 已由 `target_plugin` 承载，**不重复加**。真缺：候选 patch 建议、验收判据（`risk_level` 亦已有，`models.py:57`）。

> **二次复核（2026-10-06，开工 S2 前）—— S2 改判「不纳入」**（一手三条）：
> ① **无消费者＝空转**：`delta` 现仅被 `engine._crystallize_skill`（`engine.py:250-252`）读 `issue` 与 `schema` 两键；
> 新增键**没有任何读取方** ⇒ 与 phase-19 §5 E31「不给出空转生命周期」同型。
> ② `suggested_patch` **无规格依据、无生产者**：`Proposer` 是 `DiagnosisReport`（`target_plugin`/`issue`/`evidence`/`confidence`）的纯函数，无 patch 建议来源。
> ③ **真消费方是 S0**：patch 建议与验收判据是 `EvolutionExecutor` 的输入 ⇒ 并入 S0 一并定字段**与其消费者**。
> 连带订正：`delta["schema"]` 是**读而不写**的既有键（`proposer.py:38` 只写 `issue`），`evolution/spec.md:38-47`
> 「生成带验收标准的单元」的落地口径随 S0 定。
---

## 4. RSI 特有风险（初稿未覆盖，开工前须有答）

| # | 风险 | 说明 |
|---|---|---|
| R1 | **自我验证可被自我弱化** | 验证门跑的是**被测代码自己的 pytest** ⇒ 执行器可改测试自证通过（reward hacking）。与 P4「进化必经验证门 + 不可变世代」相冲 ⇒ 门必须**独立于被改产物**（冻结的四门 + 独立执行环境），不得由执行器自选门禁命令。 |
| R2 | **红线 3 无落地机制** | 「executor 走独立任务面」现无实体（只有 `runtime.py:715` `_delegate` + `orchestration/scheduler.py:87` `TaskScheduler`）。红线写了也拦不住 ⇒ 须给**具体**隔离机制（独立 TaskScheduler / 专用 loop 实例）。 |
| R3 | **红线 1 自相张力** | 红线 1 称「不把人工审核自动化」，却把 `confirm` 之后的**实施复核**也全自动 ⇒ 实际移除一道人工关。两句须二选一并写明。 |
| R4 | **世代语义回退风险** | change `0102` 刚把 `published` → `accepted` 诚实化（**不谎报发布**）。若要新增「已实施」结局，须新增词表项并同步订正规格，**不得**悄悄改回 `published`。 |

---

## 5. 提案（DS1 已获准，须按此序）

### 5.1 裁决（2026-10-06 已定）

| 编号 | 裁决问题 | **裁决** |
|---|---|---|
| DS1 | `accept` 之后是否允许**自动实施核心代码**？ | **允许**，但落为**可配置开关**：**缺省 `false`（fail-closed）**，显式开启即「自动实施进化」。与 `permission.mode` 缺省 `interactive`（`manager.py:405-406`）、`sandbox.host_allowlist` 缺省空（fail-closed）同取向。 |
| DS1-a | 开关**形态** | **装配裁剪**：关 ⇒ 不装配 `EvolutionExecutor` ⇒ `crystallize` accepted 后无 `enqueue` ⇒ 逐字回到现状。落点 `features.evolution_executor`，**须同步加进 `runtime.GATABLE_MODULES`**（`runtime.py:120`）—— 否则触发 E20① 未知功能开关告警（`manager.py:351-363`）。**不采用**「executor 常驻 + 二级开关」形态：change `0067` 规格明文「feature flag SHALL ONLY 作用于**模块装配**，SHALL NOT 改变模块**自身**的二级启用开关」。 |
| DS2 | 实施结果的**复核关** | **保留人工复核**（保守）。与 `confirm` 分工：`confirm` 批「做什么」，复核批「改得对不对」；执行器产出的 patch 落 `implemented` 前须人工过目。 |
| DS3 | 验证门**独立性** | **冻结**（不可协商，R1）：只允许跑 `GATE_COMMANDS` 单一真源、独立执行环境、禁止执行器自选门禁命令。 |
| DS4 | 是否修改 `:203/215`？ | **必改**。门控能力**本身**即规格变更 —— 先例 change `0067`（feature-flag-gating）：**默认开也照样**写 `configuration/spec.md` MODIFIED + 4 Scenario，**非** `skip_specs`。「缺省不走到那段代码」不构成豁免。 |

### 5.2 规格先行（delta 草案）

- `evolution/spec.md` **MODIFY**「结晶为技能/SOP」HITL 段：给 `:203` 加**限定语** —— 「**未启用原生执行器时**，系统 SHALL NOT 在该分支报告 `published`（无架构产物被发布、无世代被晋升）」；`:215` 的 `accepted` 保留为「已批准、**未实施**」。
- `evolution/spec.md` **ADDED** 新 Requirement「架构级候选的原生实施（可选）」：明写「**仅当** `features.evolution_executor` 开启时，`accepted` 候选 SHALL 由 `EvolutionExecutor` 实施，实施结局 SHALL 经**独立验证门**（冻结 `GATE_COMMANDS`）**＋**人工复核（DS2）后落不可变世代」；Scenario：①开启 ⇒ 实施并落 `implemented` / ②关闭 ⇒ 逐字回到现状（不实施）/ ③验证门不过 ⇒ `dissolve` 回退。
- `configuration/spec.md` **MODIFY**「功能开关」：门控名单（单一真源）**＋ `evolution_executor`**（对齐 change `0067` 的名单条款）。
- `EvolutionOutcome.status` 词表 **+1**（`implemented`）；change `0102` 的 `accepted` 诚实语义**不回退**（R4）。
- 连带：`phase-19.md` E31 重开条件复核（其前提「待人工实施」被限定为**缺省口径**）。

### 5.3 ADR（DS1 已通过 ⇒ 拟 ADR-0104）

自改代码的安全边界：不可变世代冻结 / 快照 + 时间旅行回退 / 验证门独立性（R1）/ 执行隔离机制（R2）/ HITL 边界重述（R3）/ **为何此处缺省 fail-closed**（DS1）；
并说明与 P1「无特权核心」、P4「验证门 + 不可变世代」的关系。

### 5.4 落地切片

| 切片 | 内容 | 规格中性？ | 判据 |
|---|---|---|---|
| **S0（E40+E41 主体）** | 新增 `evolution/executor.py` `EvolutionExecutor` + `runtime` 装配受 `not is_disabled("evolution_executor")` 裁剪 + `crystallize` accepted 分支 `enqueue` | ❌ **须先 §5.2 规格 + §5.3 ADR** | 缺省不装配（DS1）；开启才实施；结局 `implemented` 经独立门 + 人工复核（DS2/DS3） |
| S1 ✅ **已闭**（change `0111` / ADR-0104） | 把既有门禁执行器暴露为**工具面**（不新写 `gate_run` 执行器）：`tools.gate_run`，执行器经组合根**注入** | ❌ **非中性**（**订正**，见下） | 复用单一真源 `GATE_COMMANDS`（schema 枚举由其生成，用例断言逐字一致）；coeffects **诚实声明** `["process:spawn","filesystem:write"]` + 不可逆 ⇒ **照旧过确认门**；结构化返回 `{gate, passed, reason}`；1274→**1297 passed**；`tool-use` spec **+1 Requirement**（4 场景） |
| S2 ❌ **改判不纳入**（并入 S0） | ~~`proposer` delta 补 `suggested_patch` / `acceptance`~~ | — | 见 §3.2 二次复核三条（无消费者＝空转 / 无规格依据无生产者 / 真消费方是 S0） |

> **S1 判据订正（2026-10-06，开工时一手核实）**：原记「✅ 中性」**不成立** —— 「中性」成立于**需求已在位**
> （change `0108` 的插件安装三工具由更早的 change `0028` 写入 `tool-use` 需求），而 `tools.gate_run` 是
> **全新工具、无任何在位的需求** ⇒ 新工具即新 Requirement，先例 change `0028`。故 S1 走 `tool-use/spec.md`
> **ADDED** 而非 `skip_specs`（`openspec validate` 通过；spec 文件项数不变，仍 30）。

> **顺序**：S0 走完整 SDD（规格先行 → ADR → 测试先行 → 实现）；S1 属「工具面补齐」，**不触碰** §2 的规格边界
> （只新增 `tool-use` 需求），**已独立先做**（S1 也是 S0 的前置：执行器需要能结构化跑门禁）。S0 落地后 S1 加壳进执行器。
> S2 已改判并入 S0（§3.2 二次复核）。

---

## 6. 收口

- **当前状态**：🚧 **S1 已闭，S0 待开工** —— DS1 通过（允许自动实施、**缺省 false 可开启**、**装配裁剪**形态），DS4 通过（规格必改）。前置：§5.2 规格先行 → §5.3 ADR-0104 → 才能开 S0。
- **S1 ✅ 已闭**（change `0111` / ADR-0104，2026-10-06）：`tools.gate_run` 工具面落地，1297 passed，`tool-use` spec +1 Requirement。**S2 ❌ 改判不纳入**（并入 S0，理由见 §3.2 二次复核）。
- **裁决留痕**：DS1/DS1-a/DS2/DS3/DS4 见 §5.1；形态否决依据 = change `0067` 规格原文（feature flag 只作用于模块装配）。
- **验收见**：§5.4（S0/S1/S2 判据）/ §4（红线前置）。
- **复核留痕**：改判依据见 §1；订正 4 条（E42 判据、E43 判据、delta 无 `schema`、`module_id` 已有）。
