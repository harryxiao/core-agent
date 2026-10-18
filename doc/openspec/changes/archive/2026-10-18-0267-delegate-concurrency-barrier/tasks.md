# Tasks 0267 — 委托动作并发判级修正

## 1. 规格

- [x] 1.1 `loop` delta：MODIFIED「单次推理多工具动作」（deny 词元补 `delegate` + 新场景）。

## 2. 红测试（先写）

- [x] 2.1 同批两个 `agent:delegate` 工具动作串行执行（不重叠，总耗时约为两倍）。
- [x] 2.2 既有只读并发 / 写屏障 / 按序提交用例保持绿。

## 3. 实现

- [x] 3.1 `_CONCURRENT_DENY_TOKENS` 增加 `delegate`。

## 4. 验证

- [x] 4.1 反证：摘 `delegate` 词元 ⇒ 委托串行用例红；复原 `md5sum` 同。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR；`coding-plan/known-risk.md` 台账条目。
- [x] 5.2 `doc/04-testing/test-cases.md`；`doc/02-modules/loop.md`。
- [x] 5.3 单次提交 `fix(loop): ... change 0267 / ADR-0257 / 台账 E203`；更新记忆。
