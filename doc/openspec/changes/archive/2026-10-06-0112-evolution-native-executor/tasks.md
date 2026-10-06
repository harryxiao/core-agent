# tasks — 进化引擎「原生执行器」EvolutionExecutor（change 0112 / phase-27 切片 S0）

> 形态订正（开工时一手核实）：原设计把筹备挂在 loop **冷路径**（`_cold_path` → `drain()`）上。
> 核实后**否决**该形态：① `_cold_path` 是**同步** `Callable[[], None]`，唯一调用点是
> `DefaultLoop._maintenance`（`loop/default.py:359-363`）⇒ 在智能体一轮收尾处同步跑四道门禁
> （单门超时上界 600s）等于阻塞热路径；② `evolve confirm` 是**一次性 CLI 进程**，跑完即退出，
> 冷路径永不命中 ⇒ 筹备**死路径**。改为**操作面显式驱动**（`evolve implement`），仍为
> **两阶段 prepare → 人工复核 → commit**（DS2 不打折），制品随**既有候选台账**落盘（不建第二库）。

## 1. 规格（先行，DS4）
- [x] 1.1 `specs/evolution/spec.md`：MODIFIED「架构级候选强制人工审批（HITL confirm gate）」
      —— **结局诚实** bullet 加「**未启用原生执行器时**」限定语（原条款由无条件改为缺省口径），
      7 场景全量重述 + 「带已批准审批单放行」场景明写返回值**逐字不变**
- [x] 1.2 同上：ADDED「架构级候选的原生实施（可选）」—— 缺省关门控 / 操作面显式驱动的两阶段
      （筹备落台账不落地 → 人工复核关 → 落地 `implemented`）/ 门禁冻结单一真源 / 范围守卫 +
      归因一致性 / 崩溃安全 + 漂移拒绝 / `crystallize` 返回值不变（9 场景）
- [x] 1.3 `specs/configuration/spec.md`：MODIFIED「功能开关（feature flag）」—— 补**第二条极性**
      （缺省关名单 + `is_enabled` 判据 + 两极性各由独立名单承载），10 场景全量重述 + 3 新场景
- [x] 1.4 `openspec validate 0112-evolution-native-executor` 通过

## 2. 测试（先写，红）
- [x] 2.1 新 `tests/test_evolution_executor.py`：**范围守卫**逐条拒绝（`tests/**`、`pyproject.toml`、
      `src/core/ci_cd/*`、`src/core/permission/*`、`src/core/evolution/*`、绝对路径 / `..` / 非
      `src/core` 的 `.py`）；**归因一致性**（路径 ≠ 归因约定 / 目标文件不存在 ⇒ 拒绝）
- [x] 2.2 同文件：`prepare` ⇒ 应用后**工作树还原**（读回原内容）、回退报告 `reverted` 含该效应且
      `undo_failed` 为空（`rollback` **不**删除效应记录 ⇒ 不写「零残留」）、制品落台账（补丁 + 原内容 + 门禁报告）
- [x] 2.3 同文件：门禁不过 ⇒ 抛出结构化失败 + 工作树还原 + **不落制品**
- [x] 2.4 同文件：`commit` 无制品 ⇒ 拒绝；审批单缺失 / 目标不符 / 操作标识不可区分
      （`evolution.publish` 的单子）⇒ `CONFIRM_REQUIRED` 且**不落地**
- [x] 2.5 同文件：目标文件漂移 ⇒ `IMPLEMENT_STALE` 且不落地；**无**漂移时落地 ⇒ 结局 `implemented`
      + 文件内容正确 + `rollback(trace_id)` 可还原
- [x] 2.6 新 `tests/test_evolution_author.py`：**路径约定守护** —— 全部 `INTERNAL_PLUGIN_IDS`
      经 `src/core/<点转斜杠>.py` 命中真实文件；提示词含归因目标与问题；假 LLM ⇒ 契约
- [x] 2.7 新 `tests/test_evolution_executor_wiring.py`：缺省 ⇒ `runtime.evolution_executor is None`
      **且无未知功能开关告警**；`features.evolution_executor=true` ⇒ 装配；`=false` ⇒ 不装配
- [x] 2.8 新 `tests/test_evolution_executor_cli.py`：`--dry-run` 走通（`capsys` 见 diff）；
      未启用 ⇒ **rc 0** + stderr 说明（沿本仓「能力被关闭」惯例，非错误；见 `_module_disabled`）；
      未筹备直接落地 ⇒ 非零退出
