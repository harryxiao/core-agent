# tasks — 0089 observability 生产导出器装配

## 1. 规格先行
- [x] 1.1 `specs/observability/spec.md` delta：MODIFIED「全链路日志」（补组合根装配 + 注入优先 + 2 场景）
- [x] 1.2 `openspec validate 0089-observability-prod-exporter` 通过

## 2. 测试先行（红）
- [x] 2.1 `tests/test_observability_wiring.py`（新）：`build_runtime`（未注入）后，`end_trace` 使事件落 `$CORE_STATE_DIR/traces.jsonl`
- [x] 2.2 组装出的 tracer 导出面经**缓冲包装**（导出失败降级不阻塞 —— 断言类型链 `BufferedExporter` → `JSONLExporter`）
- [x] 2.3 显式注入的 tracer **优先**（不被缺省生产导出器覆盖）
- [x] 2.4 红：`git stash push -u -- src/` 后新增用例失败 → `git stash pop`

## 3. 实现（绿）
- [x] 3.1 `src/core/runtime.py`：新增 `_trace_path()`（`$CORE_STATE_DIR/traces.jsonl`）
- [x] 3.2 `src/core/runtime.py:224`：未注入时 `Tracer(exporter=BufferedExporter(JSONLExporter(_trace_path())))`；补 import

## 4. 四门
- [x] 4.1 `ruff check src tests`
- [x] 4.2 `ruff format --check src tests`
- [x] 4.3 `pyright`（0 errors）
- [x] 4.4 `.venv/bin/pytest -q` 全绿

## 5. 文档
- [x] 5.1 `doc/03-interfaces/observability-interface.md`：§5 生产装配口径
- [x] 5.2 `doc/02-modules/observability.md`：§3.1 / §5 按实际接线订正
- [x] 5.3 `doc/01-architecture/adr.md`：ADR-0084 + 映射表行
- [x] 5.4 `doc/04-testing/test-cases.md`：TC-OBS-05

## 6. 归档与记账
- [x] 6.1 手动合并 delta → `doc/openspec/specs/observability/spec.md`；`shutil.move` 变更目录到 `archive/2026-10-05-0089-…`
- [x] 6.2 `openspec validate --all` 全绿
- [x] 6.3 账本：`phase-20.md` §1 C4 行标已关闭 + `phase-19.md` §5 C 行 + `coding-plan/README.md`
- [x] 6.4 记忆 `coding-plan-leftover-walkthrough.md` + `MEMORY.md`
- [x] 6.5 提交 `feat(observability): 组合根装配生产导出器（change 0089）`
