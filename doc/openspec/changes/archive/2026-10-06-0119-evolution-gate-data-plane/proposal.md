# 提案 — 结晶面门的数据面：基准集落盘 + 真实打分 + 口径版本（change 0119 / phase-31 切片 1）

## 背景

`coding-plan/phase-31.md` 立账的 RSI 能力缺口 G1–G5：生产装配的 `Validator()` / `Evaluator()`
是**恒通过桩** ⇒ 结晶面四阶段中的第 3（验证门）、第 4（留出评测）**产出恒为常量**，
`rejected` / `rollback` 分支**生产不可达**（G5）。2026-10-06 用户裁决 §4.1 六点：
**① 立账为能力缺口**、**⑥ 拆两次（先 G4+G3 数据面，后 G1+G2 判定面）** —— 本 change 是**切片 1**。

| # | 一手事实 | 后果 |
|---|---|---|
| 1 | `evaluator.py:23-25` `BenchmarkRegistry.__init__` 只建两个**进程内 dict**（`_benchmarks` / `_baselines`），**无 `path`** | 基准集与基线**跨进程不可见** —— CLI 每条命令各起一份装配，注册的基准在下一进程里**蒸发**（与 ADR-0103 `MarketIndex` 同型：进程内状态必须落盘） |
| 2 | `evaluator.py:131-134` `_held_out_score` 在无 `score_fn` 时**返 `0.0`**；`:105` 判 `held_out < baseline - margin` = `0.0 < 0.0 - 0.0` **恒假** | 生产恒 `verdict="publish"` ⇒ 门禁全开（G3） |
| 3 | `evaluator.py:39-40` `baseline_score` 未注册基线 ⇒ **`0.0`** | 即便修好 G3，`held_out(≥0) < 0.0 - 0.0` **仍恒假** ⇒ **G4 是 G3 的前置**（phase-31 §0） |
| 4 | 全仓 `set_baseline` / `score_fn=` **零生产调用点**（仅测试与 Phase 15 用例） | 缺的是**数据面与生产者**，不是类；「可落地 / 工程化执行」（spec `:154-155`）落空 |
| 5 | `engine.py:98-107` 引擎**确实消费** `gate.passed` / `eval_report.verdict` | 缺口**不在接线**在**产出的值恒为常量**（phase-31 §0 共同口径） |
| 6 | `engine.py:105-107` 把 **任何** `verdict != "publish"` 一律记 `status="rollback"` | 一旦引入「无法评测」态，现状会把它**谎报为「退化」** —— 词表须随语义同步（先例 ADR-0100：`accepted`） |
| 7 | `runtime.py:589-590` `validator=Validator(), evaluator=Evaluator()`（**无参**） | 生产**连注入点都没有** —— 「装配选择」要成立须「有得选」，这里没有（phase-31 §4.1 第 1 点） |

**契约面现状（能力缺口，非缺陷）**：spec `:122-123`「SHALL 对候选执行 review + 运行时测试」字面满足
（确实调用了），但同 spec `:154-155`「SHALL 提供**可落地**的评测基建（基准集 + 评测运行器 + 指标对比
基线），支撑验证门与留出评测的**工程化执行**」**实质落空** —— 三处 Requirement 的产出恒为常量。
按 phase-31 §4.1 裁决 ①，本 Phase **立账为能力缺口**并**规格先行**（非 `skip_specs`）。

## 变更目标

**`evolution/spec.md` 三处 Requirement MODIFIED**（对齐 phase-31 §3 的「补生产者与数据面条款」）：

1. **留出评测** —— 真实打分与 fail-closed：留出分 SHALL 由**基准集样本经基准执行器真实执行**产出
   （SHALL NOT 以常量充当）；候选↔基准按 `plugin_id` **绑定**选取（SHALL NOT 回落「任意基准」或
   「自证基准」）；**无法评测**（无绑定基准 / 基准无样本 / 执行器未注册）⇒ `verdict="freeze"`，
   SHALL NOT 报 `publish`、SHALL NOT 谎报 `rollback`（无退化证据）。
2. **评测基建** —— 数据面落盘与执行面注入：基准集与基线 SHALL 落**`$CORE_STATE_DIR` 下单文件**
   （跨进程可读）；SHALL 支持**人工/运维注册**；基准样本的**执行器**（`task_type` → 可调用体）
   SHALL 由**组合根或运维注入**、SHALL NOT 随数据面落盘（数据面与执行面分离）；损坏/残缺 SHALL
   **降级为空表并告警**，SHALL NOT 阻断启动；基线 SHALL NOT 取自被评对象的自身历史分（自证）。
3. **验证门** —— **结晶面门口径版本**：候选台账条目 SHALL 记录其**提案时的口径版本**；投放
   （`crystallize`）时口径与现口径不符的候选 SHALL **拒绝**（fail-closed，须按现口径重新提案）；
   SHALL NOT 以新口径重判历史候选、SHALL NOT 一次性重算历史。

## Non-goals

- **不做 G1/G2（判定面）**：`Validator` 的缺省桩（`_review_pass` 恒真 / `_no_tests` 恒空）、
  结晶面跑哪几道门、`GATE_COMMANDS` 派生 —— **全属切片 2**（phase-31 §4.1 第 2 点）。本 change
  **逐字不动** `validator.py`。
- **不接实施验证路径**：spec `:273-274` 明文「留出评测**不**参与实施验证」——真实 `Evaluator`
  只服务**结晶面**。
