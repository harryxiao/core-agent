# Tasks 0190 — 检查点会话归因 + task 路径会话接线

## 1. 规格（spec-first）

- [x] `specs/orchestration/spec.md`：MODIFIED「断点续跑」（检查点携带发起会话标识条款 +
      1 Scenario）＋ MODIFIED「任务入口与进度事件」（CLI task 会话铸/复用条款 + 2 Scenario），
      既有 Scenario 标题零丢失
- [x] `specs/cli-ops/spec.md`：MODIFIED「会话命令族与交互入口续聊」（一次性任务入口铸会话入
      同一注册表条款 + 1 Scenario），既有 5 Scenario 逐字保留
- [x] ADR-0180（`doc/01-architecture/adr.md`）

## 2. 测试先行（红）

- [x] `test_orchestration.py`：checkpoint / on_done 回调收到发起会话标识（fresh 非空 + 缺省空串）
- [x] `test_phase15.py`：组合根 `_write_checkpoint` 写入实参原值（真会话入检查点元数据）
- [x] `test_entry.py`：CLI fresh 铸会话（经注册表、mode `cli`）且 `astream` 收到；resume 复用
      检查点会话；旧 `"default"` 检查点视作未归属 + 提示
- [x] 既有替身补第 4 参（`test_orchestration.py` / `test_phase14.py` / `test_phase15.py`）；
      既有 resume 用例补 `session_id` 元数据（断言不变量不变）

## 3. 实现（绿）

- [x] `scheduler.py`：`CheckpointFn` / `DoneFn` 类型别名 + 2 调用点透传
- [x] `runtime.py`：`_checkpoint` / `_finalize` / `_write_checkpoint` 接 session 实参原值
- [x] `entry.py`：`_task` fresh 铸会话 / resume 复用（含旧占位值归一）+ `_stream_task` 尾参透传

## 4. 门禁与收口

- [x] 四门禁（直连二进制）：`ruff check` / `ruff format --check` / `pyright` 0-0-0 / `pytest -q`
- [x] `openspec validate 2026-10-11-0190-checkpoint-session-attribution`
- [x] 手工归档（delta 合 canonical，断言 0 行丢失 / 0 Scenario 标题丢失）
- [x] `doc/04-testing/test-cases.md` 新 TC 节 + 基线 bump；台账 E127（`known-risk.md` §1）
- [x] 单次提交 `feat(orchestration): …`
