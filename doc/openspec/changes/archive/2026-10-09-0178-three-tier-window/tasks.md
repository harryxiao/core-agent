# Tasks: 三层会话滑窗（short / mid / long）

**测试先行**：每层先写测试（红），再实现（绿）。四门禁直连二进制、**禁** `uv run`。

## Layer A —— 纯策略 `src/core/context/window.py`

- [x] A1. 测试：`tests/test_context_window.py`（红：`ImportError: plan_window`）—— 非分层 ≡ 既有双重上界 / 按比例切分（20→10/6）/ 零守卫 / `short≥1` 边界（表驱动）/ `short+mid≤turns` / 单调 —— pin「三层窗口比例分配」全部 Scenario
- [x] A2. 实现：`WindowPlan` + `plan_window` + `_SHORT_SHARE/_MID_SHARE/_LONG_SHARE/_CHARS_PER_TOKEN`
- [x] A3. `src/core/context/__init__.py` 导出 `WindowPlan` / `plan_window`（同步 `__all__`）

## Layer B —— 机制 `src/core/memory/transcript.py`

- [x] B1. 测试：追加 `tests/test_transcript.py`（红：`AttributeError: window`）—— 短/中带切分不重叠 / 短带 token 截断 + 丢孤儿 assistant / 轮数不足 ⇒ 中带空 / `short_turns<=0` ⇒ 双空 / `tail` 回归锚 —— pin「对话转录持久化」新增 Scenario
- [x] B2. 实现：提取 `_truncate_newest(rows, max_tokens)`（`tail` 改调它，行为逐字不变）；新增 `window(session_id, *, short_turns, mid_turns, short_tokens)`

## Layer C —— 记忆产物 `src/core/memory/store.py`

- [x] C1. 测试：追加 `tests/test_memory.py`（红）
- [x] C2. 实现：提 `_entry_by_id(target)`；新增 `mid_summary_for` + `summarize_slice`（`redact_secrets`、`max_chars` 有界、**不 migrate**）；`memory/protocol.py` 同步声明 —— pin「记忆压实」新增 Scenario

## Layer D —— 循环接线

- [x] D1. 测试：追加 `tests/test_history_replay.py` + `tests/test_loop_token_accounting.py`（红）
- [x] D2. `loop/protocol.py`：`LoopContext` 增 `summary_long` / `summary_mid`
- [x] D3. `loop/planner.py::_system_prompt`：插「历史摘要（长期）/（中期）」两条件块
- [x] D4. `loop/default.py`：`_load_summaries` + `perceive` 分层装配 + `_context_tokens` 非空守卫
- [x] D5. `loop/default.py`：`_maintain` 会话感知（`compact(session_id)` + `_materialize_mid`）+ 调用点传 `ctx.session_id`

## Layer E —— 收尾

- [x] E1. 三份规格 delta（`specs/{loop,context,memory}/spec.md`）
- [x] E2. `doc/01-architecture/adr.md`：ADR-0169 + 追踪行
- [x] E3. 模块/接口文档：`02-modules/{loop,context,memory}.md`、`03-interfaces/{loop,memory}-interface.md`
- [x] E4. `doc/04-testing/test-cases.md`：`## 91.` + 基线 bump
- [x] E5. `coding-plan/known-risk.md`：E115 行 + ADR-0169 局限行
- [x] E6. 四门禁 + `openspec validate` + 手工归档 + `validate --all`
- [x] E7. 记忆（`MEMORY.md` + `coding-plan-leftover-walkthrough.md`）+ 单次提交
