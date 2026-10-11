# Design 0214 — 主循环会话轮级检查点

## D1 落点 = `DefaultLoop` 的可选闭包参（loop **不 import** durability）

`turn_checkpoint: Callable[[str, str, str, bool], None] | None`（`(trace_id, session_id, goal,
done)`），与 `turn_observer` / `cold_path` / `act_wrapper` **同型**（组合根注入的可调用）。
loop **不感知**检查点是什么、落哪里 —— 分层不破（架构用例 `:272-283` 钉 loop/constraints
边界口径一致：能力经**闭包注入**，不经 import）。

## D2 两个写点在哪儿（不是三个、不是逐步）

| 写点 | 位置 | 载荷 | 理由 |
|---|---|---|---|
| 轮首 | `astream` 中 `perceive` + `_load_pinned_notes` **之后** | `done=False` | 用户消息**已进**转录（`perceive` 内的 `_append_transcript`）⇒ 与转录序一致；`_load_pinned_notes` 是**读**，不产生在途写入 ⇒ 写点置于其后，保证「已开始」的语义在**所有**前置读之后 |
| 轮末 | `remember` **之后** | `done=True` | 成功路与 `limit_reason` 终止路**都**到达此处（`remember` 在分支之外）⇒ 终止轮也被正确标记完结 |

**不逐步刷新**：`CheckpointStore._persist` 每次 `put` **全量重写**整个 JSONL ⇒ 每步写是
O(n²) 且把「一步」的成本放大为数 MB I/O。轮级两写点已足够回答「哪轮被打断」；
**检查点数量的增长**由 `0208` 的保留策略（`durability.retention.*`）兜 —— 本 change 的
轮级写入**同样**在写后 `apply` 保留策略（若已配置），否则保留策略会只清编排任务、漏掉轮级，
长跑下无限增长。

**无 try/finally 是**（刻意的）：中途异常 / 被杀 ⇒ 天然留 `done=False` —— 与编排波次回调
同语义（编排器也只在自己的回调点写）。

## D3 独立命名空间 `turn.<trace_id>`（防误接）

`task --resume` 的续跑入口以 task id 寻址。轮级检查点若与编排任务**同命名空间**，一次
`task --resume` 会把「一轮对话」当「一个任务」去 restore + resume ⇒ 语义错位（且 restore
依赖 `state["plan"]`，轮级快照无 `plan`）。

`turn.` 前缀 + 状态里的 `"kind": "turn"` **双标记**：`kind` 是语义真源（呈现分流读它），
前缀是**命名空间守卫**（快照损坏、`kind` 读不出时仍能把它与任务分开 —— 只看前缀即判定
非任务面）。二者**同时**满足才豁免：`kind == "turn"` **或** `task_id` 以 `_TURN_TASK_PREFIX`
开头即视为轮面（与「损坏检查点按未完成处理」的既有降级方向一致：轮面宁可漏一句提示，
**不**产生错的 `task --resume` 提示）。

## D4 组合根闭包（主 loop 专属）+ **晚绑定**

主 loop 在 `runtime.py` 的 `loop = DefaultLoop(...)` 处构造（早于 `checkpoints =
CheckpointManager(store)` 的装配块）⇒ 闭包按**晚绑定**读 `checkpoints` / `retention_policy`
（同 `0202` / ADR-0202 D3 的 `_bench_runner` 晚绑定 `general_agent` 先例：只在本轮**运行时**
读取，届时装配已完成；pyright 对「引用后赋值的外层局部」报 0 错，已探针验证）。

**只注入主 loop**：子 Agent（`_agent_loop`）/ 神兽（`_beast_loop`）/ 宠物（`_pet_loop`）
**不接** —— 会话维度是主 Agent 的门面概念（同 `transcript` 的注入面：`:946-948` 注明「只注入
主 loop」）。轮级检查点的呈现面（启动扫描）本就绑定**用户会话**，子 Agent 轮没有独立的
「续聊」语义。

## D5 呈现分流（`_recover_incomplete` + `Runtime.recover_turns` + `_surface_incomplete`）

- `_recover_incomplete`：扫两遍（第一遍收 `done` 标记与 `kind`），第二遍**跳过轮面** —— 轮面
  **不**交给 `CrashRecovery.restore`（否则会产出 `turn.x` 的续跑句柄 ⇒ 被 `_surface_incomplete`
  渲染成 `task --resume turn.x`，**错的提示比没有提示更糟**）。
- `Runtime.recover_turns() -> list[tuple[str, str]]`：**只读**（`list_checkpoints` + `get_snapshot`）
  ⇒ 零副作用，返回未完结轮的 `(task_id, session_id)`（按 ts 序）。
- `_surface_incomplete`：任务面提示不变；轮面**独立一段**（「⚠ 上次有 N 个中断的会话轮（会话 …）」），
  **不含** `task --resume`。只报 task id 与会话标识（**不回显**轮目标正文 —— 与既有「只报
  task id」口径一致；`goal` 落盘只为**运维可读的本地快照**，不进任何呈现输出）。

## D6 已知局限

1. **无撤销账本** —— `EffectTracker` 的 undo 闭包不可序列化（`entry.py` 既有注记已认）⇒
   轮级检查点**不是**「可回滚的执行态」，只是**在途留痕**；不做假耐久。
2. **`goal` / `done` 快照仅供呈现**，不供重放（恢复语义仍显式，守 P2）。
3. **进程内可见性**：轮级检查点**落盘**、跨进程可读（`checkpoints.jsonl`），故崩溃重启后
   启动扫描**能**呈现；但**运行中**另一个进程写的轮级检查点不会被已运行的 serve 看见
   （同 `BenchmarkRegistry` / `skills.json` 先例）。
4. **不逐步刷新** ⇒ 被杀时最多丢「轮内进度」，只保留「这轮在途」这一事实（见 D2）。
5. **保留策略缺席时无界增长**：`loop.turn_checkpoint` 开而 `durability.retention.*` 未配 ⇒
   每个轮级两行检查点，长跑无限增长（文档化；`0208` 提供兜底手段）。
