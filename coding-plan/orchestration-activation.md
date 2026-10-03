# 任务：多任务编排激活（L3.5 orchestration 从骨架到可用）

> 状态：已完成 ｜ 创建：2026-10-03 ｜ 完成：2026-10-03 ｜ 前置：工具调用链路已贯通（原生 tool_calls + code_run/web_fetch + 审批通道，见 `7789f46` 后续提交）

> 完成纪要：spec 补「LLM 拆解 / 验收门 / 任务入口 / 依赖结果交接」场景；
> `LLMSubtaskPlanner`（失败回落单子任务）+ `LLMVerifier`（fail-closed，单次重试）注入拆解器；
> `core-agent task <目标> [--task-id|--resume]` CLI 入口流式进度事件；
> 检查点落盘 `$CORE_STATE_DIR/checkpoints.jsonl`（计划 + 累计结果 + 依赖交接上下文），
> kill -9 后跨进程 `--resume` 幂等续跑（已完成子任务跳过）；
> 依赖子任务注入前置验收通过结果。E2E：3 子任务 DAG 并行波次 3/3 通过；
> kill/续跑跳过已完成；验收失败非零退出不静默推进。

## 背景

orchestration 层（`src/core/orchestration/`）代码与测试齐备（拓扑排序 / 波次 / 检查点 / 断点续跑 / 崩溃恢复），`build_runtime` 也已装配 `TaskScheduler`，但存在三处断点，导致多任务能力**实际不可达**：

1. **拆解器无智能**：`runtime.py` 构造 `SubtaskDecomposer()` 未注入 planner → 永远拆成单子任务（`decomposer.py` 离线默认）。
2. **验收是占位判定**：`SubtaskDecomposer.verify()` 只做「结果非空即通过」，无真实验收门。
3. **入口不可达**：`entry.py` 无任何路径驱动 `orchestrator`（TUI/CLI 只走单任务 `loop`）；`Runtime.orchestrator` 仅测试引用。

## 激活步骤（SDD：先改规格再改代码）

1. **规格**：`doc/openspec/specs/orchestration/spec.md` 补「LLM 拆解」「验收门」场景（当前只写离线默认行为）；`loop` 或新增入口规格写明任务入口事件流。
2. **LLM 拆解**：给 `SubtaskDecomposer` 注入 planner（prompt 产出子任务 DAG：id/goal/acceptance/depends_on），失败回落单子任务。
3. **验收门**：`verify()` 换 LLM 对照子任务 `acceptance` 判定（可用 judgment/DecisionRouter），未过验收标记失败不推进（或重试一次）。
4. **入口接线**：`core-agent task <目标>` CLI 子命令驱动 `TaskScheduler`，流式产出子任务进度事件；TUI 后续跟进。
5. **审计**：每步验收结果与检查点写 trace（可断点续跑验证）。

## 验收锚点

- 输入复合目标（如「抓取 A 页面 + 用结果执行 B + 汇总写文件」）→ 拆出 ≥2 子任务的 DAG，按依赖序执行，全链 trace 可查。
- kill 进程后重启 → `recover()` 从检查点续跑未完成子任务。
- 验收不过的子任务不静默推进（失败可见、可回滚）。

## 关联

- 规格引用：orchestration / loop / durability（检查点）spec。
- 依赖：审批通道（高风险子任务动作复用 confirm 门）；`code_run`/`web_fetch` 已就绪可作子任务动作面。
