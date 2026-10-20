# Design — 0298 前台委托子 Agent 的实况标签与只读交互视图

## 1. 问题链路

```
主 DefaultLoop.astream
  └─ _act(tools.delegate)
       └─ Runtime._dispatch
            └─ profile.loop.arun(...)      ← 整段子循环在此同步等待，父流零事件
```

0294 的标签模型只认 `task.subtask_*`；`tools.delegate` 不产生这些事件 ⇒ 无标签、无详情、
无法观察子 Agent。修复点必须在 `_dispatch` 与父循环之间**加一条事件通道**，而不是给
`arun` 硬塞回调（会破坏三入口的既有协议）。

## 2. 侧信道：`current_event_sink`

`src/core/loop/protocol.py`：

```python
current_event_sink: ContextVar[asyncio.Queue[LoopEvent] | None] = ContextVar(
    "current_event_sink", default=None
)
```

`DefaultLoop.astream` 执行动作批次时：

1. 新建队列并 `set` 到 ContextVar；
2. 把批次执行放进 `asyncio.create_task`，`finally` 写入哨兵 `_ACTIONS_DONE`；
3. 父生成器 `await sink.get()` 循环，**边执行边 yield**，遇哨兵后 `await runner` 取结果；
4. `finally` `reset` ContextVar。

语义保证：

- 侧信道事件**先于**动作结果提交与外发（哨兵在批次的 `finally`，`outcomes` 之后才提交）；
- `arun` 不经过 `astream` ⇒ 无队列、无额外事件，行为逐字不变；
- 嵌套动作批次（子 Agent 自己的 loop）会覆盖 ContextVar，但其 `reset` 恢复父 sink；
  子 Agent 的 `agent.*` 由父 `_dispatch` 的 `on_event` 中继，不依赖嵌套 sink。

## 3. runtime 发射与白名单

`_dispatch` 前台路径：

```python
sink = current_event_sink.get()
agent_id = f"{profile.agent_id}:{uuid4().hex[:8]}"   # 同一画像可并发多实例
_emit("agent.started", {agent_id, agent, title})
try:
    result = await collect_result(profile.loop.astream(...), on_event=relay)
except Exception as exc:
    _emit("agent.completed", {agent_id, ok=False, reply=f"子 Agent 执行异常：{type(exc).__name__}"})
    raise
_emit("agent.completed", {agent_id, ok=not result.failed, reply=excerpt(result.reply)})
```

- `sink is None` ⇒ 走原 `profile.loop.arun(...)`，既有单测与后台路径零变化。
- `_AGENT_PROGRESS_FIELDS` 是**逐事件字段白名单**：只把编排层既有的五类里程碑字段
  （`round` / `tool_id` / `args` / `ok` / `duration_ms` / `output` / `failed` /
  `elapsed_ms` / `timeout`）写入 `agent.progress.data`；思考、回复增量、表外类型一律丢弃。
- 标题：任务首个非空行、空白折叠、≤60 字符；回复事件节选 ≤4000 字符（工具返回值仍全文）。
- 异常只回显**类型名**，不把任意异常正文带进主对话或 UI。

## 4. 呈现层

TUI（`repl.py`）：

- `_agent_tabs` 与 `_task_tabs` 并列；`_refresh_tabs` 的可见性为 `_task_active or _agent_tabs`；
- 复用 `_SubtaskBlock` / `_open` / `_progress_subtask` / `_set_focus`：`agent_id` 作为
  sid，进度载荷与 `subtask_progress` 同形（`{event, data}`），里程碑行渲染零新代码；
- `agent.started` 建块并 upsert 标签；`agent.completed` 落 ✓/✗ 并补回复节选；
- 新任务 `task_started` 与会话切换清空 `_agent_tabs`。

Web（`taskview.js`）：

- 状态新增 `delegates: []`；`agent.started/progress/completed` 走同一纯 reducer；
- `AGENT_SCOPE = "__agent__"` 作为选择域，`selectTaskAgent` 对委托做 fail-closed 校验；
- `activeAgent` 为委托合成与 `SubtaskDetail` 同形的 `{task, subtask}`（只读）；
- `Chat` 把 `agent.*` 上抛 App；每轮发送前发 `agent.reset` 清空上一轮委托。

## 5. 被拒方案

- **给 `tools.delegate` 增加事件回调参数**：工具 schema 会变，模型可写；且所有工具都要
  感知呈现层。
- **在 `_dispatch` 里直接写 UI**：违反分层；TUI/Web/CLI 三个入口无法共用。
- **把子 Agent 全量事件透传**：会泄露思考/回复增量与完整工具输出，且与「只读详情」的
  字段面不一致。
- **后台委托也实时中继**：后台路径没有父轮次生命周期，事件无宿主；留作后续独立变更。
- **把 `agent.*` 映射成 `task.subtask_*`**：伪造编排事件会污染任务区与会话记录。

## 6. 局限（登记 known-risk E234）

1. 后台 `tools.delegate(background=true)` 仍无实时进度，只有终态通知。
2. 同一次委托内思考与回复增量不外发 ⇒ 只读详情是「里程碑 + 终态节选」，不是完整对话。
3. 进程重启后委托标签不恢复（呈现态不持久化）。
4. 侧信道只在 `astream` 动作批次期间存在；`arun` 调用方永远拿不到 `agent.*`。
