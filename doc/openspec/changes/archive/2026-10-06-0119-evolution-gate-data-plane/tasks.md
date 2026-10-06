# tasks — 结晶面门的数据面（change 0119 / phase-31 切片 1：G4 + G3）

## 1. 规格（先行）
- [x] 1.1 `specs/evolution/spec.md`：MODIFIED「验证门」——**口径版本**（候选台账盖章 + 投放校验 +
      不重判历史 + 不谎报理由）
- [x] 1.2 同 delta：MODIFIED「留出评测」——留出分的**生产者**（基准样本经执行器真实执行）、
      候选↔基准**绑定**、**无法评测 ⇒ freeze**（fail-closed，不谎报 rollback）、基线分 = 绝对阈值
- [x] 1.3 同 delta：MODIFIED「评测基建」——**落盘**（`$CORE_STATE_DIR` 单文件、跨进程可读）+
      人工/运维注册 + **执行面注入**（数据面与执行面分离）+ 损坏降级**告警** + 无副作用声明
- [x] 1.4 `openspec validate 0119-evolution-gate-data-plane` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_evolution_gate_data.py`（新）：**基准集落盘跨进程可见** —— `BenchmarkRegistry(path=tmp)`
      注册基准 + 设基线 ⇒ 新实例（同 path）读回一致
- [x] 2.2 同文件：**损坏降级并告警** —— 损坏 JSON ⇒ 空表 + `warnings` 留痕 + 不抛
- [x] 2.3 同文件：**候选↔基准按 `plugin_id` 绑定** —— `benchmark_for_plugin` 命中/未命中
- [x] 2.4 同文件：**真实打分** —— `BenchmarkScorer`（注册执行器）⇒ 分数 = 逐样本真实执行结果的聚合
- [x] 2.5 同文件：**无法评测** —— 无绑定基准 / 无样本 / 无执行器 ⇒ `score_fn` 返 `None` ⇒
      `Evaluator` 给 `verdict="freeze"`、`passed=False`（**不**报 publish、**不**报 rollback）
- [x] 2.6 同文件：**无基线 ⇒ 无法评测** —— 有基准 + 有执行器但未注册基线 ⇒ `freeze`（不静默按 0.0 放行）
- [x] 2.7 同文件：**退化 ⇒ rollback 可达**（G5 锚点之一）—— 真实打分 0.3 < 基线 0.8 ⇒ `verdict="rollback"`
- [x] 2.8 同文件：**端到端 frozen**（G5 锚点之二）—— `run_cycle` 在**生产形状**装配（落盘 registry +
      `BenchmarkScorer` + 无 runner）下 ⇒ `EvolutionOutcome.status == "frozen"`（**不是** `rollback`）
- [x] 2.9 同文件：**端到端 rollback** —— 注册基准 + 基线 + 执行器（打分低于基线）⇒ `status == "rollback"`
- [x] 2.10 同文件：**口径版本** —— 旧口径候选（`caliber=0`，模拟落盘旧行）⇒ `crystallize` 结构化拒绝
      `GATE_CALIBER_STALE`、**不发布**；现口径候选正常投放（口径校验不阻断）
- [x] 2.11 同文件：**口径随台账落盘** —— `PendingQueue(path=…)` 记录候选后重开 ⇒ `caliber` 读回；
      落盘**缺该字段的旧行** ⇒ 解析为 0（旧口径）
- [x] 2.12 同文件：**执行器异常冒泡**（不吞成 0 分/不吞成通过）
- [x] 2.13 装配级：`build_runtime` 的 engine 注入 **落盘** benchmark registry + 非空 `score_fn`
      （生产形状守门：`runtime` 的 evaluator 不再是「无参裸桩」）
- [x] 2.14 回归改判：既有依赖「缺省即 publish」的用例（`test_evolution_pending.py` /
      `test_evolution.py` / `test_phase14.py` / `test_phase15.py` / `test_evolution_wiring.py` /
      `test_evolution_attribution.py`）改为**显式注入**能通过的打分器（读数器仍是真门）；改判理由写进 ADR

## 3. 实现
- [x] 3.1 `src/core/evolution/models.py`：`GATE_CALIBER = 1`（口径版本常量 + 递增规则写进 docstring）；
      `GenerationCandidate.caliber: int = GATE_CALIBER`；`Benchmark.plugin_id: str | None = None`；
      `EvolutionOutcome.status` 词表注释 +1 `frozen`
- [x] 3.2 `src/core/evolution/evaluator.py`：
      `BenchmarkRegistry(path: Path | None = None)`（载入 + 原子落盘 + 损坏 `warnings.warn` 降级）+
      `benchmark_for_plugin()` + `baseline_of() -> float | None`（`baseline_score` 保留）+
      `BenchmarkScorer(registry, *, quality=None, runners: Mapping[str, Callable[[dict], Any]] | None = None)`
      （返 `float | None`，`None` = 无法评测）+
      `Evaluator._held_out_score -> float | None`、`evaluate()` 三态（publish / rollback / **freeze**）
- [x] 3.3 `src/core/evolution/errors.py`：+`GATE_CALIBER_STALE`、+`EVAL_FROZEN`（结构化错误码）
- [x] 3.4 `src/core/evolution/engine.py`：`run_cycle` 结局按 verdict **诚实映射**（`rollback`→rollback /
      `freeze`→**frozen**）；`crystallize` 先校验 `candidate.caliber == GATE_CALIBER`（不符 ⇒
      `GATE_CALIBER_STALE`，理由 SHALL NOT 记为退化）+ `freeze` 报告 ⇒ `EVAL_FROZEN`（消息不含「退化」）
- [x] 3.5 `src/core/evolution/pending.py`：候选 dict 读/写带 `caliber`（**缺字段的旧行 ⇒ 0**）
- [x] 3.6 `src/core/runtime.py:589-590`：组合根建**落盘** `BenchmarkRegistry(path=_skill_state_path(
      "evolution-benchmarks.json"))` 并注入同一实例 + `score_fn=BenchmarkScorer(registry)`
      （runner 映射**空**，注释据实写明「生产未接执行器 ⇒ 无法评测 ⇒ freeze」，reopen 条件指向 ADR-0112）

## 4. 门禁（直连二进制，禁 `uv run`）
- [x] 4.1 `.venv/bin/ruff check src tests`
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright`（须 0/0/0）
- [x] 4.4 `.venv/bin/pytest -q`（基线 1477 passed ⇒ 改判 + 新增后应全绿）
- [x] 4.5 `openspec validate --all`（归档前后各一次，须 30 passed / 0 failed）

