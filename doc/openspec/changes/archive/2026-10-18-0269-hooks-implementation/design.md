# Design 0269 — 钩子实现

## D1 清单语法：扩展 YAML 子集，而不是改写契约

规格的声明面要求 `hooks.entries` 是**清单**（`doc/02-modules/hooks.md` §6 的示例），而
`_parse_yaml_subset` 此前明确「不含列表」。两个选项：

- 改规格为映射形态（如 `entries.<name>: {...}`）：实现省事，但偏离已归档契约，且操作者
  无法按顺序表达同事件多钩子；
- 扩展解析器：支持块序列、行内 `[...]` / `{...}`，并让 `_dump_yaml` 对称输出（否则
  `write_patch` 会把清单写成 `str(list)` 并破坏配置）。

选后者。解析器仍拒绝锚点 / 多行块；新增能力有独立单测（含 round-trip）。
`hooks.entries` 依然**只**从 `config.yaml` 读取。

## D2 接缝：动作前链 / 观察者链可等待

`tool.before` 规格要求挂在既有 `middlewares` 上。中间件当前是同步调用；外部命令钩子若
同步 `subprocess.run` 会阻塞事件循环最长 `timeout_s`。故把 `_apply_middlewares` 与
`_notify_action_result` 改为可等待：

```python
Middleware = Callable[[LoopContext, Action], Action | None | Awaitable[Action | None]]
ActionObserver = Callable[[LoopContext, Action, ActionResult], object | Awaitable[object]]
```

`inspect.isawaitable` 判定后 await；既有同步中间件 / 观察者（constraints、pet safety）
逐字不变。

## D3 `turn.before` / `turn.after`：两个同步注入点

`turn.before` 无既有注入点，新增形参（规格已允许）。`turn.after` 既有 `turn_observer` 是
**后台**收尾（可含同步模型调用，`to_thread`，且在 `Tracer.end_trace` **之后**运行）。
钩子要求「每次调用落 trace」，若复用后台观察者，`kind="hook"` 将写入已封口的 trace 并
永不导出。故新增 `turn_after` 形参，在 `loop_finished` 遥测之后、`_end_trace` 之前
`await`；后台 `turn_observer` 保持原语义不变。

这是对 hooks 规格「turn.after 经每轮收尾观察者」的**明确修正**：本 change 的 delta 把该句
改为「每轮收尾的同步注入点（后台 `turn_observer` 不变）」。仍然没有事件总线。

## D4 载荷摘要与 `tool.after` 时延

`tool.*` 只给摘要：正文经 `json.dumps(..., sort_keys=True, default=str)` 后取
`{"chars": n, "hash": sha256[:12]}`。`tool.after` 的 `duration_ms` 由 loop 写入
`ActionResult.duration_ms`（新字段，缺省 0），观察者从结果读取 —— 不改变观察者签名。

## D5 脱敏与子进程边界

- 载荷递归脱敏：字符串先用 `core.memory.redact_secrets`（与记忆同一 over-redact 口径），
  再把运行期登记的密钥明文（`register_secret`）替换为 `<redacted>`；单字符串截断到
  4096 字符，避免超长 input 撑大信封。
- 子进程 argv 不经 shell；环境只保留白名单（`PATH/HOME/LANG/LC_ALL/TZ/TMP*` 与 Windows
  必需的 `SYSTEMROOT/COMSPEC/PATHEXT/USERPROFILE`）。
- stdout/stderr 只 `capture_output=True` 读取后丢弃，**不**进日志 / 记忆 / 对话 / trace。
- trace 只记 `event / command basename / exit / duration_ms / blocked_by`。

## D6 失败语义

- 外部命令退出码非 0 / 回调返回 `False` ⇒ `block`（before 类立即阻断；after 类只留痕）。
- 超时 / `OSError` / 回调抛错 ⇒ 按该条 `on_error`：`block`（缺省）/ `allow` / `warn`。
- `memory.write` 与所有 after 类永不阻断；钩子异常吞掉并留 `kind="hook"` 痕。

## D7 会话边界与 trace 归属

- `session.start` 在 `turn_before` 适配器里幂等触发（同一 `session_id` 一次）。
- `session.end` 由 `HookManager.close()` 在 `atexit` 触发；无显式结束 API 的 UI 也能收尾。
  多会话进程内逐个发；已知局限：进程被强杀时不发。
- hook trace 的 trace_id：turn/tool 事件取 `current_trace_id` ContextVar；`memory.write`
  取 `entry.trace_id`；会话事件无在途 trace ⇒ 管理器开一条短命 `hook.<event>` trace，
  记录后立即封口（保证每次调用仍落 trace）。

## D8 配置访问器

`ConfigManager` 新增 `hooks_enabled()` / `hooks_timeout_s()` / `hooks_on_error()` /
`hooks_entries()`。`timeout_s` 超 60 截断并 `warnings.warn`，非正数回落缺省 5；
`on_error` 集合外回落 `block`；清单项非法（事件名 / command 形态 / match 类型）跳过并告警
（fail-closed：不执行未校验的钩子，但不阻断整机启动）。

## D9 已知局限

1. `memory.write` 钩子在**调用线程**同步执行（`MemoryStore.write` 是同步 API）；操作者应
   把该事件钩子写成快命令。其余事件经 `asyncio.to_thread`，不阻塞事件循环。
2. `session.end` 依赖进程退出；Web/Desktop 长驻进程中的显式会话关闭暂不触发。
3. 同事件多钩子按声明序执行，无权重 / 短路覆盖之外的组合语义。
4. 钩子副作用不可逆（规格明示例外），不纳入 `EffectTracker`。
