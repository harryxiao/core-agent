# 任务 — 已知模型窗口表与 provider 审计标签（change 0184 / ADR-0175 / 台账 E121）

## 1. 规格（spec-first）

- [x] `specs/configuration/spec.md` — MODIFIED「LLM 提供商配置（必选）」（窗口来源优先级 + 表纪律）
      + 3 新 Scenario；既有 8 Scenario 逐字保留
- [x] `specs/llm-provider/spec.md` — MODIFIED「模型调用审计」（标签真实性）+ 1 新 Scenario；
      既有「调用留痕」Scenario 逐字保留
- [x] `proposal.md` / `design.md` / `tasks.md`

## 2. 红测试（先失败）

- [ ] `tests/test_loop_budget_config.py` 新增节「已知模型窗口表」：
      `test_known_window_matches_model_families`、`test_known_window_unknown_model_is_zero`、
      `test_loop_limits_derives_window_from_model`、`test_loop_limits_explicit_window_wins`、
      `test_loop_limits_unknown_model_falls_back`
- [ ] `tests/test_llm_provider.py` 新增节「provider 审计标签」：
      `test_response_provider_label_reflects_configuration`、
      `test_response_provider_defaults_to_identity`
- [ ] `test_build_runtime_labels_provider_from_config`（组合根接线）
- [ ] 确认全红（模块不存在 / 构造参数不存在 / 标签恒 `stdlib`）

## 3. 实现

- [ ] 新模块 `src/core/configuration/model_windows.py`：`_KNOWN_CONTEXT_WINDOWS` + `known_window()`
- [ ] `src/core/configuration/manager.py`：`loop_limits()` 窗口三态归一（`_DEFAULT_CONTEXT_WINDOW`）
- [ ] `src/core/llm_provider/stdlib_provider.py`：`provider: str = "stdlib"` 构造参数 + `self._provider`
      + `_map_response` 用实例值
- [ ] `src/core/runtime.py`：`StdlibLLMProvider(..., provider=app.llm.provider)`

## 4. 四门禁（直连二进制）

- [ ] `.venv/bin/ruff check src tests` → All passed
- [ ] `.venv/bin/ruff format --check src tests`
- [ ] `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [ ] `.venv/bin/pytest -q` → 基线 2176 → ?（记增量）

## 5. 归档（手工）

- [ ] `openspec validate 2026-10-10-0184-model-window-provider-label` → valid
- [ ] 脚本化合并 delta → canonical（**MODIFIED 替换**同名 Requirement 块，断言 0 既有 Scenario
      标题丢失 / 未改块逐字保留）⇒ `mv` 进 `doc/openspec/changes/archive/`
- [ ] `openspec validate --all` 全绿

## 6. 文档 / 台账

- [ ] `doc/01-architecture/adr.md`：ADR-0175 + 变更追踪行
- [ ] `doc/02-modules/configuration.md`（窗口表）/ `doc/02-modules/llm-provider.md`（审计标签）
- [ ] `doc/03-interfaces/configuration-interface.md` / `doc/03-interfaces/llm-provider-interface.md`
- [ ] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump
- [ ] `coding-plan/known-risk.md` §1 E121 行 + §3 ADR-0175 局限行

## 7. 记忆 / 提交

- [ ] `MEMORY.md` + `coding-plan-leftover-walkthrough.md`（`0184` 节 + 批次进度）
- [ ] 单次提交 `feat(configuration): …（change 0184 / ADR-0175 / 台账 E121）`
