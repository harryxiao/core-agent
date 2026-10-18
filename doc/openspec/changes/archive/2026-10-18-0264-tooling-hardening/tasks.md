# Tasks 0264 — 工具面打磨

## 1. 规格

- [x] 1.1 `durability` delta：ADDED「检查点加载损坏行告警且不阻断」。
- [x] 1.2 `loop` delta：MODIFIED「单次推理多工具动作」（去重参数规范化口径）。
- [x] 1.3 `tool-use` delta：MODIFIED「内置原子工具」（输出首尾保留）。

## 2. 红测试（先写）

- [x] 2.1 检查点：坏 JSON 行 + 结构不符行 ⇒ 一条 `UserWarning`（只含条数 / 文件名）、合法行仍可读。
- [x] 2.2 去重：同路径不同写法 / CRLF vs LF / 省略 mode vs 显式 `w` ⇒ `action_deduplicated`。
- [x] 2.3 去重：append 与覆盖写不误合并；`code_run` 保持精确匹配。
- [x] 2.4 输出截断：长输出首尾都在、总长 ≤ 8192、`*_truncated` 语义不变。

## 3. 实现

- [x] 3.1 `CheckpointStore._load`：捕获 `(ValueError, TypeError, KeyError)` + 一次性告警。
- [x] 3.2 `_action_key`：文件写/补丁参数规范化（不改执行参数）。
- [x] 3.3 `_truncate_output`：头部 1/3 + 标记 + 尾部，替换纯头截断。

## 4. 验证

- [x] 4.1 反证：摘告警 / 只捕 JSONDecodeError / 摘规范化 / 退化纯头截断 ⇒ 对应用例红；复原后全绿。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0254；`coding-plan/known-risk.md` E200 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §176；`doc/02-modules/{durability,loop,tool-use}.md` 与
      `doc/03-interfaces/{durability,tool-use}-interface.md` 同步。
- [x] 5.3 单次提交 `feat(tooling): ... change 0264 / ADR-0254 / 台账 E200`；更新记忆。
