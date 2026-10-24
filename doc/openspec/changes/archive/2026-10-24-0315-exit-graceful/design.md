# Design — TUI 优雅退出 `/exit`（0315）

## 1. 目标与不变量

**目标**：空闲时 `/exit` 先让本会话的**轮末后台收尾链**收束（技能反馈 + 记忆压实/遗忘），
再正常退出；等待有界，超时/失败不挂死。

**不变量**：

1. Ctrl+Q / Ctrl+C 立即退出语义逐字不变（change 0314）。
2. 有在途轮次 ⇒ `/exit` 拒绝并提示，不退出、不排队、不放弃本轮。
3. 等待有界：复用 `DefaultLoop._post_turn_wait_timeout`（缺省 120s），零新配置键。
4. 收尾失败 / 超时 ⇒ 明示后**仍**正常退出（`app.exit()`，退出码 0）。
5. TUI 内既有命令、呈现、审批语义逐字不变；`/exit` 不接受参数。

## 2. 事实与缺口

| 写入面 | 时机 | 退出时是否可能未完成 |
|---|---|---|
| 转录追加 | 轮内 `loop_finished` 之前（`_append_transcript`） | 否（同步；文件原子提交） |
| `remember`（episodic 等） | 轮内 `loop_finished` 之前（`default.py:949`） | 否（同步；`backend._persist` tmp + `os.replace`） |
| 技能反馈 / 沉淀 | 轮末后台 task（`_notify_turn`） | **是**（`_schedule_post_turn`，change 0296） |
| 会话压实 / 遗忘 | 轮末后台 task（`_maintain` → `memory.compact` / `forget`） | **是**（同上，可含模型往返） |

后台链在 `loop_finished` 之后挂出，TUI 不等待；0314 的 `_close_loop` 取消残留 task、守护
线程随进程终止 ⇒ 退出瞬间在途的后台收尾被放弃。数据不会损坏（原子写），但收尾未完成。

## 3. 方案

### 3.1 循环层公开接缝

`DefaultLoop` 已具备有界等待原语 `_await_post_turn(timeout, trace_id)`（change 0296）。
新增公开包装（不改私有实现）：

```python
async def flush_post_turn(self, *, timeout: float | None = None) -> bool:
    """等待本会话轮末后台收尾链收束；None ⇒ 用既有 `_post_turn_wait_timeout`。"""
    wait = self._post_turn_wait_timeout if timeout is None else timeout
    return await self._await_post_turn(timeout=wait)
```

- 无在途 task ⇒ `True`（立即返回）。
- 超时 ⇒ `False`，且**不取消** task（既有 `shield` 语义）；随后进程退出时由
  `_close_loop` 清理。
- trace 留痕沿用 `_await_post_turn` 的 `post_turn_timeout`。

### 3.2 API 层委托

```python
async def flush_post_turn(self, session_id: str) -> bool:
    self._require_session(session_id)
    flush = getattr(self._loop, "flush_post_turn", None)
    if not callable(flush):
        return True          # 自定义 loop 无该接缝 ⇒ 视为无在途收尾
    return bool(await flush())
```

鸭子类型而非扩展 `LoopPlugin` Protocol：该接缝只服务 UI 退出，其他 loop 实现无义务提供。

### 3.3 TUI 命令

- 真源 `_COMMANDS` 末尾新增 `_Command("/exit", "保存会话记忆后退出")`（浮层可见）。
- 分发顺序：**焦点命令之后、忙态检查之前**插入 `_handle_exit_command(text)`——
  它自己检查忙态以给出专用提示（通用忙态提示不含退出语义）。
- 空闲分支：置忙态（防重入、收尾窗口拒收输入）→ `run_worker(self._exit_gracefully())`。
- `_exit_gracefully`：

```python
self._add(Static("正在保存会话记忆…", classes="hint"))
try:
    settled = await api.flush_post_turn(self._session_id)
except Exception:          # noqa: BLE001 — 收尾失败不阻断退出
    settled = False
self._add(Static("会话记忆已保存，退出" if settled else "记忆收尾超时（已尽力保存），退出",
                 classes="hint"))
self.exit()
```

- 带参 `/exit x` ⇒「/exit 不接受参数」，不退出。
- 忙态 ⇒「本轮进行中：等本轮结束后再 /exit，或 Ctrl+Q 立即退出」，不退出。

## 4. 为什么不用其它方案

| 方案 | 否决理由 |
|---|---|
| `/exit` 里调 `api.compact(session_id)` | 压实锁非阻塞：后台维护正在跑时直接返回 `None`（恰恰是要等的那次）；并可能与维护链重复调用 |
| 在 `_end_turn` 里自动挂「退出待办」 | 隐式延迟退出，用户已输入 `/exit` 却继续接收输入，状态不可见 |
| `_close_loop` 统一等待后台链 | 会把 0314 修掉的「退出随在途工作增长」重新引入 |
| 无限期等待收尾 | 与「优雅但不挂死」冲突；Ctrl+Q 虽是逃生口，但 `/exit` 不应需要二次操作 |

## 5. 测试策略

- **循环层**：有在途后台链 ⇒ `flush_post_turn()` 等其收束后返回 `True`；等待上限 0.1s +
  阻塞观察者 ⇒ 在 1s 内返回 `False`，且 task 未被取消；无在途 ⇒ 立即 `True`。
- **API 层**：委托到 loop 并透传布尔；未实现该方法的 loop ⇒ `True`；未登记会话 ⇒
  `UI_SESSION_NOT_FOUND`。
- **TUI**：`/exit` 空闲 ⇒ 调用 `flush_post_turn` 后 `app._exit is True`；超时 ⇒ 仍退出且
  时间线含超时文案；忙态 ⇒ 不调用、不退出、提示专用文案；带参 ⇒ 不退出；浮层命令清单
  含 `/exit`。
- **反证**：① 去掉 `flush_post_turn` 调用（直接 `exit()`）⇒ 空闲用例红；② 忙态检查删除 ⇒
  忙态用例红；③ 超时文案恒为「已保存」⇒ 超时用例红。

## 6. 已知局限

- `/exit` 等待期间用户仍可按 Ctrl+Q 强制退出（此时收尾可能被放弃）—— 与 0314 逃生语义一致。
- 只覆盖 `DefaultLoop` 的后台收尾链；自定义 loop 无该接缝 ⇒ 视为无在途收尾。
- 退出前不额外写「会话结束」记录，也不强制一次 `compact`：压实/遗忘由既有关闭节拍决定。
- 计划/工具审批挂起时输入仍先走 y/n 分流，`/exit` 需先决断或 Ctrl+Q。
