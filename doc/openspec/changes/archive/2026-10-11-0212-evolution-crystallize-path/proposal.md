# Proposal 0212 — 结晶通路：真 runner 注入 + 基准人工注册操作面

## 为什么

六能力走查确认：「技能 → 插件」结晶（`evolution`）**上半场通、下半场被 freeze 卡死**：

- `BenchmarkScorer` 由组合根构造时**不传 `runners`**（`runtime.py:837`，`BenchmarkScorer(benchmarks)`）
  ⇒ `_runners` 恒空 ⇒ `__call__` 恒返 `None`（`evaluator.py`「该 `task_type` 无执行器」分支）；
- `Evaluator.evaluate` 见 `held_out is None` ⇒ `verdict="freeze"`（`evaluator.py:281-286`）；
- `EvolutionEngine.crystallize` 对 `freeze` 抛 `EVAL_FROZEN`（`engine.py:180-185`）。

即：**就算把基准注册进去，也没有任何代码路径能产出留出分** ⇒ `publish` 生产不可达，观察期回归
自动溶解（`0205`）所依赖的「先发布再观察」也不闭环。且**没有任何操作面**能注册基准 / 设基线
（`BenchmarkRegistry.register` / `set_baseline` 零生产调用）——「人工注册面」在规格里写了、
在代码里没有。

## 做什么

### 1. 真 runner（硬门控，缺省关）

- `OPT_IN_MODULES += ("evolution_benchmark_runner",)`（`runtime.py:158`）：**缺省关**，仅显式
  `features.evolution_benchmark_runner: true` 才注入执行器。
- 旗关（缺省）⇒ `runners=None` ⇒ 今日 `freeze` 判定**逐字不变**（**注册基准 ≠ 同意烧 token**：
  注册只是数据入库，是否真跑由代码开关决定）。
- 旗开 ⇒ `runners = {"module_health": _bench_runner, "tool_use": _bench_runner}`（这两个正是
  `EvolutionWorker` 生产产出的 `task_type`，`worker.py:109/:128`）传 `BenchmarkScorer(benchmarks,
  runners=runners)`。
- **runner 闭包引用 `general` 兜底子 profile**（`runtime.py:1026-1031`），**非主 loop**：
  - 子 loop **无 `cold_path` / `trace_observer`** ⇒ `runner → loop → _maintain → scorer → runner`
    的递归路径**不存在**（主 loop 有 cold_path，递归今日仅靠 900s 节拍闸挡，脆）；
  - `agent_loop` 天然 `transcript=None` ⇒ 样本间上下文零漂移；
  - 绕开 `agent_router` 关键词匹配的非确定性。
- `_bench_runner(sample)`：`_run_coro(general.loop.arun(str(sample["input"]), session_id="bench"))`
  → 失败 ⇒ `None`（完成度 0），成功 ⇒ `reply`（精确对齐 scorer 语义 `evaluator.py:239-244`）。
  `session_id="bench"` 防 `loop.<trace>` 污染全局记忆层。**异常冒泡**（`evaluator.py:215` 认可的
  freeze 语义 —— 不吞成 0 分、不吞成通过）。
- `_run_coro`：调用线程无运行中事件循环 ⇒ `asyncio.run`；有 ⇒ 单线程池兜（**已核**：冷路径在
  `to_thread`、`evolve run` CLI 在主线，两者皆无循环 —— 兜底只为不把 `RuntimeError` 抛给评测）。

### 2. 基准人工注册操作面（数据面免 runtime）

- 嵌套 `evolve benchmark {register|set-baseline|list}`（`_add_evolve_parser`，`entry.py:296-317`）。
- 操作面**只写数据面**：`BenchmarkRegistry(path=_state_path("evolution-benchmarks.json"))`
  —— 与组合根**同源**（`runtime.py:817`），**不装配 runtime**（免凭据；`_notes_store` 先例）。
- `register <benchmark_id> --plugin-id <id> --task-type <t> --samples <path.json>`
  （`[{"input","expected"}]`；`--plugin-id` **必填** —— plugin 绑定才激活评测 `evaluator.py:230`，
  也是基线键）；`set-baseline <plugin_id> <score>`；`list`。
- CLI help 注明 `expected` 须与期望回复**逐字相等**（缺省只评完成度）。

## 不做（边界）

- **不改 `_crystallize_plugin`**：仍只登记不产真插件（`plugin_ids.py:11-18` 有意裁决，不在本批）。
- **不给 `BenchmarkScorer` 加 `runners_factory` 之类的懒加载 API**：门控在组合根，接缝保持
  `runners: Mapping | None` 不变。
- **不加「注册即开跑」的隐式同意**：注册（数据）与执行（代码）分离是规格既有红线。
- **不做第三 / 第四种 `task_type`**：worker 只产这两个。