- [x] 2.9 `tests/test_feature_gating.py`：新增 `OPT_IN_MODULES` / `KNOWN_FEATURE_MODULES`
      派生断言（`== GATABLE_MODULES + OPT_IN_MODULES`），**不动** `:84` 现有逐元素断言
- [x] 2.10 `tests/test_evolution.py`：**零改动** —— R4 由既有用例承担（`crystallize` 恒 `accepted`；
      本切片**未**动 `engine.py`）
- [x] 2.11 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `evolution/models.py`：`ImplementationRecord` dataclass（候选 id / 路径 / 原内容 /
      补丁内容 / 各门结论 / 已落地标记）+ `EvolutionOutcome.status` 词表 **+1** `implemented`
- [x] 3.2 `evolution/errors.py`：`IMPLEMENT_REJECTED` + `IMPLEMENT_STALE` **+2**（未过门复用既有
      `GATE_REJECTED`、复核缺失复用既有 `CONFIRM_REQUIRED`）
- [x] 3.3 `evolution/pending.py`：`PendingItem.implementation` + `attach_implementation()` +
      `implementation_of()` + 落盘往返（`record()` **保留**既有制品，不静默抹掉）
- [x] 3.4 新 `evolution/author.py`：`PatchAuthor` Protocol + `patch_author_with(llm, read_source)`
      （照 `summarize_with` / `sop_writer_with` 惯用法）+ 归因约定路径解析
- [x] 3.5 新 `evolution/executor.py`：`PatchProposal` / `GateOutcome` Protocol（消费侧声明）/
      `_scope_violation` / `EvolutionExecutor.prepare|commit`（`finally` 回退 + 漂移校验 +
      可逆效应 + 台账制品）
- [x] 3.6 `runtime.py`：`OPT_IN_MODULES = ("evolution_executor",)` + 派生 `KNOWN_FEATURE_MODULES`
      （`GATABLE_MODULES` 逐字不动）；`is_enabled("evolution_executor")` 门控装配执行器
      （**复用**既有 `gate_executor`/`_run_gate`/`effect_tracker`/`_llm_text`/同一 `PendingQueue`）；
      `Runtime.evolution_executor` 字段 + 构造点
- [x] 3.7 `entry.py`：`_config_manager` 注入面改 `KNOWN_FEATURE_MODULES`；`evolve implement
      <candidate_id> [--approver] [--note] [--dry-run]`（解析器 + 分派 + handler）；`_sign_approval`
      增 `op`（`evolution.implement`，与 `evolution.publish` 可区分）；`_EVOLVE_USAGE` 补用法
- [x] 3.8 四门全绿（直连二进制，不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/01-architecture/adr.md`：ADR-0105 —— 自改代码的安全边界（缺省 fail-closed /
      两级名单 / 验证门独立性 + 范围守卫 / 操作面隔离 / HITL 两道关 / 世代语义 `implemented` /
      筹备回退为何不违反 `CORE-EVO-R3` / 与 P1·P2·P4 的关系）+ **形态订正留痕**（冷路径否决依据）
      + 已知局限（生产 `Validator`/`Evaluator` 仍恒通过桩、物理隔离未落地、无回退 CLI、
      门禁副产物不入 undo）
- [x] 4.2 `doc/03-interfaces/evolution-interface.md`：§3.2 台账形状 + §4 操作面 `evolve implement`
      + §5 词表 `implemented` + 错误码表 `IMPLEMENT_STALE`
- [x] 4.3 `doc/03-interfaces/configuration-interface.md` + `doc/02-modules/configuration.md`：
      两谓词用途栏与装配裁剪契约补「缺省关名单」口径
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-EVO-* / TC-CONF-* 新增行（带锚点测试名）

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{evolution,configuration}/spec.md` + tick tasks
      + `shutil.move` 进 `archive/2026-10-06-0112-evolution-native-executor/`；**非** `skip_specs`
      ⇒ 不加 `.openspec.yaml`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`phase-27.md` §0 E40/E41 行 + §5.4 S0 行 + §6 收口 + DS1-a 落点订正留痕；
      `README.md` 同步）
- [x] 5.4 记忆更新 + 提交（`feat(evolution): 原生执行器 EvolutionExecutor（S0，change 0112）`，
      一个 Phase 一个 commit）
