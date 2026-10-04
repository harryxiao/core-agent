# Tasks — evolution-confirm-surface

## 1. 规格先行
- [x] 1.1 evolution delta（ADDED「人工确认队列的持久化与操作面」6 场景）
- [x] 1.2 `openspec validate 0055-evolution-confirm-surface` 全绿

## 2. 测试先行（先红）
- [x] 2.1 稳定身份：两个 `generation` 相同的候选 `candidate_id` 不同；同一对象恒等
- [x] 2.2 `PendingQueue` 落盘/恢复：候选 + 门禁 + 评测三项往返一致；未注入路径不写盘
- [x] 2.3 损坏/缺失落盘 → 空队列（不抛）
- [x] 2.4 跨进程语义：同路径新引擎恢复候选后 `confirm` → `crystallize` 得 `published`（回归 `id()` 键失配）
- [x] 2.5 `pending()` 只列 `status=="pending"`；`confirm`/`reject` 后不再出现
- [x] 2.6 `reject`：置 `rejected` + 落盘 + 后续 `crystallize` 拒绝
- [x] 2.7 `find(candidate_id)` 命中/未命中
- [x] 2.8 操作面：`evolve pending` 列出、`evolve confirm <id>` 发布、`evolve reject <id>` 拒绝、未知 id 非零退出
- [x] 2.9 `risk_level="high"` 经操作面确认：签发审批单 → 放行；`low` 无需工单
- [x] 2.10 生产装配：`build_runtime` 后引擎队列已注入路径（接线断言）
- [x] 2.11 回归：`tests/test_evolution.py` 既有确认门/结晶/观察期用例全绿；`test_architecture.py` 分层不破

## 3. 实现
- [x] 3.1 `models.py`：`GenerationCandidate.candidate_id`（UUID，构造固化）
- [x] 3.2 `evolution/pending.py`：`PendingQueue`（record/records/pending/find/gate_of/eval_of/flush + 落盘恢复）
- [x] 3.3 `engine.py`：以队列取代 `_pending`/`_gate`/`_eval`；检索键改 `candidate_id`；增 `reject`/`find`
- [x] 3.4 `evolution/__init__.py` 导出 `PendingQueue`
- [x] 3.5 `runtime.py`：组合根注入 `_skill_state_path("evolution-pending.json")`
- [x] 3.6 `entry.py`：`evolve pending|confirm|reject` 子命令 + 审批单签发（high 风险）

## 4. 文档同步
- [x] 4.1 `doc/03-interfaces/evolution-interface.md`（队列持久化 + 操作面 + `reject`/`find`）
- [x] 4.2 `doc/02-modules/evolution.md`（确认队列状态面 + 组合根装配）
- [x] 4.3 `doc/01-architecture/adr.md` ADR-0058 + 文末映射表行

## 5. 门禁与归档
- [x] 5.1 四门全绿：ruff check/format · pyright · pytest · openspec validate --all
- [x] 5.2 手动归档（合 delta → mv 到 `archive/<date>-0055-evolution-confirm-surface/`）
- [x] 5.3 账本 A4 关闭 + `coding-plan/README.md` 同步
- [x] 5.4 提交（`feat(evolution): 人工确认队列持久化与操作面（change 0055）`）
