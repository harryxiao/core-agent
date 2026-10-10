# 任务 — 流式令牌用量与请求侧输出上限（change 0183 / ADR-0174 / 台账 E120）

## 1. 规格先行

- [x] 1.1 `specs/llm-provider/spec.md` delta：ADDED「流式增量携带令牌用量」（4 Scenario）
- [x] 1.2 `specs/llm-provider/spec.md` delta：ADDED「请求侧输出上限按预留注入」（2 Scenario）
- [x] 1.3 `proposal.md` / `design.md`（D1~D7 + I1~I7 + 测试设计 8 项）

## 2. 先红测试

- [x] 2.1 `tests/test_llm_provider.py`：`_map_chunk` 用量三态（空 `choices` 末块 / 无键 / `null`）
- [x] 2.2 `tests/test_llm_provider.py`：请求体形状（流式带 `stream_options`、非流式不带）
- [x] 2.3 planner 侧：实报抬升下界 / 未上报不抬升 / `completion_tokens` 观测
- [x] 2.4 planner 侧：`max_tokens` 注入下发 / `None`·`0`·`-1` 不下发
- [x] 2.5 组合根：`config` 缺省 ⇒ planner 下发 `output_reserve` 缺省值
- [x] 2.6 红态确认：上述全红（字段/解析/探针/注入点均不存在）

## 3. 实现

- [x] 3.1 `models.py`：`LLMChunk.usage: TokenUsage | None = None`
- [x] 3.2 `stdlib_provider.py`：`_map_usage` 归一 + `_map_chunk` **早返前**解析 + 正常分支带上
- [x] 3.3 `stdlib_provider.py`：流式 body 增 `stream_options={"include_usage": True}`
- [x] 3.4 `planner.py`：`_observe_usage` + `_last_completion_tokens` + `last_completion_tokens()` 探针
- [x] 3.5 `planner.py`：`astream` 循环体**首行**消费用量（早于 `continue`）
- [x] 3.6 `planner.py`：`max_tokens` 构造注入点（`> 0` 归一，否则 `None`）+ `_build_request` 填入
- [x] 3.7 `configuration/manager.py`：`output_reserve()` 独立访问器（**无**新 ConfigSpec）
- [x] 3.8 `runtime.py`：`LLMPlanner(..., max_tokens=config.output_reserve())`

## 4. 四门禁

- [x] 4.1 `.venv/bin/ruff check src tests` → All passed
- [x] 4.2 `.venv/bin/ruff format --check src tests`
- [x] 4.3 `/home/harry/.praisonai/venv/bin/pyright` → 0/0/0
- [x] 4.4 `.venv/bin/pytest -q` → 全通过（记基线增量）

## 5. 归档与文档

- [x] 5.1 `openspec validate 2026-10-10-0183-streaming-token-usage` → valid
- [x] 5.2 手工归档：delta 合 canonical（**ADDED** ⇒ 追加于末条 Requirement 之后；断言 0 行丢失 /
      0 Scenario 标题丢失）⇒ `mv` 进 `doc/openspec/changes/archive/`
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 `doc/01-architecture/adr.md`：ADR-0174 + 追踪行
- [x] 5.5 `doc/02-modules/llm-provider.md` / `doc/02-modules/configuration.md`（`output_reserve()` 访问器）
- [x] 5.6 `doc/03-interfaces/llm-provider-interface.md`（`LLMChunk.usage` / 请求体形状）+
      `doc/03-interfaces/loop-interface.md`（planner 注入点与探针）
- [x] 5.7 `doc/04-testing/test-cases.md`：新 TC 节 + 基线 bump
- [x] 5.8 `coding-plan/known-risk.md`：§1 E120 行 + §3 ADR-0174 局限行
- [x] 5.9 记忆更新（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）

## 6. 提交

- [x] 6.1 单次提交 `feat(llm_provider): …（change 0183 / ADR-0174 / 台账 E120）`