## 5. 归档
- [x] 5.1 手工合并 delta 进 canonical `doc/openspec/specs/evolution/spec.md`（逐文件对齐既有排版：
      `#### Scenario:` 后不留空行）
- [x] 5.2 目录 `shutil.move` 至 `doc/openspec/changes/archive/2026-10-06-0119-evolution-gate-data-plane/`

## 6. 文档与账本
- [x] 6.1 `doc/01-architecture/adr.md`：**ADR-0112**（决策 + 判据订正 3 条 + 已知局限：生产未接执行器
      ⇒ 恒 `frozen`／无 CLI 注册面／落盘无跨进程锁／`held_out_score` 在 freeze 报告记 0.0 无意义）+
      变更追踪表行
- [x] 6.2 `doc/03-interfaces/evolution-interface.md`（基准集/执行器注入面/口径版本/新错误码）；
      `doc/02-modules/evolution.md`（数据面与执行面分离）
- [x] 6.3 `doc/04-testing/test-cases.md` 增 TC 行（TC-EVGD-01..05）
- [x] 6.4 `coding-plan/phase-31.md`：状态 → 切片 1 已落地（change `0119` / ADR-0112）+ §1.4 与
      §0 表的「已落地/缺口」措辞同步 + §7 下一步改为「切片 2（G1+G2）」；`coding-plan/README.md`；
      `coding-plan/phase-27.md` ADR-0105 已知局限① 指针
- [x] 6.5 记忆：`coding-plan-leftover-walkthrough.md` + `MEMORY.md`

## 7. 提交
- [x] 7.1 单次提交：`feat(evolution,runtime): 结晶面门数据面落盘与真实留出评测（change 0119）`
- [x] 7.2 **不提交**：`config.yaml`、`.claude/settings*.json`（含 `settings.json`，D4 不动）、
      `coding-plan/phase-29.md`（**他人**未提交改动）、`coding-plan/phase-3-prompt.md`、
      `AI-SoftwareEngineer-4.md`、`coding-plan/phase-21-findings.md`、`src-tauri/Cargo.lock`、
      `node_modules/`、`frontend/dist/`
