# 提案 — 难易度感知的同波次调度策略（change 0123 / phase-29 change C：E50）

## 背景

`coding-plan/phase-29.md` 立账的编排缺口 **E50**（用户需求①「主 Agent **依据任务难易度动态决策串行
还是并行**」）。phase-29 §6 已裁决把该 Phase 拆为 A/B/C/D 四个 change，本 change 是 **C：策略层**
（规格最重；A 事件回流 = `0121`，B HTTP 面 + Web 任务区 = `0122`，D CLI 只读详情另议）。

| # | 一手事实（2026-10-06 复核，行号已核实） | 后果 |
|---|---|---|
| 1 | `models.py:31-39` `Subtask` 只有 `id/goal/acceptance/depends_on/priority`，**无 `difficulty`** | 难易度**无载体** ⇒ 「按难易度决策」无输入（E50 根因） |
| 2 | `scheduler.py:214-227` 波次内一律 `asyncio.gather` + `Semaphore(self._max_concurrency)` | 同波次**恒并发**，无任何决策点（决策点 = 零，非「有但没生效」） |
| 3 | `decomposer.py:85-95` `_build_waves` 层号 = 1 + 依赖层号最大值 | 波次划分依据是**依赖拓扑**（硬约束），与难易度无关 —— 本 change **不动**此层 |
| 4 | `runtime.py:866-876` 装配 `TaskScheduler` **不传 `max_concurrency`** | 上限恒取构造缺省 `4`（`scheduler.py:107`）⇒ 判据「可注入但唯一调用点不传参」（与账本 E15 同型） |
| 5 | `configuration/manager.py:198-205` `loop.history_turns` 的 ConfigSpec + 「独立访问器」先例（change `0115`） | 新增编排配置键有现成范式：ConfigSpec 三面 + 独立访问器（**不动** `loop_limits()` arity） |
| 6 | `models.py:82-123` `plan_to_dict` / `plan_from_dict` 逐字段搬运 | 新增字段**须同改两处**，否则检查点跨进程往返**静默丢字段**（`scheduler.py:851` 即经此持久化） |

**契约面现状（能力缺口，非缺陷）**：`orchestration` spec 有「并行扇出」（`:115`）与「优先级调度」
（`:156`）两条 Requirement，但**无任何难易度条款**，且 `Subtask` 字段集在 spec 中从未声明为闭合。按本仓
SDD 惯例 **规格先行**（**非** `skip_specs`）。

## 变更目标

1. **`orchestration/spec.md` ADDED「难易度感知的调度策略」**（新能力，先例 change `0028`）：`difficulty`
   三档字段（缺省 `medium`，集合外归一）+ 可配置同波次调度策略 + 并发上限由组合根注入 + 5 个 Scenario。
2. **`orchestration/spec.md` MODIFIED「子任务拆解」**：仅订正 `LLM 拆解产出子任务 DAG` 场景的字段枚举
   （`id/goal/acceptance/depends_on` → 加 `difficulty`），使 spec 与模型输出契约一致（Requirement 正文
   逐字保留）。
3. **`configuration/spec.md` ADDED「编排调度配置」**：`orchestration.difficulty_policy`（默认 `off`）与
   `orchestration.max_concurrency`（默认 `4`）经 ConfigSpec 三面生成 + 校验期拒绝非法取值。
4. 实现：`Subtask.difficulty` + 调度策略落点（`scheduler._wave_limit`）+ 难易度自报（`planner`）+
   配置键与访问器 + `runtime` 组合根注入。

## 缺省语义（用户裁决，2026-10-06）

phase-29 §4① 原文为「缺省 = 全串行」。落地前复核发现该字面与**既有能力**冲突：spec「并行扇出」
（`:115`）与 `tests/test_orchestration.py:253-273`（`tracker.peak == 2`，**不传策略参数**）都断言
**缺省即并发** ⇒ 取字面将**改判既有规格与用例**、并把 `TaskScheduler` 的生产默认行为由并发改为串行。

**用户裁决：取「缺省沿用拓扑并发」**（§4① 的**用意** —— 「不得把不可靠信号直连并发开关」—— 保留，
字面订正）：

- `difficulty_policy = off`（缺省）⇒ 同波次按依赖拓扑**并发**（上限 `max_concurrency`），与今天**逐字一致**；
- `difficulty_policy = difficulty` ⇒ 同波次**含 `hard`** 时该波次**串行**，否则维持并发。

