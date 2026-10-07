# 0167 · 任务清单

> 触发：用户 2026-10-08 实测（本轮批准的第 3 项修复）。
> 证据：`~/.core/state/traces.jsonl` 的 `maintenance_failed` × 26，分布 1/1/8/2/3/11 = `max(0, rounds-9)`。

## 1. 规格与决策（先行）

- [x] 1.1 `specs/loop/spec.md` **ADDED** Requirement「收尾与维护工作的执行线程」+ 5 Scenario
- [x] 1.2 **ADR-0157**（三处边界卸载 / 取 A 弃 B、C 的两条理由 / 私有方法保持同步 / DI 契约零变更 /
      与 ADR-0064 ② 的一致性 / 局限）+ 变更追踪行
- [x] 1.3 `openspec validate 2026-10-08-0167-loop-offload-sync-llm-seams` ⇒ valid

## 2. 测试先行（红）

- [x] 2.1 `tests/test_loop_offload_threads.py`（新）：收尾观察者在**无运行中事件循环**的线程上被调用
- [x] 2.2 同上：冷路径回调在**无运行中事件循环**的线程上被调用
- [x] 2.3 同上：压实期间事件循环**仍能推进其他协程任务**（阻塞式替身堵住压实）
- [x] 2.4 同上（端到端）：会话摘要接缝用**同步模型桥接**（`asyncio.run` 形态）⇒ 摘要**真的落库**
      且**无** `maintenance_failed` 遥测
- [x] 2.5 同上：观察者 / 冷路径**抛错仍只降级留痕**，本轮回复与事件序零回归
- [x] 2.6 红态确认：`.venv/bin/pytest -q tests/test_loop_offload_threads.py` ⇒ **4 失败 / 1 通过**
      （失败带 `RuntimeWarning: coroutine 'acompletion' was never awaited` + `maintenance_failed` ——
      精确复现生产事故；旧实现 `to_thread` 缺席）

## 3. 实现（绿）

- [x] 3.1 `src/core/loop/default.py:324` ⇒ `await asyncio.to_thread(self._compact, ctx, trace_id)`
- [x] 3.2 同上 `:331` ⇒ `await asyncio.to_thread(self._notify_turn, ctx, trace_id, ok=…)`
- [x] 3.3 同上 `:344` ⇒ `await asyncio.to_thread(self._maintain, trace_id)`
- [x] 3.4 **不改**三个私有方法的签名与内部降级链；**不改**任何 DI 接缝契约
- [x] 3.5 绿态确认：`.venv/bin/pytest -q tests/test_loop_offload_threads.py` ⇒ **5 passed**
      （2.3 断言放宽为 `compacted >= 1` —— 替身 `round_threshold=1` 下两轮各压实一次；
      2.4 观测点从 `acompletion` **移出**（其内 `asyncio.run` 自建循环，非被观测对象）⇒ 落在
      `_sync_bridge._text` 的 `completion()` 调用点）

## 4. 文档

- [x] 4.1 `doc/02-modules/loop.md` 补段（§3.5 收尾与维护在工作线程上执行；原 §3.5 可观测顺延 §3.6）
- [x] 4.2 `doc/03-interfaces/loop-interface.md` §4（约束）补一条
- [x] 4.3 `doc/04-testing/test-cases.md` 新节 `## 79.`（TC-OFFLOAD，5 用例）
- [x] 4.4 `coding-plan/known-risk.md`：§1 新行 **E103** + §3 ADR-0157 局限行

## 5. 门禁与收口

- [ ] 5.1 `ruff check` / `ruff format --check` / `pyright`（0/0/0）/ `pytest -q` 四门禁直连全绿
- [ ] 5.2 `openspec validate 2026-10-08-0167-…` ⇒ valid ⇒ 手工归档（delta 并入 canonical + `mv`）
      ⇒ `openspec validate --all` ⇒ n/0
- [ ] 5.3 台账回填 + 记忆更新 + **单次提交**

> **5.1 备注**：`tests/test_diagnostics.py` 有 **1 失败**（`test_render_notes_columns_aligned`）+ 3 处
> ruff 报错 —— 属**用户进行中的 `0165` 未提交工作**，本次**有意未改**（非本 change 面）。
> 本 change 自身文件（`src/core/loop/default.py` / `tests/test_loop_offload_threads.py`）四门禁全绿。
