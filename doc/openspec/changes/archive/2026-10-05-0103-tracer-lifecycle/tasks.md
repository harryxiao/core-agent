# tasks — trace 生命周期闭环与内存释放（change 0103）

## 1. 规格（先行）
- [x] 1.1 `specs/observability/spec.md`：MODIFIED「链路追踪」——Tracer 只存在途；`end_trace` 交付导出器 +
      释放内存；`replay` 服务在途、已完成回溯以落盘为真源；+4 场景
- [x] 1.2 `specs/loop/spec.md`：MODIFIED「执行循环」——开轮 `start_trace`、收尾在完成回调**之后**
      `end_trace` 封口；收尾顺序约束；+3 场景
- [x] 1.3 `openspec validate 2026-10-05-0103-tracer-lifecycle` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_observability.py` 追加：`end_trace` 后该 trace 已被释放（`replay` 返回空）；
      `end_trace` 仍交付导出器（捕获导出器收到事件）
- [x] 2.2 `tests/test_observability.py` 迁移：`test_three_event_kinds_logged` 由「封口后 replay」改为
      「捕获导出器断言」（落盘真路径）
- [x] 2.3 `tests/test_loop.py` 追加：收尾后 `tracer.replay(result.trace_id) == []`；捕获导出器收到本轮事件
- [x] 2.4 `tests/test_loop.py` 追加：**回归守护** —— `trace_observer` 回调收到的快照在封口**之前**
      非空且含 `loop_finished`（既有用例 `test_trace_observer_sees_all_events_of_the_run` 保持绿即证）
- [x] 2.5 `tests/test_loop.py` 追加：多轮（N≥10）后 Tracer 内存不随轮次增长
- [x] 2.6 `tests/test_loop.py` + `tests/test_phase13.py` 迁移：`loop.run(...)` 后 replay 断言改为
      捕获导出器断言（`loop_finished` / `loop_started` 归因）
- [x] 2.7 `tests/test_evolution_wiring.py` 追加：loop 收尾封口后 `EvolutionWorker` 仍能拿到事件
      （`on_trace_complete` 快照非空；`maybe_run(force=True)` 不返回 `no_evidence` 型空结果）——
      **0101/0102 回归守护**
- [x] 2.8 `tests/test_evolution.py` 追加/调整：`on_trace_complete` 现登记**事件快照**；`_collect` 遍历快照；
      `_completed` 受批窗口约束（有界断言）
- [x] 2.9 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `observability/tracer.py`：`end_trace` 改 `pop`（取出 → 非空则 `emit`）；`replay` 文档口径订正为
      「在途」；模块 docstring 同步
- [x] 3.2 `loop/default.py`：新增 `_start_trace(task_id)`（注入 tracer 则 `start_trace`，否则 uuid 回退）；
      `astream` 开轮改用它取 `trace_id`；新增 `_end_trace(trace_id)`（注入 tracer 则 `end_trace`），
      插在 `_notify_trace_complete` **之后**
- [x] 3.3 `evolution/worker.py`：`_completed: list[list[TraceEvent]]`；`on_trace_complete` 登记
      `self._tracer.replay(trace_id)` 快照；`_collect` 遍历快照
- [x] 3.4 四门全绿（直连二进制不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/observability-interface.md` §4（`replay` 口径）/§5（`end_trace` 交付 + 释放；
      订正「flush」措辞）
- [x] 4.2 `doc/03-interfaces/loop-interface.md`：收尾面补「开轮 start / 收尾 end 封口（在回调之后）」
- [x] 4.3 `doc/01-architecture/adr.md`：**ADR-0096**（责任分区：Tracer 只存在途、留存归消费者；为何不做
      有界环形缓存 / 推送 sink；`replay` 口径收窄的理由）+ 末尾映射表行
- [x] 4.4 `doc/04-testing/test-cases.md`：`TC-OBS-xx` / `TC-LOOP-xx` 追踪号
- [x] 4.5 `coding-plan/phase-22.md`：§2 P0 勾选/标注；`coding-plan/README.md` §2 第 22 行状态推进

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{observability,loop}/spec.md` + tick tasks
      + `shutil.move` 进 `archive/2026-10-05-0103-tracer-lifecycle/`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填
- [x] 5.4 记忆更新 + 提交（`feat(observability): trace 生命周期闭环与内存释放（change 0103）`）
