# Tasks — TaskHandoff 统一执行框架（change 0247）

## 1. 共享执行器

- [x] 1.1 新增 `src/core/orchestration/handoff.py`：`MAX_HANDOFF_CHARS` /
      `DEFAULT_CONTEXT_TOKENS` / `build_context_pack` / `render_handoff` /
      `stream_handoff` / `run_handoff`
- [x] 1.2 `errors.py` 增 `SUBTASK_TIMEOUT`
- [x] 1.3 `router.py`：`_resolve` / `handoff` 委托 / `handoff_stream`

## 2. Scheduler 接线

- [x] 2.1 构造参数 `subtask_timeout: float = 0` + 非法值 fail-fast
- [x] 2.2 `_build_handoff` 全字段构造；`_run_subtask` 经 `router.handoff_stream`
- [x] 2.3 删除 `_handoff_goal`；`_MAX_HANDOFF_CHARS` 统一引用 handoff 模块

## 3. 配置

- [x] 3.1 `configuration`：常量 + ConfigSpec（CLI/env/yaml 三面）
- [x] 3.2 `_orchestration_errors` 校验 ≥0 整数（bool 非法）
- [x] 3.3 访问器 `orchestration_subtask_timeout()`
- [x] 3.4 `entry._key_to_patch` 白名单加 `orchestration`
- [x] 3.5 组合根注入 `subtask_timeout`

## 4. beast / pet

- [x] 4.1 beast `summon`：`recall` 移入 `finally`
- [x] 4.2 pet `wake`：经 `run_handoff`（空上下文 prompt 逐字相同）

## 5. 委托会话

- [x] 5.1 `loop/protocol.py`：`current_session_id` ContextVar + 导出
- [x] 5.2 `DefaultLoop` 在 `_act` 前后 set/reset
- [x] 5.3 `runtime._dispatch` 透传 `session_id`

## 6. 规格与测试

- [x] 6.1 `orchestration` R3 MODIFIED（+4 Scenario）
- [x] 6.2 `configuration`「编排调度配置」MODIFIED（`subtask_timeout` + 校验 Scenario）
- [x] 6.3 新增 `tests/test_orchestration_handoff.py`（全字段 / 有界 / 超时 / 会话 / 统一执行）
- [x] 6.4 beast / pet / loop / config 回归与新增用例
- [x] 6.5 四门禁 + `openspec validate --all` + 归档
- [x] 6.6 ADR-0235 / 台账 E182 / 测试节 §158 / 接口与模块文档