- **不回退 `accepted` 诚实语义**（ADR-0100 / spec `:266-268`）；**不**让系统凭空产出世代。
- **不另立门禁清单**（spec `:273`）；本 change 根本不碰门禁命令面。
- **不做基准自动沉淀**：以被评对象自身历史分当基准 = **自证**（phase-31 §6 自我弱化红线）。
- **不加 CLI 注册入口**：运维注册面 = 落盘状态文件 + 库函数（`register` / `set_baseline`）。
  无 CLI 是**已知局限**（reopen 条件见 ADR-0112）。
- **不动观察期的采样口径与基线语义**（spec `:342-392` 逐字不动）：本次只加「口径版本」这一
  **候选台账维度**（见判据订正 (a)）。

## 判据与取舍（判据订正 3 条）

**(a) 「门加口径版本字段」的载体 = 候选台账条目（提案时盖章），判定点 = `crystallize`（投放前）。**
phase-31 §4.1 第 5 点原文为「门加「口径版本」字段，新口径只对新增候选生效，历史候选冻结在旧口径；
SHALL NOT 一次性重算历史（避免「历史候选集体未过门」污染 `reuse_count`）」。一手核实后**订正两点**：

- **判定点不在门内**：`crystallize` 读的是台账里**已记录**的 gate/eval 结论、**不重算**
  （`engine.py:150-160`）⇒ 「历史候选在新口径下集体未过门」在结构上**不会发生**（判定不重跑）。
- **真实危害方向相反**：会发生的是**「历史候选带着旧口径（桩）产出的**假通过**结论被投放」**
  —— 那才是必须挡住的（候选过了人工 `confirm` 即进 `crystallize`，而它的 gate/eval 是桩给的
  `passed=True` / `verdict="publish"`）。故口径守卫设在**「记录 → 投放」之间**：台账条目盖章 +
  `crystallize` 校验。**同一机制同时闭合两个方向**，故仍按裁决落地，仅订正载体与判定点。

**(b) 「绝对阈值起步」= `margin` 保持缺省 `0.0`，注册的基线分**就是**绝对阈值。**
phase-31 §3.3 提到「`margin` 取现行 spec `:350` 的绝对分差口径（默认值须裁决）」。裁决 ③ 取
「人工注册 + 绝对阈值」⇒ **不**给 `margin` 换默认值（换默认值会同时改观察期容差的语义面），
而是让 `baseline_score` 成为**唯一**阈值：`held_out < baseline` 即退化。`margin` 的构造参数
**逐字不动**（既有调用方零影响）。

**(c) 结局词表 +1 `frozen`（诚实化，非新增能力）。**
`run_cycle` 现把任何非 `publish` 一律记 `status="rollback"`（`engine.py:105-107`）—— 引入
`freeze` 后**必须**同步，否则「无法评测」被**谎报为「退化」**（`rollback` 语义是「已回滚」）。
按 ADR-0100 先例（`accepted` +1）加一个**诚实的结局词** `frozen`（未评测 ⇒ 不下发、不发布、
不溶解），**`rollback` / `rejected` 语义逐字不回退**。

## 风险与对策

| 风险 | 对策 |
|---|---|
| **生产未接执行器 ⇒ 候选恒 `frozen`**（不含糊：本 change 后产线**不再凭空发布**） | 这是裁决 ①（立账落地）的**有意结果**：fail-closed 优先于「看得出在动」。照实写进 spec + ADR 已知局限（第 1 条）+ 登记 reopen 条件（接真实执行器 = 另一 change）；`accepted`/`pending` 等既有语义不变 |
| 历史候选（旧口径）**带着假通过结论被投放** | 台账条目 `caliber` 盖章（`PendingItem`，随 JSON 落盘）；`crystallize` 口径不符 ⇒ **结构化拒绝** `GATE_CALIBER_STALE`（候选留 `pending`，重新提案即按现口径判定）；缺字段的**旧行**解析为口径 `0` ⇒ 一律拒绝（不 fail-open） |
| 静默降级：损坏的基准集 ⇒ 空表 ⇒ 全体 `frozen` | 降级**必告警**（对齐 `MarketIndex` / `plugin-registry` / `transcript` 先例）；不阻断启动 |
| 基准**自证**（自我弱化红线） | 数据面（样本/基线）落盘、执行面**由组合根/运维注入**；spec 明文 SHALL NOT 取被评对象自身历史分 |
| 落盘写-写并发 | 注册/设基线只发生在启动期与运维期；本 change **不做**跨进程锁（照实登记已知局限，不假称安全） |
| 执行器不可信（吃掉一切异常 ⇒ 恒 publish） | 执行器返回 `None` ⇒ **无法评测**（freeze）；抛异常 ⇒ 冒泡（不吞）；单样本异常不转成 0 分、不转成通过 |

## 兼容性

- `BenchmarkRegistry()` **无 path 仍纯内存**（既有测试与库层调用逐字不变）；`Evaluator()` 无参
  构造仍是「无 `score_fn`」——但语义从「恒 `publish`」变为「无法评测 ⇒ `frozen`」，**这是本
  change 的目的**，已在 spec 写明（凡是依赖「缺省即发布」的用例都须改判）。
- `PendingItem` 新字段 `caliber` 缺省 = 现口径（内存构造逐字不变）；仅**落盘旧行**（无该字段）
  解析为 `0` ⇒ 拒绝。
- `EvalReport.verdict` 词表**不动**（`freeze` 早已在字面量内，此前从未产出）。
