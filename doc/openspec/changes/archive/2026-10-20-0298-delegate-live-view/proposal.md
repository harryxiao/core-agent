# 0298 — 前台委托子 Agent 的实况标签与只读交互视图

## Why

用户反馈：`tools.delegate` 启动子 Agent 后，聊天区下方**没有** `main` + 子 Agent 标题标签，
无法切换查看子 Agent 的交互内容。

原因：0294 的标签栏只消费 `TaskScheduler` 的 `task.subtask_*` 事件；`tools.delegate` 走
`Runtime._dispatch`，不经过编排器，子 Agent 的整个生命周期对父事件流**不可见**。主 loop
在动作批次里同步等待 `profile.loop.arun(...)`，期间不产出任何事件；用户只能看到主轮卡住，
子 Agent 的进度、收尾与失败都无呈现面。

## What Changes

- `DefaultLoop` 在动作批次执行期间 SHALL 提供**事件侧信道**：工具处理器可把事件写入
  `ContextVar` 持有的队列，循环**边执行边外发**，且 SHALL 保证侧信道事件先于对应动作的
  `action_completed` / 终态。
- `Runtime._dispatch`（前台 `tools.delegate`）SHALL 产出三条生命周期事件：
  `agent.started`（agent_id / agent / title）、`agent.progress`（白名单字段）、
  `agent.completed`（ok / 有界 reply 节选）。异常路径 SHALL 先落 `ok=false` 的
  `agent.completed`（只含异常类型名）再向上抛，由既有工具错误面兜底。
- 子 Agent 进度 SHALL 按**字段白名单**裁剪（与编排层 `_PROGRESS_FIELDS` 同口径）：
  `action_started` / `action_completed` / `step_completed` / `loop.compacting` /
  `loop.compacted`；表外事件（含思考增量、回复增量）SHALL NOT 外发。
- TUI 与 Web SHALL 在 `main` 之后追加 `Agent · <标题缩写>` 标签；点击 SHALL 切换到该
  Agent 的**只读**详情（状态 / 里程碑 / 回复节选），点击 `main` SHALL 返回主视图且主时间线
  逐字不变。
- 无订阅方（`arun` / 后台 `tools.delegate(background=true)`）SHALL 保持原路径与事件面
  逐字不变：前台委托才走 `astream` 中继。
- 新一回合开始 SHALL 清空上一回合的委托标签（Web 由 `agent.reset`；TUI 由下一任务/会话
  复位）。

## Non-goals

- **后台委托的实时中继**：`BackgroundAgentRegistry` 仍只在终态投递通知；本 change 不把后台
  子 Agent 的事件接入父流（登记为局限 / 后续）。
- 不接子 Agent 的**原始消息流**（`reply_delta` / 思考 / 完整工具输出）：只转发白名单字段。
- 不新增会话通道：输入框仍只对主 Agent 生效；子 Agent 视图只读。
- 不改 `tools.delegate` 的返回值、超时、工作树隔离、权限判级与委托深度护栏。
- 不为 `arun` 路径新增事件，不改变既有 `loop.*` 事件类型与载荷。

## Impact

- 代码：`src/core/loop/protocol.py`（`current_event_sink`）、`src/core/loop/default.py`
  （动作批次侧信道）、`src/core/runtime.py`（`agent.*` 发射与白名单中继）、
  `src/core/ui/repl.py`（标签/折叠块/焦点复用）、`frontend/src/lib/taskview.js` +
  `App.svelte` + `Chat.svelte`（委托模型与事件路由）。
- 规格：`ui` ADDED「前台委托子 Agent 实况视图」。
- 测试：新增 `tests/test_agent_live_events.py`、`tests/test_repl.py` 委托标签用例、
  `frontend/src/lib/taskview.test.js` 委托模型用例。
- 文档：ADR-0288、`coding-plan/known-risk.md` E234、`doc/04-testing/test-cases.md` §211、
  `doc/03-interfaces/ui-interface.md` 与 `doc/03-interfaces/loop-interface.md`。
