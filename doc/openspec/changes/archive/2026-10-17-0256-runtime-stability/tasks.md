# Tasks 0256 — 运行稳定性三项

## 1. 规格

- [x] 1.1 `llm-provider` delta：ADDED「流式增量等待超时」/ 2 scen。
- [x] 1.2 `loop` delta：ADDED「流式中断留痕」/ 3 scen。
- [x] 1.3 `loop` delta：ADDED「轮内压实进度与上限」/ 2 scen。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_llm_provider.py`：
      - 首块前静默超过 `timeout` ⇒ `LLMTimeoutError`，已收增量保留
      - 增量持续到达不超时（同一响应多块）
- [x] 2.2 `tests/test_loop.py`：
      - 消费方在 `reply_delta` 后 `aclose` ⇒ 导出器收到 `loop_aborted`，trace 已封口
      - 执行体抛未收尾异常 ⇒ 同样留痕并封口
      - 正常轮次**不产** `loop_aborted`
- [x] 2.3 `tests/test_loop_cost_observability.py`：
      - 阈值压实 ⇒ `loop.compacting` / `loop.compacted`（`elapsed_ms`、`timeout=False`）
      - 压实阻塞超过注入上限 ⇒ `timeout=True`，本轮仍到 `loop_finished`，
        遥测含 `maintenance_failed.step="compaction_timeout"`
- [x] 2.4 `tests/test_ui.py`：`_EVENT_MAP` 登记两条事件；`_format_event` 文本。

## 3. 实现

- [x] 3.1 `llm_provider/stdlib_provider.py`：队列等待超时 + 响应释放 + `LLMTimeoutError`。
- [x] 3.2 `loop/default.py`：`astream` 包装 / `_astream_events` / `state` / `aclosing`。
- [x] 3.3 `loop/default.py`：`_compact_bounded` + 两条 LoopEvent + `compact_timeout` 构造参。
- [x] 3.4 `ui/api.py` 事件映射；`ui/repl.py` 单行格式化。

## 4. 验证

- [x] 4.1 探针：逐点摘除 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0247；`coding-plan/known-risk.md` E193 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §169；接口 / 模块文档补写。
- [x] 5.3 单次提交 `fix(loop): ... change 0256 / ADR-0247 / 台账 E193`；更新记忆。
