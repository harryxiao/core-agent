# Tasks — constraints-middleware-wiring

## 1. 规格先行
- [x] 1.1 loop delta（MODIFIED 横切中间件插入：双接缝 + 3 新场景）
- [x] 1.2 constraints delta（MODIFIED 容错中间件：按工具隔离 + 计数规则 + 3 新场景）
- [x] 1.3 `openspec validate 0052-constraints-middleware-wiring` 全绿

## 2. 测试先行（先红）
- [x] 2.1 loop 契约：观察者按注册序收 (ctx, action, result)
- [x] 2.2 loop 契约：观察者抛错 → 本轮照常完成 + 记 `action_observer_failed`
- [x] 2.3 loop 契约：终止动作不触发观察者；既有 callable 中间件/改写中间件行为不变（回归）
- [x] 2.4 适配层：按工具隔离（A 开断、B 仍可执行）
- [x] 2.5 适配层：策略性拒绝（GATE_DENIED/IRREVERSIBLE_BLOCKED/INVALID_ARGS）远超阈值仍 CLOSED
- [x] 2.6 适配层：注入 clock 走 半开→成功→闭合；CIRCUIT_OPEN 转终止 Action 且不逃逸
- [x] 2.7 生产装配：`build_runtime` 后主 loop 与子 agent loop 持有同一 chain 实例
- [x] 2.8 端到端熔断：连续失败达阈值 → 第 N+1 次工具 handler 调用计数停在 N，回复含 CIRCUIT_OPEN

## 3. 实现
- [x] 3.1 `loop/default.py`：`ActionObserver` 别名 + ctor `action_observers` + `_notify_action_result` + astream 调用点
- [x] 3.2 `loop/__init__.py`：导出 `ActionObserver`
- [x] 3.3 `constraints/fault_tolerance.py`：`CircuitBreaker` 加法式 `clock` 注入
- [x] 3.4 `loop/constraints_adapter.py`（新）：`ConstraintsChain` + `build_constraints_chain`
- [x] 3.5 `runtime.py`：构造一份 chain，注入主 loop + `_agent_loop`

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/loop-interface.md`（补两接缝 + fail-loud/soft）
- [x] 4.2 `doc/03-interfaces/constraints-interface.md`（按工具接线 + 只计执行失败 + §7 关联适配层）
- [x] 4.3 `doc/02-modules/constraints.md` §4（改为实际接线描述）
- [x] 4.4 `doc/02-modules/loop.md`（注入面补 `action_observers`，若列举）
- [x] 4.5 `doc/01-architecture/adr.md` ADR-0055 + 文末映射表行

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate
- [x] 5.2 手动归档（合 2 份 delta → mv 到 `archive/<date>-0052-constraints-middleware-wiring/`）
- [x] 5.3 `openspec validate --all` 全绿
- [x] 5.4 账本：E1 关闭（含「校验非空转」订正）+ phase-13/phase-2 勾销 + 3 条后续行
- [x] 5.5 提交（`feat(constraints): 约束中间件链接入 loop（结果侧观察者 + 按工具熔断，change 0052）`）
