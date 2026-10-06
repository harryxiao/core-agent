# 提案 — 结晶面门的判定面：真实 review + 真实运行时测试（change 0120 / phase-31 切片 2）

## 背景

`coding-plan/phase-31.md` 立账的 RSI 能力缺口 G1–G5。2026-10-06 用户裁决 §4.1 六点并**拆两次**：
切片 1（change `0119` / ADR-0112）已闭**数据面**（基准集/基线落盘 + 真实留出评分 + 口径版本）。
本 change 是**切片 2：判定面（G1 + G2）**——让 `Validator` 在**生产装配**下产出**真实判定**。

| # | 一手事实（切片 1 后复核，行号已订正） | 后果 |
|---|---|---|
| 1 | `validator.py:15-16` `_review_pass` 恒 `True`、`:19-20` `_no_tests` 返 `{}`，且是 `__init__`（`:28-35`）的**缺省** | 生产 review 判定恒真（**G1**） |
| 2 | `validator.py:40` `passed = review_ok and all(test_results.values())` —— 空 dict 的 `all()` 为 **真** | 生产运行时测试恒空、恒通过（**G2**） |
| 3 | `runtime.py:596` `validator=Validator()` **无参** | 生产**连注入点都没有**（phase-31 §4.1 第 1 点） |
| 4 | `engine.py:99-104` 引擎**确实消费** `gate.passed`（否则 `status="rejected"`） | 缺口**不在接线**在**产出的值恒为常量**（phase-31 §0 共同口径） |
| 5 | `ci_cd/pipeline.py:25` `GATE_COMMANDS` + `:47` `SubprocessGateExecutor` 已存在且有测试 | 运行时测试**不另造执行器**，按裁决 ② **派生**子集 |
| 6 | `evolution/author.py` 已建立「evolution 不 import LLM 抽象、prompt 文本属本域、模型调用由组合根注入」的接缝（ADR-0045 依赖方向） | review 的 LLM 面**复用同一接缝**（组合根的 `_llm_text`），不新造依赖边 |

**契约面现状（能力缺口，非缺陷）**：spec `:122` 「SHALL 对候选执行 review + 运行时测试，通过才
允许发布」**字面满足**（确实调用了 `Validator`、引擎确实按 `passed` 分支），但**实质落空**——
两个判据的生产者都是恒真桩 ⇒ `rejected` 分支**生产不可达**（G5），「不合格候选被挡在门外」这句
承诺不成立。按 phase-31 §4.1 裁决 ①，本 change **规格先行**（非 `skip_specs`）。

## 变更目标

**`evolution/spec.md` 「验证门」Requirement MODIFIED**（在切片 1 已加的口径版本条款之上，补**生产者**条款）：

1. **review 的生产者** —— review SHALL 由**结构化审查者**产出（候选 `kind`/`target_plugin`/`delta`
   的自洽性 → 通过/不通过），审查者 SHALL 由组合根注入；判定 SHALL **fail-closed**（不可解析 /
   空输出 / 调用失败 ⇒ **未通过**）。
2. **运行时测试的生产者** —— 测试 SHALL 取自门禁命令**单一真源** `GATE_COMMANDS` **按标记派生的
   子集**：结晶面 SHALL 跑 `lint` + `test`（**spec 明写哪几道、为什么**）；`typecheck` / `build`
   SHALL NOT 进结晶面。派生 SHALL NOT 复制命令字符串（不另立第二份门禁清单）；标记命中未注册门名
   ⇒ 派生**失败**（fail-closed）。任一门未通过 ⇒ 门未通过。
3. **未注入生产者 ⇒ 不得放行** —— 生产者未注入时 SHALL 判验证门**未通过**（缺省 `Validator()`
   恒通过正是本 Requirement 要消除的形态）。
4. **门的面（诚实）** —— 结晶面运行时测试跑的是**仓库级**回归门（与候选**内容无关**的基线健康
   检查）；候选**专属**产物的验证属**实施面**（`EvolutionExecutor` 的冻结门，spec `:334-337`），
   两门不同源、不互替。

## Non-goals

- **不动 `crystallize` 的 `accepted` 诚实语义**（ADR-0100 / spec `:266-268`，红线）。
- **不把 `Evaluator` 接进实施验证**（spec `:334-337` 明文，红线）。
- **不另立门禁清单**：结晶面子集**派生**自 `GATE_COMMANDS`，命令字符串只有一份（红线）。
- **不改观察期口径 / 不重算历史**（切片 1 的口径版本机制已覆盖；本 change 只**递增** `GATE_CALIBER`）。
- **不接真实 `runners` 执行器映射**（`frozen` 是否恒定属**独立 change**，ADR-0112 已知局限① 的
  reopen 条件）。
