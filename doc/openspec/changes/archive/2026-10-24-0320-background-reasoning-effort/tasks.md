# Tasks — 后台派生调用的推理档位透传（0320）

> 规格先行：先落 `configuration` ADDED ×1，再红→绿。
> 台账编号让位并行 change `0318`（ADR-0308／E254／§231 预留），本 change 用 ADR-0310／E256／§233。

## 1. 规格

- [x] 1.1 `specs/configuration/spec.md`：ADDED「后台派生调用的推理档位透传」——透传 SHALL、
  未配置 SHALL NOT 下发、零新配置键、不改超时/重试；Scenario ×2。
- [x] 验证：`openspec validate 2026-10-24-0320-background-reasoning-effort` 绿。

## 2. 红测（先写、确认失败）

- [x] 2.1 `tests/test_background_reasoning_effort.py::test_background_calls_carry_configured_reasoning_effort`：
  配置 `llm.reasoning_effort: low`，经 `MemoryStore.compact(session_id=…)` 触发后台调用 ⇒
  捕获的**每个**请求 `reasoning_effort == "low"`。
- [x] 2.2 `tests/test_background_reasoning_effort.py::test_background_calls_omit_reasoning_effort_when_unset`：
  未配置 ⇒ 每个请求 `reasoning_effort is None`。
- [x] 验证：2.1 在未改动实现前**红**；2.2 绿（零变化守卫）。

## 3. 实现

- [x] 3.1 `src/core/runtime.py`：`_llm_text` 构造 `LLMRequest` 时加
  `reasoning_effort=app.llm.reasoning_effort`。
- [x] 验证：2.1 转绿；`tests/test_foreground_liveness_config.py` / `test_memory*.py` /
  `test_evolution*.py` / `test_procedural_e2e.py` 不回归。

## 4. 门禁

- [x] 4.1 `uv run pytest`（全量）全绿。
- [x] 4.2 `uv run ruff check src tests` + `uv run ruff format --check src tests` 干净。
- [x] 4.3 `uv run pyright` 无新增错误。
- [x] 4.4 反证（`cp` → `/tmp` 改坏 → 复原 → `md5sum` 比对）：
  - 删 `reasoning_effort` 实参 ⇒ 2.1 红；
  - 硬编码 `"high"` ⇒ 2.1 红；
  - 未配置回落 `"low"` ⇒ 2.2 红。
- [x] 4.5 `openspec validate --all` 全绿（并行 `0318` 仍 active 时按实际计数记录）。
- [x] 4.6 真实端点正证：同一摘要 prompt 在 `reasoning_effort=low` 下实测 < 20s（设计证据 E5
  重放；密钥只在内存解析，不落盘 / 不回显）。

## 5. 文档与台账

- [x] 5.1 `doc/01-architecture/adr.md`：ADR-0310（后台派生透传 `llm.reasoning_effort`；被拒：
  provider 内补默认档位、后台固定 `max_tokens`、复用 `output_reserve`）。
- [x] 5.2 `doc/04-testing/test-cases.md`：§233 用例表。
- [x] 5.3 `coding-plan/known-risk.md`：E256（未配置档位仍可能超时；端点采纳不可校验；压实仍
  轮内阻塞）。
- [x] 5.4 `doc/02-modules/` 对应模块（memory / evolution）如提及后台调用参数，补一句档位口径
  —— 仅在既有文字与实际不符时改。

## 6. 收口（须用户确认）

- [x] 6.1 归档 `openspec archive 2026-10-24-0320-background-reasoning-effort -y`。
- [x] 6.2 提交（`fix(llm): 后台派生调用透传推理档位（change 0320 / ADR-0310 / 台账 E256）`）。
- [ ] 6.3 推送 `origin/phase20-base`。
