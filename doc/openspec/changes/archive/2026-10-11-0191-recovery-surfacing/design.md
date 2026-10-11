# Design 0191 — 恢复呈现接线（启动扫描+呈现，续跑仍显式）

## D1 · 呈现不重执行（P2 守住）

- `resume()` 现状**无 replay 回调**时即纯扫描（`manager.py:123-129`：仅把句柄记入 `_resumed`
  幂等集，`replay is None` 则不执行任何东西）⇒ `runtime.recover()` 本身**零副作用**。
- 本 change **不**给 `resume()` 加 replay 面 —— 呈现=调用 `recover()` 后打印，**绝不**自动
  重新执行未完成任务（用户裁决①：「启动扫描+呈现，续跑仍显式」）。
- 呈现文案：`⚠ N 个未完成任务：`task --resume <id>`` ——只报 **task id**，不回显任务正文 / 记忆 /
  密钥（留痕红线）。

## D2 · 恢复句柄携带 task id（自然载体）

```python
@dataclass
class RestoreHandle:
    handle_id: str
    task_id: str          # 新增：句柄标识其所属任务（呈现「哪些任务未完成」无需旁路扫描）
    checkpoint_id: str
    resume_cursor: str
    degraded: bool = False
```

- 构造点仅 `manager.py:113` 一处（全仓 grep `RestoreHandle(` 唯一）⇒ 破坏性变更影响面最小。
- 放**第 2 位**（紧跟 `handle_id`）：语义上「哪个任务的句柄」先于「哪个检查点」；构造点全用
  关键字，位次变更无实参错位风险。

## D3 · 降级不炸全扫（对齐既有 corrupt 口径）

```python
for cp in checkpoints.list_checkpoints():
    if cp.task_id in done_tasks or cp.task_id in seen:
        continue
    seen.add(cp.task_id)
    try:
        handle = recovery.restore(cp.task_id)
    except DurabilityError:
        warnings.warn(f"任务 {cp.task_id} 无可恢复检查点，跳过", stacklevel=2)
        continue
    recovery.resume(handle)
    handles.append(handle)
```

- 与首轮 `get_snapshot` 的 corrupt 捕获（`runtime.py:1125-1128`）**同口径**：单任务不可恢复 ⇒
  跳过 + 告警，不中断整轮扫描。
- `warnings.warn` 只报 **task id**（不回显正文）。

## D4 · 入口呈现接线（面最小：`serve` + CLI `task`）

- **CLI `task`（新任务）**：`_task` 无 `--resume` 时，`build_runtime` 后调
  `_surface_incomplete(runtime)`。**只在 fresh 路径呈现** —— `--resume` 已是显式续跑动作，
  再报「你有未完成任务」是噪音（呈现的价值在「起新任务时提醒旧任务」）。
- **`serve`**：`_build_ui` 增关键字形参 `surface_recovery: bool = False`，`runtime` 装配成功后
  若为真则调 `_surface_incomplete(runtime)`；**仅 `_serve` 传 `True`** ⇒ `repl`/`app`/`run`
  入口输出面**逐字不变**。
- `_surface_incomplete(runtime)` 助手：

```python
def _surface_incomplete(runtime: Runtime) -> None:
    """启动扫描未完成任务：只呈现不重执行（P2：副作用不自动重放）。"""
    handles = runtime.recover()
    if not handles:
        return
    tasks = sorted({h.task_id for h in handles})
    warnings.warn(f"启动扫描发现 {len(tasks)} 个未完成任务", stacklevel=2)
    print(
        f"⚠ {len(tasks)} 个未完成任务："
        + "、".join(f"`task --resume {t}`" for t in tasks)
        + " 可续跑",
        file=sys.stderr,
    )
```

## D5 · 「最新检查点」对齐 ts 序

- `entry.py:1720`：`latest = cps[-1]`（文件落盘序）⇒ `latest = max(cps, key=lambda cp: cp.ts)`
  （ts 序），与 `CrashRecovery.restore`（`manager.py:102-106` `reverse=True`）**同口径**。
- 正常追加落盘时落盘序 = 时间序 ⇒ 行为**逐字不变**；仅当二者不一致（如时间旅行回填 / 手工改动
  落盘）时才改变取值——**修正**为取真正最新。

## D6 · 已验证的不变量

- `recover()` 的既有测试（`test_phase15.py` `assert runtime.recover() == []`）在空库下仍返回
  `[]`（无句柄、无输出）⇒ 空库静默，不变量保持。
- `RestoreHandle` 的 `degraded` 语义不变（`manager.py` 内回退更早有效快照时置真）。
- 呈现只读：`_surface_incomplete` 不写任何检查点 / 记忆 / 注册表。

## D7 · 风险

- **入口输出面变更**：`serve` 启动在有未完成任务时向 stderr 多打印一行 —— 属本 change 设计内
  （cli-ops delta 明文）；`repl`/`app`/`run` 不受影响（只 `serve` 传 `surface_recovery=True`）。
- **`RestoreHandle` 破坏性变更**：全仓构造点一处 + 测试构造点（若有）已枚举同步。
- **`--resume` ts 序**：仅在落盘序 ≠ 时间序时改变取值，指向「真正最新」。
