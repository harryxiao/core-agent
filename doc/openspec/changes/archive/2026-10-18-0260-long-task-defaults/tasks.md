# Tasks 0260 — 长任务默认值

## 1. 规格

- [x] 1.1 `loop` delta：MODIFIED「错误与预算控制」（默认轮数 20）。
- [x] 1.2 `configuration` delta：MODIFIED「循环预算配置」（默认轮数 20）与「编排调度配置」
      （默认 600 秒；显式 0 仍不设限）。

## 2. 红测试（先写）

- [x] 2.1 `tests/test_loop_budget_config.py`：ConfigSpec 缺省 20、全部 `loop_limits()` 缺省断言
      `(20, …)`、组合根注入缺省 20；新增 `DefaultLoop` 构造缺省同值用例。
- [x] 2.2 `tests/test_llm_config_hot_update.py`：缺省 `(20, 65536)`。
- [x] 2.3 `tests/test_orchestration_config.py`：ConfigSpec 缺省 600、缺省访问器 600、组合根注入
      600、显式 `0` 仍为 0（关闭）、`TaskScheduler` 构造缺省仍为 0。

## 3. 实现

- [x] 3.1 `configuration/manager.py`：`_DEFAULT_MAX_ROUNDS = 20`、
      `_DEFAULT_ORCHESTRATION_SUBTASK_TIMEOUT = 600`，相关注释同步。
- [x] 3.2 `loop/default.py`：`DefaultLoop.__init__(max_rounds: int = 20)`。

## 4. 验证

- [x] 4.1 反证：逐点还原常量 / 构造缺省 ⇒ 对应用例红；复原 md5 一致。
- [x] 4.2 四门禁：`ruff check` / `ruff format --check` / `pyright` / `pytest -q`。
- [x] 4.3 `openspec validate --all`；归档 change。

## 5. 文档与收口

- [x] 5.1 ADR-0250；`coding-plan/known-risk.md` E196 + §3 行。
- [x] 5.2 `doc/04-testing/test-cases.md` §172；`doc/03-interfaces/configuration-interface.md`
      与模块注释同步。
- [x] 5.3 单次提交 `feat(configuration): ... change 0260 / ADR-0250 / 台账 E196`；更新记忆。
