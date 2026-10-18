# Design 0279 — 后台任务跨重启登记

## D1 持久化始终开启（runtime 面），注册表默认保持纯内存

生产组合根以 `BackgroundAgentRegistry(state_path=$CORE_STATE_DIR/background-tasks.json)`
构造；`state_path=None`（缺省）⇒ 不读写任何文件，既有直接构造（含全部既有测试）逐字不变。
与 `ProcessRegistry`（change 0259）同口径：**元数据登记**不改变执行语义、不放宽权限，
故不设配置开关；真正有后果的动作（重入队）由独立工具 + 审批门控制。

## D2 落盘格式与有界性

- 文件 `background-tasks.json`：`{"version": 1, "tasks": [...]}`。
- 写：同目录 `.{name}.{uuid}.tmp` → `fsync` → `os.replace`，`0600`；写失败告警**一次**
  （"后台任务登记无法落盘（仅本进程内有效）: <文件名>"），不阻断主循环。
- 读：文件缺失 ⇒ 空；坏 JSON / 结构不符 ⇒ 告警一次并按空登记处理；单条非法记录跳过。
- 有界：按 `started_at` 保留最新 `MAX_PERSISTED = 64` 条（加载与写入两侧同口径）。
  运行中上限仍是 8，`interrupted` 不占运行名额。
- 触发写入：`spawn`、每次落终态（done / failed / cancelled / 被中断）。

## D3 脱敏与字段取舍

`task` / `error` 落盘前经 `core.memory.extract.redact_secrets` 处理，并分别截断到
120 / 200 字符。`session_id` 落盘（重入队需要恢复到原会话归属），但它不进
`info()`（对模型仍不可见）。**不持久化 `reply`**：完成结果已由完成通知投递；重启后
`tools.tasks` 只保留状态与错误，避免把子 Agent 输出正文长期留在状态文件。

## D4 重启映射：`running → interrupted`

加载时把落盘的 `running` 记录改为 `interrupted`，`finished_at` 保持 `None`，
`error = "进程重启导致中断"`。该状态是**终态**：不可取消（无 `asyncio.Task`）、不产生
完成通知（通知队列是会话内的即时投递，重启后重放会造成每次启动都重复提醒）；
可见性由 `tools.tasks` 提供。重入队不按原 `task_id` 复用，而是新 `spawn` 得到新 id
（原 id 的终态保持不可变）。

## D5 重入队：`tools.task_retry`

- 入参：`task_id`。可重入队状态：`interrupted` / `failed` / `cancelled`；
  `running` ⇒ "任务仍在运行，无需重入队"；`done` ⇒ "任务已完成，不自动重入队"；未知 id ⇒
  `ok=false`。
- 路由：用注册表内**原任务正文**（进程内是未脱敏原文；跨重启是脱敏副本）重新
  `MultiAgentRouter.match` —— 不按持久化的 `agent_id` 直接取 loop，因为配置可能在重启后变化。
- 成功后 `spawn(..., session_id=原会话)` 并返回新 `task_id`；达到运行中上限时返回
  `BACKGROUND_TASKS_FULL` 结构化失败。
- 安全：工具 id 词元 `{task, retry}` 不命中只读/写词元 ⇒ `HIGH_RISK`（审批门）；
  coeffect `task:write` 显式注册、`reversible=False`。只挂主工具面（子 Agent 结构上不可见）。
- 已知局限：跨重启重入队使用的是**脱敏后**的任务正文，若原任务正文含密钥形态子串，
  重入队的任务描述会带 `REDACTED`（原值本就不应进入状态文件）。

## 反证

1. 移除加载时的 `running → interrupted` 映射 ⇒ 重启可见性用例红（状态仍是 running）。
2. 移除落盘前 `redact_secrets` ⇒ 密钥形态 canary 出现在状态文件（用例红）。
3. `tools.task_retry` 接受 `done` / `running` ⇒ 状态守卫用例红。

## 已知局限

- 多进程共用 `CORE_STATE_DIR` 时，另一进程启动会把本进程运行中的任务误标 `interrupted`
  （单用户 CLI 视为重启；跨进程运行锁不在本 change 范围）。
- 文件最多 64 条，超出淘汰最旧记录；被淘汰任务不再可查/可重入队。
- 重启后不恢复 `reply`；`tools.tasks` 的 `reply` 为空是预期行为。