- **不新增 CLI 入口**、**不改 `SubprocessGateExecutor`**（其缺省 600s 超时与失败归一口径逐字不动）。
- **不给验证门加第三态**（`GateReport.passed` 仍是 bool）：「无法判定」按「未通过」处置（fail-closed），
  与留出评测的 `freeze` 不同 —— 门未过不会误伤「已发布」语义（不发布即无产物），无需新词。

## 判据与取舍（判据订正 3 条）

**(a) 判定面所在位置 = `run_cycle` 的 `validate` 阶段（冷路径），非操作面 `confirm`。**
phase-27 §7 记「同步四门阻塞 `_maintenance` ⇒ 改操作面显式驱动」是针对**实施面**（`EvolutionExecutor`）
的处置。结晶面**不可照搬**：`run_cycle` 的 `if not gate.passed: return rejected` 是 spec `:122`
「通过才允许发布」的**唯一**落点，把门挪到操作面会让该分支**在生产仍然不可达**（候选恒定
`pending`，拒绝改由 `crystallize` 报错表现）—— 那正是本 Phase 要消除的形态（G5 验收锚点）。
**代价如实登记**：冷路径在 loop 收尾**同步**跑子进程门禁（`pytest` 数十秒）+ 一次 review 调用；
只在「维护节拍（缺省 900s）到点**且**触发阈值命中**且**确有可归因证据」时发生，但确实会推迟
该轮收尾。**登记为已知局限 + reopen 条件**（冷路径异步化 = 独立 change），不假称无代价。

**(b) `Validator()` 缺省 = **不得放行**（fail-closed），与切片 1 的 `Evaluator()` 缺省同型。**
切片 1 把 `Evaluator()` 无参的语义从「恒 publish」改为「无法评测 ⇒ `frozen`」；本 change 对
`Validator()` 做同型处置：**未注入生产者 ⇒ 未通过**（`review` 文本据实写明「未注入」）。理由：
spec `:122` 的「**通过才**允许发布」在「无判据」时**不得**成立；留着 fail-open 缺省等于把 G1/G2
留在类里等下一个装配者踩。代价是既有依赖「缺省即通过」的用例须**改判**（同切片 1 先例，
逐处显式注入过门替身，**读数器仍是真门**）。

**(c) 运行时测试的**结果载体**保持 `dict[str, bool]`（不塞失败原因字符串）。**
`validate` 用 `all(test_results.values())` 判通过 —— 值若混入非空**字符串**（失败原因），
`all()` 会把它当真值 ⇒ **失败被读成通过**。故门名 → **bool**；失败原因不进门报告（人要看的是
「哪道门没过」，而 `GateReport.review` 承载 review 面文本）。「教训写回 L2/L3」（spec `:145-147`
场景）本 change **不做**（`run_cycle` 的 `rejected` 分支今日即不写记忆，属既有形态，不夹带）。

## 风险与对策

| 风险 | 对策 |
|---|---|
| **冷路径同步跑子进程门禁**（数十秒） | 如实登记已知局限（见判据 (a)）+ reopen 条件（冷路径异步化）；不改本 change 范围 |
| 缺省 fail-closed ⇒ 既有用例集体改判 | 与切片 1 同型处置：逐处**显式**注入过门替身；真门（`Validator`）语义不打折；改判处集中、可审 |
| 标记与 `GATE_COMMANDS` 漂移（少跑一门而无人知） | 派生时 **fail-closed**：标记命中未注册门名 ⇒ `CiCdError`；有测试钉住 |
| `all()` 语义被非 bool 值污染（失败读成通过） | 结果面钉死 `dict[str, bool]`（判据 (c)）+ 用例钉住「未过门 ⇒ `passed=False`」 |
| review 判定被模型输出「糊弄」成通过 | 词表严格（首行以 `PASS`/`通过` 起首才通过），其余**一律不通过**；不可解析 ⇒ 不通过 |
| 旧口径候选（切片 1 的桩口径）被投放 | **递增 `GATE_CALIBER` 1→2**：旧候选投放时 `GATE_CALIBER_STALE`（切片 1 机制，本 change 只是把口径真的改了） |
| LLM 未配置 ⇒ 每个候选都未过门 | **有意**：无审查判据即不得发布（fail-closed）；组合根按既有约定注入模型调用 |

## 兼容性

- `Validator(review=…, tests=…)` 的**调用形态逐字不变**（两个 callable 的签名与语义不变）；
  变的只是**不注入时**的结果（通过 → 未通过）—— 这是本 change 的目的。
- `GateReport` / `EvalReport` / `EvolutionOutcome` 数据模型**零字段变更**（只递增 `GATE_CALIBER`）。
- `GATE_COMMANDS` / `SubprocessGateExecutor` / 门禁工具面 `tools.gate_run` **逐字不动**（只**新增**
  标记常量与派生函数）。