即：难易度是**降级信号**（只在开启时把 hard 波次收窄为串行），**不**是并发的开关。

## Non-goals

- **不改波次划分**：`_build_waves` 的依赖拓扑仍是硬约束（事实 3），本 change 只在其**之下**加决策点。
- **不引入「模型自主判依赖」**（§4② 明确延后为后续演进项）——判据本期只有「依赖拓扑 + 难易度 + 并发上限」。
- **不改事件面**：不新增事件类型、不改 `wave_started` / `subtask_*` 载荷形状（change `0121` / `0122` 的
  消费面不回归）。
- **不动 CLI/TUI 与 Web 呈现**（phase-29 change D / 已闭的 change B）。
- **不动主 loop 多 `tool_call` 丢弃**（phase-29 §7 **E55**，须改 L3 协议，独立登记）。
- **不新增难度档位/阈值旋钮**：三档固定，只有「策略开关」与「并发上限」两个配置键（无「难易度阈值」
  之类的第二旋钮 —— 未请求的灵活性）。

## 判据与取舍

**(a) 难易度是「降级信号」而非「并发开关」**（见上节用户裁决）。取字面（缺省全串行）会以一条**不可靠
的模型自报信号**为理由**回收**已有的、由**硬约束**（依赖拓扑）保障的并发能力 —— 收益为负、且改判既有规格。

**(b) 决策粒度取「波次级」而非「子任务级」。** 波次内若把 `easy/medium` 与 `hard` 分成两组分别并发/串行，
会引入**组间时序**（先跑哪组？）与**部分并发**两套新语义，而收益不及复杂度；波次级规则（含 hard ⇒ 整波
串行）可用一条断言（并发峰值 = 1）钉死，且与 `_fan_out` 现有的「一个波次一个 Semaphore」结构同构。

**(c) 非法难易度**取值归一为 `medium` 而**非**抛错/丢弃子任务。`difficulty` 是模型输出的**弱信号**，其
非法值不该让整次拆解失败（对齐 `planner._parse` 既有的「非法项剔除 / `priority` 非整数取 0」口径）；
而**配置键**（`difficulty_policy` / `max_concurrency`）属**人工配置**，取值非法 ⇒ **校验期阻断启动**
（不静默强转 —— 对齐 `loop.*` 与 `permission.mode` 口径）。两者口径**有意不同**，理由是信号来源不同。

**(d) `max_concurrency` 由组合根注入**（事实 4）：本期必须接线，否则「并发上限」判据在生产**空转**
（构造缺省 4 恰好等于既有行为，掩盖未接线）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| 缺省行为被无意改变（并发 → 串行） | `off` 分支**逐字**走原路径（`_wave_limit` 返回 `max_concurrency`）；既有 `test_run_fanout_bounded_concurrency` / `test_run_priority_order` **不改动**即为守门 |
| 新字段跨检查点丢 | `plan_to_dict` / `plan_from_dict` **同改** + 往返用例（含**缺字段**的旧检查点 ⇒ 回落 `medium`，向后兼容） |
| 提示词改动使模型输出漂移 | `_parse` 对 `difficulty` **归一而非校验**（非法 ⇒ `medium`）；不改变既有字段解析口径 |
| 策略取值拼错静默 no-op | 配置面校验期拒绝（三面）；构造器**同口径**校验（对齐 `max_concurrency < 1` 先例，新错误码 `INVALID_DISPATCH_POLICY`） |
| 误把难度当并发开关的「自动并发」 | `difficulty` 策略**只**能收窄（hard ⇒ 串行），**不**提供任何「提高并发」的语义 |

## 兼容性

- `difficulty_policy` 缺省 `off` ⇒ **未配置的部署行为逐字不变**（`difficulty` 字段即使被拆解器填上也不
  参与决策）。
- `Subtask` 新字段有缺省值 ⇒ 全仓既有构造点（测试替身 / `_fallback` / 检查点反序列化）**零改动**。
- `plan_from_dict` 对**缺 `difficulty` 键**的旧检查点回落 `medium`（不抛、不丢子任务）。
- `TaskScheduler.__init__` 新增形参为 keyword-only 且有缺省 ⇒ 既有调用点零改动。
- 事件面 / CLI / Web / `tools.delegate` **零改动**。
