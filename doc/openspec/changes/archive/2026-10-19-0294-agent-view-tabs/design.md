# 设计 — 0294 主/子 Agent 视图标签栏

## D1 TUI：标签栏是既有焦点视图的可见入口

- `#footer` 内、`#input-box` 上方新增 `Horizontal(id="task-tabs")`，初始 `display:none`。
- `_TaskTab(Static)`：`markup=False`、`can_focus=False`（点击不抢输入框焦点），`on_click` 调
  `ReplApp._select_agent(sid)`；active 用 CSS 类。
- 标签模型 `_task_tabs: list[(sid, goal)]` 与 widget 注册表 `_open` **分离**：`_open` 跨任务保留
  （既有 `/focus` 的 widget 身份绑定依赖它），`_task_tabs` 只表示当前/最近一次任务。
- `task_started` 清空标签并回主视图；`subtask_started` upsert 并刷新；`subtask_completed` 刷新状态；
  `task_finished` / `task_failed` 保留终态标签与当前焦点；`/resume` 清空。
- 点击子任务块：`_SubtaskBlock(Collapsible)` 覆写 `_on_collapsible_title_toggle`，先 `super()`
  保留展开/收起，再 `_select_agent(sid)`。`CollapsibleTitle` 的点击会 `stop()` 并 post `Toggle`，
  这是唯一可拦截点；键盘 Enter 也会进入焦点视图（有意）。
- 标签只读、无新数据源：goal 来自 `subtask_started`，状态来自开工/收尾事件。

## D2 Web：状态上提 + 纯 reducer

- `App.svelte` 持有 `taskState = {tasks, lastTask, selected, notice, error}`；`TaskPanel` 不再自持
  任务列表，只保留输入/忙态/传输错误，事件交给 `onEvent`。
- `frontend/src/lib/taskview.js` 为纯函数模块（无 DOM、无 runes）：`reduceTaskEvent`、
  `selectTaskAgent`、`taskTabModel`、`activeAgent`、`abbreviateGoal`、`replyExcerpt`、
  `milestoneLine`。便于 `node --test` 覆盖。
- 选中键 = `taskId + subtaskId`（sid 仅在任务内唯一）；非法选择 fail-closed 回 main。
- 收尾：`task_finished` 用 `outcomes` 回填终态，任务移出 `tasks` 但保留 `lastTask` 快照与当前选择；
  `task_failed` 同样保留快照；`task_started` 或会话切换才重置。
- `Chat.svelte` 保持挂载：主时间线与子任务详情用 `display:none` 切换，**不 unmount**（流式与本地
  状态不丢）；`TaskTabs` 位于内容区下方、输入框上方；输入框仅对主 Agent 生效。
- 只读边界：详情只呈现 `task.*` 已有字段（acceptance / milestones / reason / bounded reply），
  不接子 Agent 消息流，不使用 `{@html}`。

## 被拒方案

- 接子 Agent 消息流 / 允许发消息：无数据源与协议，需改动调度器与并发语义，另立 change。
- 自动聚焦正在运行的子 Agent：打断主视图阅读；只自动展示标签。
- 新增后端 `/task` 快照端点：当前单消费者 SSE 足够，收尾用 `outcomes` 即可重建。
- 全局 `.svelte.js` store：会话切换需要同时重置 Chat/TaskPanel/标签，`App` 已是会话真源，
  上提更直接且避免 second source。

## 局限

- TUI 标签只为**已开工**子任务创建（无折叠块时保持「不延迟聚焦」不变量）；Web 可展示 pending。
- 标签主题缩写有界（14 字符），长目标会被截断；TUI 标签多时横向溢出/换行，不做分页。
- 收尾快照是静态的，不再更新；只保留最近一次任务。
- 不展示子 Agent 的思考、流式正文或完整对话；结果只有 ≤600 字事件节选。
- 不提供键盘标签切换（TUI 仍可用 `/focus`、`/main`、`F2`）。
