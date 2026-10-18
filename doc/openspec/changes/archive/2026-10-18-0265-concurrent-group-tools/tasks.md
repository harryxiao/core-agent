# Tasks 0265 — 组内工具并发执行

## 1. 规格

- [x] 1.1 `loop` delta：MODIFIED「单次推理多工具动作」（只读并发 / 写屏障 / 按序提交）。
- [x] 1.2 `tool-use` delta：MODIFIED「异步工具调用」（同步 handler 卸载到工作线程）。

## 2. 红测试（先写）

- [x] 2.1 组内两个只读动作并发：总耗时显著小于串行上界。
- [x] 2.2 写动作是屏障：读完成后才执行写。
- [x] 2.3 并发结果按原序提交（完成顺序反转时事件 / 观测仍按序）。
- [x] 2.4 `concurrent_reads=False` 逐字串行。
- [x] 2.5 批内重复键不并发、仍只执行一次。
- [x] 2.6 并发批次不超过 `max_rounds` 剩余额度。
- [x] 2.7 同步 handler 经 `ainvoke` 不阻塞事件循环；协程 handler 仍真并发。

## 3. 实现

- [x] 3.1 `ToolProvider._call`：`iscoroutinefunction` 直调，否则 `asyncio.to_thread`。
- [x] 3.2 `_is_concurrent_safe` + 批次吸收（连续只读、唯一键、轮次上限）。
- [x] 3.3 执行 / 提交分离：并发段 gather，结果按原序提交；串行段既有路径不变。
- [x] 3.4 `DefaultLoop(concurrent_reads=True)` 构造开关。

## 4. 验证

- [x] 4.1 反证：摘并发（强制串行）/ 摘 `to_thread` / 摘屏障 / 改提交逆序 ⇒ 对应用例红；复原 `md5sum` 同。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR；`coding-plan/known-risk.md` 台账条目。
- [x] 5.2 `doc/04-testing/test-cases.md`；`doc/02-modules/{loop,tool-use}.md`、
      `doc/03-interfaces/tool-use-interface.md`。
- [x] 5.3 单次提交 `feat(loop): ... change 0265 / ADR-NNNN / 台账 ENNN`；更新记忆。
