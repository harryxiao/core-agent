# Change: 记忆维护节拍（遗忘不再只挂在压实旁路）

## Why

`coding-plan/phase-19.md` 账本 A1：**`forget` 无调度器**。

- 遗忘目前只作为 `DefaultLoop._compact` 的第三步执行（`src/core/loop/default.py:285`），
  而 `_compact` 由 `_should_compact`（轮数 ≥ 阈值或 token 达预算，`:253-263`）触发——
  **短会话（永不触发压实的那些）永远不遗忘**，记忆衰减只有"长时间任务"才顺带发生。
- `forget` 自身是幂等、可撤销（`forgetting.<id>` trace）、低成本的扫描（`memory/store.py:192`），
  缺的只是**触发节拍**，不是能力。
- 生产侧另一个缺口：运维/系统定时器无法显式驱动一次记忆维护（无 CLI 入口）。

## What Changes

- **loop 收尾维护节拍**（loop，MODIFIED「执行循环」，`CORE-LOOP-R1`）：循环收尾（「记忆」步之后）
  SHALL 检查维护节拍——距上次维护达 `maintenance_interval`（可配置，`<=0` 关闭）时执行一次
  记忆维护（遗忘）；时钟与间隔可注入（可测）。维护失败降级不中断本轮，语义与既有
  `maintenance_failed` 遥测一致；不改变终止条件与回复内容。
- **遗忘的触发面**（memory，MODIFIED「记忆遗忘（forgetting）」，change `0042` 新增 Requirement，未编 R 号）：遗忘 SHALL
  由**维护节拍**（循环收尾按间隔 / 显式维护入口）驱动，不再仅依赖压实旁路；衰减判据、
  归档去向（L2→L4）与可撤销性一律不变。
- **显式维护入口**（cli-ops，MODIFIED「运维命令集」，`CORE-CLIOPS-R1`）：命令集补
  `memory maintain`——装配 runtime 后触发一次记忆维护（压实 + 遗忘），打印归档条数。
  一次性动作，不改变运行态。
- **`MemoryStore` 契约补齐**：Protocol 补声明 `forget`（与 `0048` 补 `compact` 同理，
  接口文档早定义，Protocol 遗漏）。

## Non-goals

- **不做常驻进程内的后台周期任务**：当前无真实常驻宿主（`HarnessHost` 由 CLI 单命令生命周期
  实例化，`entry.py:313/474`）；后台 daemon 属账本 A3（持久化 + serve 常驻）一并做。
- 不做每会话独立记忆维护节拍；不改遗忘阈值与打分公式；不给压实链路加节拍（压实仍按轮数/预算）。
- 不引任何调度依赖（零三方运行时依赖红线）。

## Impact

- **Affected specs**：`loop/spec.md`（MODIFIED「执行循环」+ 2 场景）、`memory/spec.md`
  （MODIFIED「记忆遗忘」+ 1 场景）、`cli-ops/spec.md`（MODIFIED「运维命令集」+ 1 场景）
- **Affected code**：`src/core/loop/default.py`（`clock` / `maintenance_interval` / `_maintain_memory`）、
  `src/core/memory/protocol.py`（补 `forget`）、`src/core/entry.py`（`memory maintain`）
- **Affected docs**：`03-interfaces/loop-interface.md`、`03-interfaces/memory-interface.md`、
  `03-interfaces/ui-interface.md`（CLI 命令面若有清单）
- **Affected tests**：`tests/test_loop.py`（节拍闸门：未达间隔不触发 / 达间隔触发一次 / 失败降级）、
  `tests/test_entry.py`（顶层命令面 + `memory maintain`）
- **Dependencies**：无新依赖
- **风险**：默认间隔 900s 意味着**单命令 CLI 进程内不会触发**（符合节拍语义，长会话/常驻进程才走它）；
  显式入口覆盖单次场景。遗忘在既有测试中由压实路径驱动，节拍路径新增独立用例、互不干扰。
