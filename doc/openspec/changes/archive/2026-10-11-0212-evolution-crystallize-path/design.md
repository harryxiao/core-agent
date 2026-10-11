# Design 0212 — 结晶通路：真 runner 注入 + 基准人工注册操作面

## D1 runner 挂 `general` 子 profile 而非主 loop

评测要「真实执行任务」，执行面就必须是**一个 loop**。选主 loop 会引入**递归**：主 loop 的
`_maintain` 触发 `cold_path` → 进化引擎 → `Evaluator` → `_bench_runner` → 主 loop `arun` →
`_maintain` …… 今日仅靠 900s 节拍闸挡住（脆，且闸一松即爆栈风险）。

`general` 兜底子 profile 的 loop 由 `_agent_loop()` 构造，**不接** `cold_path` / `trace_observer`
（`runtime.py:931-965`）⇒ 它跑完一轮**不会**回流冷路径 ⇒ **递归路径结构上不存在**。附带好处：
子 loop 天然 `transcript=None`（样本间无上下文漂移）、不走 `agent_router` 关键词匹配（无非确定性）。

**代价如实记**：基准测的是**子 Agent 形状**（工具面无 `delegate`、无主 loop 的转录/常驻笔记面），
与主 loop 不完全同构。这是「结构上不可能递归」付出的确定性代价，优于「今日靠节拍闸侥幸不递归」。

## D2 门控极性 = OPT_IN（缺省关），不是 GATABLE

`evolution_executor`（`0112`）立下的先例：**能自改代码 / 能烧钱的执行面必须「关得住、且是关着的」**。
runner 一旦注入，评测会**真实调用模型**（token 成本），与 `evolution_executor` 同性质 ⇒ 同极性。
故进 `OPT_IN_MODULES`（`is_enabled` 查询、缺省 `False`），不进 `GATABLE_MODULES`（那是「缺省开、
显式 false 才关」的另一极性）。

**关键语义**：**注册基准不是同意烧 token 的信号**。旗关时即便 `evolution-benchmarks.json` 里
躺着绑定好的基准与基线，`BenchmarkScorer` 拿不到 runner ⇒ 仍判 `freeze` ⇒ 既有 `EVAL_FROZEN`
路径**逐字不变**。这是 fail-closed 的：不开旗，什么都不会发生。

## D3 闭包晚绑定：runner 定义在 `general_agent` 赋值之前

`BenchmarkScorer` 在 `runtime.py:837`（evolution 块内）构造，而 `general_agent` 在
`:1026` 才赋值。Python 闭包**调用时**解析自由变量 ⇒ 只要评测发生在 `build_runtime` 返回之后
（确实如此：评测在冷路径 / `evolve run` CLI），闭包就能取到已赋值的 `general_agent`。
pyright 对「闭包引用稍后赋值的局部名」不报警（已实测 0-0-0）。故**无需**改
`BenchmarkScorer` 的构造签名、无需可变 holder —— 保持接缝 `runners: Mapping | None` 原样。

## D4 `_run_coro`：为什么需要，为什么这么写

执行面是**同步** `Runner = Callable[[dict], Any]`（`evaluator.py:200`），而 loop 的执行入口是
`async arun`。两种接法：

1. `general.loop.run(...)` —— loop 自带的同步薄壳（`default.py:370` = `asyncio.run(arun(...))`）。
2. `_run_coro(general.loop.arun(...))` —— 本 change 选的写法。

选 2 的理由：`run()` 在**运行中的事件循环线程**里必抛 `RuntimeError: asyncio.run() cannot be
called from a running event loop`（`default.py:471-473` 已为此把 `_compact` 挪出事件循环）。
本 change 的所有调用方**今日都无循环**（已逐一核：冷路径经 `to_thread`、`evolve run` 在 CLI 主线），
但评测是**可被未来新调用方复用**的接缝 —— `_run_coro` 把这条边界显式化：无循环 ⇒ `asyncio.run`；
有 ⇒ 单线程池（该线程无循环）兜。**代价**：多 6 行 helper；**收益**：不把 `RuntimeError` 当评测结果
抛给 `Evaluator`。

## D5 CLI 操作面免 runtime（数据面与执行面分离的落地）

`BenchmarkRegistry` 的落盘是**数据面**（`runtime.py:817` 已论证：注册基准是数据入库）。操作面直接
构造**同源** registry（`_state_path("evolution-benchmarks.json")`）读写落盘，**不 `build_runtime`**
—— 理由同 `_notes_store` / `_build_skill_library`：注册不需要模型、不需要凭据、不需要装配，
装配反而把「配置坏了就注册不了基准」的脆弱性引进来（ADR-0153 决策①的同一取向）。

## D6 已知局限（如实记）

- **运行中 runtime 重启才见新注册**：`BenchmarkRegistry` 在组合根构造期一次性 `_load()`；CLI 注册
  后已在跑的 `serve` 不会热加载（同 `skills.json` 先例）。跨进程可读是**下次装配**时兑现。
- **样本串行、跑在维护线程**：`BenchmarkScorer` 逐样本串行调用（`evaluator.py:245-253`），N 个样本
  × 每样本一整轮 loop ⇒ 冷路径可能出现分钟级阻塞（冷路径本身在维护线程，不卡主循环）。样本数以
  **小**为宜（门控 + 文档化，不做并行 —— 并行会与 `Evaluator` 的 Semaphore 语义纠缠）。
- **`_crystallize_plugin` 仍不产真插件**：本 change 只打通「评测产出留出分 → 判 publish/rollback」，
  发布动作仍是登记（`plugin_ids.py:11-18` 有意裁决，另立 change）。
