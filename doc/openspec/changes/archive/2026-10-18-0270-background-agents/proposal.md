# Proposal 0270 — 后台子 Agent、完成通知与模型侧任务清单（Claude Code 对齐建议 4）

## Why

`tools.delegate` 是**阻塞**语义：主 loop 发起委托后停在同一动作上等子 Agent 跑完
（`timeout_s=600`），期间不能继续推理、不能并行推进其他子任务；而子 Agent 的完成结果
只能作为该次工具调用的返回被看到一次，**跨轮不可见**。对照 Claude Code 的 Agent 工具：
它支持后台运行、完成时把「任务完成」推回主对话，并给模型一份可自查的任务清单。三者
缺失导致：

1. 长委托把整轮串行化，模型无法「先起一个调研、同时写代码」；
2. 子 Agent 完成后若主 loop 已切换到别的话题，结果无人消费（只在工具结果里）；
3. 模型没有「我刚起了哪些任务、跑到哪了」的自省面，只能盲目等待或重复委托。

## What Changes

- 新 `src/core/orchestration/background.py`：`BackgroundAgentRegistry` —— 有界（默认 8）
  的后台委托注册表；`spawn(loop, task, agent_id, session_id)` 立即返回 `task_id`；
  完成 / 失败 / 取消落终态并按**会话**记录一次性完成通知。
- `tools.delegate` schema 增可选 `background: bool = false`：为真时立即返回
  `{ok, task_id, agent, status:"running"}`，不阻塞主 loop；为假（缺省）路径**逐字不变**。
- 新工具 `tools.tasks`（只读）：`list` / `status` —— 模型侧任务清单。`coeffect=task:read`，
  权限**精确工具 id 豁免**判 `read`（不放宽为词表/前缀）。
- loop 新增 `notices_consult` 注入点与 `LoopContext.notices` 独立字段：轮首取用本会话的
  后台任务通知，planner 以**独立系统块**（「后台任务通知：」）注入；未注入 / 无通知 ⇒
  提示词逐字不变。
- 组合根：创建注册表、接 `delegate(background=…)`、注册 `tools.tasks` 与 `task:read`
  coeffect、只给**主 loop** 注入 `notices_consult`（子 Agent 不取，避免抢走通知）。

## Impact

- 代码：`src/core/orchestration/background.py`（新）、`src/core/orchestration/__init__.py`、
  `src/core/runtime.py`、`src/core/loop/{default,protocol,planner}.py`、
  `src/core/permission/policy.py`。
- 测试：新增 `tests/test_background_agents.py`；`tests/test_phase13.py` 的工具面集合补
  `tools.tasks`。
- 规格：`orchestration` ADDED「后台委托与完成通知」、`loop` ADDED「轮首通知注入」、
  `permission` MODIFIED「分级权限体系」（任务清单精确 id 豁免）。
- 兼容：`background` 缺省 false ⇒ 既有阻塞委托与工具面行为逐字不变；`notices_consult`
  缺省 `None` ⇒ `ctx.notices` 恒空、提示词不变；`tools.tasks` 为新增只读工具。

## 不做（明确边界）

- 不做后台进程级持久化（注册表随进程退出；`tools.process` 的后台**命令**是另一条线）。
- 不做通知的主动打断（不在主 loop 空闲时唤醒模型；通知在**下一轮**轮首投递）。
- 不做跨会话 / 跨进程任务查询；不提供终止后台子 Agent 的工具（取消留给进程退出）。
- 不把子 Agent 写入并入父 `EffectTracker`（既有边界，见 ADR-0257 局限①）。
- 不改 `tools.delegate` 的深度护栏与 `agent:delegate` coeffect 语义。
