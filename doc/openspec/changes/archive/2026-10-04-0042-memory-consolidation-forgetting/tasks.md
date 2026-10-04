# Tasks: 记忆固化与遗忘

## 1. 规格先行

- [x] 1.1 `specs/memory/spec.md` delta：ADDED「记忆固化（consolidation）」（打分写回 + 价值门控 +
      打分失败不写零）
- [x] 1.2 同 delta：ADDED「记忆遗忘（forgetting）」（衰减评分 → L4 归档 + 可逆 + semantic/L0/L3
      不受影响）
- [x] 1.3 `openspec validate 0042-memory-consolidation-forgetting` 全绿

## 2. 契约与接口文档

- [x] 2.1 `03-interfaces/memory-interface.md`：`forget` 方法与语义；固化打分/门控（`summarizer`
      通道内的价值门控）+ 打分写回的 `importance` 可逆语义
- [x] 2.2 `01-architecture/adr.md`：ADR-0047（固化为压实通道内的价值门控 + 逐条目打分成本上界 +
      遗忘的衰减公式偏离）
- [x] 2.3 `03-interfaces/loop-interface.md`：压实触发一句补 `forget` 一步

## 3. 测试先行（先红）

- [x] 3.1 `tests/test_memory.py`：注入假 scorer + 假摘要器 → `importance` 被写回且可回滚恢复旧值
- [x] 3.2 `tests/test_memory.py`：价值门控——达标会话提炼、低分会话保持 episodic 原层
- [x] 3.3 `tests/test_memory.py`：无 scorer → 不设门槛（0041 行为保持：全部会话提炼）
- [x] 3.4 `tests/test_memory.py`：`forget` 归档陈旧零复用条目（迁 L4 + 返回撤销句柄），
      高 reuse/高 importance 与 semantic/L0/L3 不受影响
- [x] 3.5 `tests/test_memory.py`：`rollback("forgetting.<id>")` 迁回 L2
- [x] 3.6 `tests/test_loop.py`：压实触发时 `forget` 一并执行（陈旧条目被归档）

## 4. 实现

- [x] 4.1 `src/core/memory/store.py`：`compact` 内价值门控（`_score_importance` +
      `_CONSOLIDATE_THRESHOLD` + `_MAX_SCORED_PER_COMPACT`）、`forget`（`_decay_score` +
      `_FORGET_THRESHOLD`）、打分写回记 `memory.importance` 效应
- [x] 4.2 `src/core/loop/default.py`：压实触发补 `memory.forget()`；异常事件名 `maintenance_failed`

## 5. 门禁与归档

- [x] 5.1 ruff check / format 全绿
- [x] 5.2 pyright（src）0 error
- [x] 5.3 `.venv/bin/pytest -q` 全绿
- [x] 5.4 `openspec validate --all` 全绿 → 手动归档（delta 合并进 specs/ + mv 到 archive/）
