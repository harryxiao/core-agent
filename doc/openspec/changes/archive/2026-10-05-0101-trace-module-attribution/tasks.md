# tasks — trace 收尾回调与模块归因（change 0101）

## 1. 规格（先行）
- [x] 1.1 `specs/loop/spec.md`：MODIFIED「执行循环」——收尾 SHALL 按轮调用可选 trace 完成回调
      （不受维护节拍节流、失败降级）；自身失败事件的模块归因 + 4 个新场景
- [x] 1.2 `specs/observability/spec.md`：MODIFIED「全链路日志」——事件 SHALL 可携带模块归因字段
      （可选、缺省无、向后兼容）
- [x] 1.3 `specs/evolution/spec.md`：MODIFIED「经验采集」——带模块归因的事件 SHALL 被适配为可归因 Trace
- [x] 1.4 `openspec validate 2026-10-05-0101-trace-module-attribution` 通过

## 2. 测试（先写，红）
- [x] 2.1 `tests/test_loop.py` 追加：回调按轮提交 / 回调时事件已齐 / 不受节拍节流 / 失败降级
      （`trace_observer_failed`）/ 未注入则不做
- [x] 2.2 `tests/test_loop.py` 追加：`loop_finished` 的 `module_id` 归因（失败轮有、正常轮无）
- [x] 2.3 `tests/test_observability.py` 追加：`TraceEvent.module_id` 缺省为 `None` 且既有构造/序列化不变
- [x] 2.4 `tests/test_evolution.py` 追加：`_to_traces` 模块归因通道（`plugin_id == module_id`、失败语义）
      + 既有 `tool_call` 通道逐字不变
- [x] 2.5 `tests/test_evolution_wiring.py` 追加：`build_runtime` 主 loop 接到 `worker.on_trace_complete`；
      `evolution` 关闭时该回调为 `None`（离线替身，**不出网**）
- [x] 2.6 运行确认**红**（新增用例失败、既有用例全绿）

## 3. 实现
- [x] 3.1 `observability/events.py`：`TraceEvent` 增 `module_id: str | None = None`（含语义注释）
- [x] 3.2 `loop/default.py`：`TraceObserver = Callable[[str], None]`；ctor 增 `trace_observer`；
      `_notify_trace_complete(trace_id)`（失败降级留痕）；插在 `_trace(loop_finished)` **之后**；
      `_trace` 增可选 `module_id` 形参并在 `loop_finished` 失败轮传 `"loop.default"`
- [x] 3.3 `evolution/worker.py`：`_to_traces` 增模块归因通道（带 `module_id` ⇒ 可归因 Trace）；
      `tool_call` 通道逐字不变
- [x] 3.4 `runtime.py`：evolution 装配块内取 `trace_observer=evolution_worker.on_trace_complete`，
      注入**主 loop**；关闭时保持 `None`
- [x] 3.5 四门全绿（直连二进制不用 `uv run`）

## 4. 文档
- [x] 4.1 `doc/03-interfaces/observability-interface.md`：`TraceEvent` 字段表补 `module_id`
- [x] 4.2 `doc/03-interfaces/loop-interface.md`（若有该文件）：注入面补 `TraceObserver`
- [x] 4.3 `doc/01-architecture/adr.md`：ADR-0094（trace 收尾回调 + 模块归因字段；**为何不纳入
      `PluginRegistry`**）+ 末尾映射表行
- [x] 4.4 `doc/04-testing/test-cases.md`：TC-OBS-xx / TC-LOOP-xx / TC-EVO-xx 追踪号

## 5. 收口
- [x] 5.1 手工归档（delta 合进 `doc/openspec/specs/{loop,observability,evolution}/spec.md` + tick tasks
      + `shutil.move` 进 `archive/2026-10-05-0101-trace-module-attribution/`）
- [x] 5.2 `openspec validate --all` 全绿
- [x] 5.3 账本回填（`coding-plan/phase-21.md` 勾选 + `phase-19.md`/`phase-20.md` 转出项登记）
- [x] 5.4 记忆更新 + 提交（`feat(observability): trace 收尾回调与模块归因（change 0101）`）
