# Design 0190 — 检查点会话归因 + task 路径会话接线

## D1 · 回调签名扩展（CheckpointFn / DoneFn 加第 4 参）

```
CheckpointFn = Callable[[str, "list[SubtaskOutcome]", Plan, str], None]
DoneFn       = Callable[[str, "list[SubtaskOutcome]", Plan, str], None]
```

- 第 4 参 `session_id: str`（发起方会话标识，空串 = 未归属——与 `astream` / `Loop.remember`
  既有口径同构）。
- 调用点两处（`scheduler.py` `astream` 内）：波次收拢 `self._checkpoint(task_id, outcomes, plan,
  session_id)`；终态 `self._on_done(task_id, outcomes, plan, session_id)`。两处 `session_id`
  均为 `astream` 形参，天然在作用域内——**不加新状态、不加新字段**。
- 组合根闭包 `_checkpoint` / `_finalize` 加同名第 4 参（带缺省 `""`，容错直调），透传至
  `_write_checkpoint(..., session_id=…)` ⇒ `create_checkpoint(task_id, session_id, …)` 用实参
  原值。**不再出现字面量 `"default"`**。
- 测试替身（`test_orchestration.py:526` / `test_phase14.py:166` / `test_phase15.py:315` 的
  3 参 lambda/函数）补第 4 参——签名契约变更，替身同步属预期。

## D2 · CLI task 入口会话接线

- **fresh**：`_task` 在无 `--resume` 时经共享注册表铸会话
  `SessionRegistry(path=_state_path("conversations.json")).create("cli")`（与 `run` CLI
  `entry.py` `_run` 的 `api.create_session("cli")` **同注册表、同 mode**；不建 UIAPILayer——
  `task` 入口不需要 UI 装配，直接用注册表，避免第二次 `build_runtime`）。
- **resume**：取最新检查点的 `checkpoint.session_id` 元数据（`Checkpoint` dataclass 既有字段）；
  归一规则：`sid and sid != "default"` ⇒ 复用；否则（空 / 旧占位值）⇒ 未归属（传空串）+
  stderr 提示「检查点未携带会话标识（旧版检查点），子任务轨迹归全局层」。
- `_stream_task` 增尾参 `session_id: str = ""`，恒以关键字透传
  `orchestrator.astream(..., session_id=session_id)`——空串路径与既往**逐字一致**
  （`_run_subtask` 空则不传第二实派的既有分支不变）。
- **不迁移**旧数据：`"default"` 是既有检查点的既成事实，视作未归属即逐字兼容。

## D3 · 「最新检查点」读取

本 change 不动 `cps[-1]` 的文件序取法（`_recover_incomplete`/`restore` 的 ts 序对齐属
change `0191`，同批下一条）；`--resume` 仍取 `list_checkpoints` 末元素。两个 change 的
改动点互不重叠。

## D4 · 已验证的不变量

- REPL `/task`（`api.run_task`）与 Web 任务入口已传 `session_id` ⇒ 本 change 后其检查点
  从 `"default"` 变为真会话——**纯修正**（元数据从谎言变真话），无消费方依赖 `"default"`
  字面值（全仓 grep 无 `== "default"` 判据；`test_durability_crash.py` / `test_phase15.py`
  中 `"default"` 仅作 create 时的**入参字面值**，非读取断言——入参面本 change 后由生产方
  写真值）。
- `durability` 存储层零改动：`Checkpoint.session_id` 字段、JSONL 序列化、`restore` 的
  ts 排序均已有。

## D5 · 风险

- 签名变更是**破坏性接口变更**（CheckpointFn 实现方须补参）——全仓实现方仅组合根一处 +
  测试替身三处，影响面已枚举；`DoneFn` 同理。
- CLI fresh 铸会话会在注册表落一条新记录（`conversations.json`）——与 `run` 入口同构，
  `session list` 可见，属设计内行为（cli-ops delta 明文）。
