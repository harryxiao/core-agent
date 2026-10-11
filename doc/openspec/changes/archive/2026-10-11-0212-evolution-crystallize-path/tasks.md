# Tasks 0212 — 结晶通路：真 runner 注入 + 基准人工注册操作面

## 1. 规格（spec-first）

- [ ] `specs/evolution/spec.md`：**MODIFIED**「评测基建」（全量替换；narrative 补「执行面语义」/
      「执行面门控」/「注册操作面」三 bullets ＋ **ADD** Scenario ×3；既有 5 bullets 与 6 Scenarios
      **逐字保留**）
- [ ] ADR-0202 +「变更追踪」表行
- [ ] 其余 `evolution` Requirement **逐字保留**

## 2. 测试先行（红）

- [ ] 新 `tests/test_benchmark_runner.py`：
  - 门控关闭（缺省）⇒ `build_runtime` 产出的 `BenchmarkScorer` **无** runner ⇒ 注册了基准+基线
    的候选仍 `freeze`（**逐字锚**）
  - 门控开启 + 桩 provider ⇒ runner 被调、`score` 进 `EvalReport.held_out_score`、`verdict` 非 freeze
  - runner 会话隔离（`session_id="bench"`）、失败 ⇒ `None`、异常冒泡
- [ ] 新 CLI 用例（同文件或 `tests/test_evolution_*_cli.py` 风格）：`evolve benchmark register` /
      `set-baseline` / `list` 落盘往返、跨进程可读、`--plugin-id` 缺失报错
- [ ] **反证**：摘门控（恒注入）⇒ 旗关锚红；摘 `runners=` 传参 ⇒ 旗开锚红

## 3. 实现（绿）

- [ ] `runtime.py`：`OPT_IN_MODULES += ("evolution_benchmark_runner",)`
- [ ] `runtime.py`：`_run_coro`（模块级）+ `_bench_runner`（闭包引 `general_agent.loop`、晚绑定）
- [ ] `runtime.py:837`：`BenchmarkScorer(benchmarks, runners=runners)`（`runners` 由门控决定）
- [ ] `entry.py`：`_add_evolve_parser` 加嵌套 `benchmark {register|set-baseline|list}`；
      `_evolve` 分发 + `_benchmark_registry()` + 三个 handler；`_EVOLVE_USAGE` 更新

## 4. 门禁与收口

- [ ] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [ ] **反证**：见 §2 末
- [ ] `openspec validate 2026-10-11-0212-evolution-crystallize-path`
- [ ] 手工归档（MODIFIED 合并，Scenario 追加；断言 0 Requirement 头丢失 / 0 Scenario 标题丢失）
- [ ] `doc/04-testing/test-cases.md` §125 + 基线 bump；台账 E149（`known-risk.md` §1）+
      §3 ADR-0202 行；`doc/02-modules/evolution.md` 增补
- [ ] 单次提交 `feat(evolution): 结晶通路 runner 注入 + 基准注册操作面（change 0212 / ADR-0202 / 台账 E149）`
