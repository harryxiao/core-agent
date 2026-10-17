# Tasks 0257 — 并行工具调用、重复写抑制与原子写

## 1. 规格

- [x] 1.1 `loop` delta：ADDED「单次推理多工具动作」/ 4 scen。
- [x] 1.2 `tool-use` delta：ADDED「文件写入原子性」/ 3 scen。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_phase13.py`（或新文件）：
      - 非流式两条 tool_calls ⇒ `ActionGroup` 含 2 个动作（按 index）；单调用仍为 `Action`
      - 流式多 index 片段 ⇒ `ActionGroup` 顺序正确
      - 批次内一个调用参数非法 ⇒ 单个失败终止动作（`LLM_PLAN_PARSE_FAILED`）
- [x] 2.2 `tests/test_loop.py`：
      - `ActionGroup` 两个动作 ⇒ 处理器各执行一次、两组动作事件、`rounds == 2`
      - 批内完全重复 ⇒ 处理器只调用一次 + trace `action_deduplicated(scope="batch")`
      - 相邻轮次重复 `file_write` ⇒ 只写一次 + trace `scope="turn"`
      - 中间有其他动作后的相同写不被抑制
- [x] 2.3 `tests/test_tool_use.py`：
      - 覆盖写入后目标为新内容、目录无临时残留
      - `os.replace` 失败 ⇒ 目标原内容逐字不变、临时文件清理
      - 追加模式回归
      - 既有权限位保留（创建 0o640 文件后覆盖，仍为 0o640）

## 3. 实现

- [x] 3.1 `loop/protocol.py`：`ActionGroup`。
- [x] 3.2 `loop/planner.py`：全量映射 + 批次解析失败归一。
- [x] 3.3 `loop/default.py`：`_reason_events` 展开组；主循环待执行队列；两层重复抑制。
- [x] 3.4 `tools/builtin.py`：`file_write` 覆盖模式原子化。

## 4. 验证

- [x] 4.1 探针：逐点摘除 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0248；`coding-plan/known-risk.md` E194 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §170；模块 / 接口文档补写。
- [x] 5.3 单次提交 `fix(loop): ... change 0257 / ADR-0248 / 台账 E194`；更新记忆。
