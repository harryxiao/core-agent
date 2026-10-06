# 提案 — 进化引擎「原生执行器」EvolutionExecutor（change 0112 / phase-27 切片 S0）

## 1. 为什么（问题陈述）

**架构总纲与进化规格自相矛盾。**

`core_harness_architecture.md:150-153` 承诺「若 验证(提案) 通过 ⇒ **产出不可变世代**」「稳定技能 **提升为插件（记忆→代码）**」，`:158` 进一步把「记忆结晶成插件（提升）」列为闭环四段之首尾相接的一环。

而 `evolution/spec.md`「架构级候选强制人工审批（HITL confirm gate）」把这**同一个分支明文否掉**：

- `:202-204`「架构级候选获批并过门后 SHALL 以 `accepted` 结局登记（语义为「已批准、**待人工实施**」）——系统 SHALL NOT 在该分支报告 `published`（**无架构产物被发布、无世代被晋升**）」
- 实现侧对应 `engine.py:259-272` `_crystallize_plugin`：只写一条 L3 `MemoryEntry` 即返回 `EvolutionOutcome(status="accepted", candidate=candidate)`。

**后果**：系统**没有**「产出新一代产物」的能力，进化闭环的最后一跳靠**外部 Agent 读台账动手**（phase 19→26 全 Phase 均如此闭合）。这不是缺陷，而是规格**写定的边界**（phase-27 §2.1 已核实并改判）——故本变更**不是**缺陷修复，而是**RSI 能力扩展提案**，须先改规格。

**本变更做的是**：把 `CORE-EVO-R3`（「提案 SHALL 产出世代化的**不可变产物**，**过验证门前不进入运行**」）的落地形态补上，并同步订正 `evolution/spec.md:202-204` 与总纲的**口径冲突**——不是让规格变假，而是让规格**有条件地说出「实施」这件事**。

## 2. 对哪条 Requirement 增/改/删

| 需求编号 | 变更 | 说明 |
|---|---|---|
| `CORE-EVO-R3` | **增**（补齐落地形态） | 新增 Requirement「架构级候选的原生实施（可选）」：`accepted` 候选在**显式开启**时可被实施，实施产物 SHALL 经**冻结验证门** + **人工复核**后方落不可变世代（结局 `implemented`） |
| `CORE-EVO-R3`（口径订正） | **改** | 「架构级候选强制人工审批」Requirement 的**结局诚实** bullet 加限定语「**未启用原生执行器时**」——原条款由**无条件**改为**缺省口径**；`accepted` 的「已批准、未实施」语义**不回退** |
| `CORE-CFG-R3` | **改** | 「功能开关（feature flag）」Requirement 补**第二条极性**：除「缺省装配」名单外增设**缺省关**名单，使「缺省关闭（fail-closed）」的模块级开关成为规格内的合法形态 |

**关联但不改**：`CORE-EVO-R1`（四阶段闭环不变）、`CORE-EVO-R4`（留出评测与自动回滚不变）、`CORE-CICD-R1`（四道门禁不变，本变更只**消费**其单一真源 `GATE_COMMANDS`）、`CORE-PERM-R2`（人工审批流不变，复核关**复用**同一审批机制）。

## 3. 变更内容概览

1. **`EvolutionExecutor`（新）**：`prepare`（补丁生产者 → 范围守卫 → 应用 → 跑冻结门 → **回退**，制品落待复核队列）+ `commit`（人工复核通过 → 永久落地 → 落结局 `implemented`）。
2. **补丁生产者接缝（新）**：`patch_author_with(llm, read_source)`，照既有 `summarize_with(_llm_text)` / `sop_writer_with(_llm_text)` 适配器惯用法，**由组合根注入**。
3. **装配裁剪（缺省关）**：`features.evolution_executor`，**缺省 `false`（fail-closed）**；关闭时不装配执行器 ⇒ `crystallize` 的 `accepted` 结局**逐字**回到现状。
4. **引擎接缝**：`EvolutionEngine` 增可选 `enqueue` 回调，在 `_crystallize_plugin` 登记之后调用；`crystallize` **仍返回 `accepted`**。
5. **CLI 复核关**：`evolve implement <candidate_id>` 签发 `op="evolution.implement"` 的审批单（与 `confirm` 的 `evolution.publish` 区分）。
6. **词表 +1**：`EvolutionOutcome.status` 增 `implemented`。

## 4. Non-goals（明确不做）

- **不动既有 `Validator()` / `Evaluator()` 恒通过桩**（`runtime.py:564-574`）——它们是**另一件事**（生产验证门名副其实化），波及既有 `confirm`/`crystallize` 路径与观察期基线，不并入本切片。
- **不做物理文件系统隔离**（独立工作树 / 容器）——隔离只到「**冷路径任务面 + subprocess 门**」，`prepare` 在**本仓工作树**内应用后即回退。
- **不新增 CLI 回退入口**——`commit` 记录 `EffectTracker` undo（P2 合规），但不接「卸载上一代」的命令面。
- **不动 `GATABLE_MODULES`**（`pet` / `beast` / `evolution` 语义逐字不变）——缺省关走**另一份名单**。
- **不实现「批量/多文件补丁」**——本切片限**单文件**（诊断本就归因到单个插件）。
- **不改 `proposer` 的 `delta` 字段**——phase-27 §3.2 二次复核已把「补 `suggested_patch`/`acceptance`」改判为并入本切片且**由执行器作为消费者定义**（无消费者不新增键）。

## 5. 风险（须有答，见 ADR-0105）

| # | 风险 | 本变更的答 |
|---|---|---|
| R1 | **自我验证可被自我弱化**（执行器可改测试自证通过） | **范围守卫**拒绝触碰验证装置（`tests/**`、`conftest.py`、`pyproject.toml`、门禁真源 `ci_cd/pipeline.py`、规格 `doc/openspec/**`、`.github/**` 等）；门禁命令取自 `GATE_COMMANDS` **单一真源**，执行器**不得**自选 |
| R2 | **执行器无独立任务面** | 执行器由**冷路径**驱动（`_cold_path` → `drain()`），**不注册进任何工具面**；门禁经 **subprocess** 执行。物理隔离仍缺（列为已知局限） |
| R3 | **HITL 边界自相张力**（把实施复核也自动化 = 移除一道人工关） | **保留人工复核**（DS2）：`confirm` 批「做什么」，复核批「改得对不对」，两道关**都不打折**；缺审批单/目标不符一律 fail-closed |
| R4 | **世代语义悄悄回退**（`accepted` 又变回 `published`） | 新增**独立**词表项 `implemented`；`crystallize` 的返回值与文案**逐字不动**（既有用例保持绿） |
| R5 | 自改代码不可逆 | 两阶段 + `EffectTracker` 记 undo（P2）；**复核前不落地**；工作树在复核期间始终干净 |

## 6. 验收判据

见 `tasks.md`；规格场景见 `specs/`。**缺省不装配**（fail-closed）、**开启才实施**、**结局 `implemented` 经独立冻结门 + 人工复核**。
