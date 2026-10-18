# Design 0270 — 后台子 Agent、完成通知与模型侧任务清单

## D1 注册表归属 L4，不塞进 L1 工具面

后台任务驱动的是**子 Agent 的 loop**（跨边界能力），不是 OS 进程 —— 与 `tools.process`
的 `ProcessRegistry` 语义不同。故注册表放 `core/orchestration/background.py`，由**组合根**
在主工具面注册 `tools.tasks`；子 Agent 的工具面（不含 delegate / tasks）结构上既不能起
后台任务也不能查清单，维持「子 Agent 不可再委托」的既有结构性保证。

## D2 完成通知：轮首独立块 + 按会话一次性取用

三条候选：① 新 `LoopEvent` 推给 UI；② 写进记忆；③ 轮首注入块。选 ③：

- ①会让 `astream` 的七类事件契约变化，且 UI 消费不代表**模型**能看到；
- ②污染进化轨迹（通知是瞬态协调信号，不是知识）；
- ③与既有「既往失败教训」注入同一形状：`notices_consult: Callable[[str], str] | None`
  （入参 = 会话标识），产物写入 `LoopContext.notices`，planner 出独立块
  「后台任务通知：」；缺省 `None` ⇒ 零调用、提示词逐字不变。

`drain_notices(session_id)` 是**取走**语义（一次性）：同一完成事件只投递一次，避免每轮
重复占用上下文预算。两个消费方（主 loop / `tools.tasks`）分离 —— 清单只读状态，**不**
清空通知。

## D3 有界

| 维度 | 上界 | 行为 |
|---|---|---|
| 运行中后台任务 | 8 | 超限时 `delegate(background=true)` 返回 `{ok:false, error}`，**不**排队 |
| 每会话待投递通知 | 32 | 超出丢弃最旧（保留最近完成） |
| 单轮渲染通知条数 | 10 | 取最近 10 条 |
| 单行通知正文 | 400 字符 | 任务摘要 120 + 回复预览 200 + 状态/标识 |
| 单任务保留回复 | 4000 字符 | `tools.tasks status` 返回上界 |

## D4 状态机与取消

`running → done | failed | cancelled`（终态不可变）。

- 子 Agent `LoopResult.failed=True` ⇒ `failed`，`error` 记「子 Agent 报告失败」；
- handler 抛错 ⇒ `failed`，`error` 记异常类型名（不含消息正文 —— 避免把任意异常文本
  带回主对话）；
- 进程退出 / loop 关闭取消 `asyncio.Task` ⇒ `cancelled`；`CancelledError` **原样重抛**，
  但 `finally` 仍落终态与通知（进程即将结束，通知通常无人消费）；
- 每个任务强引用保存在注册表（`_tasks`）直到终态，避免 `Task was destroyed but it is
  pending` 与「异常从未被取回」告警。

## D5 权限：精确工具 id 豁免，而不是新增只读词元

`PolicyEngine.classify` 按**完整词元**判级；`tools.tasks` 的词元是 `{tools, tasks}`，
无只读词。两条路：① 把 `tasks` 加入 `_READ_TOKENS`；② 对工具 id 做字面量豁免。

选 ②：新增 `_BACKGROUND_TASKS_TOOL = "tools.tasks"`，与 `_DELEGATE_COEFFECT` 同一纪律
（字面量、不放宽为前缀/词表）。理由：把 `tasks` 设为只读词会让未来任何含该词元的动作
（如 `tasks.purge`，`purge` 不在写词表）静默降级为只读 —— 这正是 ADR 里反复出现的
deny-by-default 破口。清单工具只读、无参数面可指向文件，豁免面可控。

## D6 默认行为不变

- `tools.delegate` 的 `background` 缺省 `false` ⇒ 请求体与阻塞路径逐字不变；
- `notices_consult` 缺省 `None` ⇒ `ctx.notices` 恒空 ⇒ 提示词与引入前逐字相同；
- `tools.tasks` 是**新增**只读工具（与 `tools.process` 同口径：生产工具面可达、
  默认不出 MCP 暴露面，因 `task:read` 不在 `_DEFAULT_EXPOSED_COEFFECTS`）；
- 无新配置键、无新三方依赖。

## D7 为什么不在主 loop 里轮询

完成通知只在**轮首**取用：主 loop 运行中不主动打断（模型正处在推理 / 动作中途，插入
系统块会破坏消息序）。模型若需要在轮内得知进度，用 `tools.tasks status` 主动查 —— 这
正是清单工具存在的理由。claude-code 的「任务完成推回」同样发生在下一轮输入边界。
