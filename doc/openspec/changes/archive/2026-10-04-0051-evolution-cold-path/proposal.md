# evolution-cold-path — 进化冷路径驱动面 + 观察期采样与持久化（A10 + A5 + A3 进化半边）

## Why

走查（本次会话新增发现，账本记作 A10）：**进化冷路径在生产没有任何驱动面** ——
`EvolutionWorker.on_trace_complete` / `maybe_run` 全仓仅 `runtime.py`（构造）与 `tests/` 引用，
CLI 无对应命令、loop 无节拍、无定时器。后果是 L4 整条冷路径离线：`run_cycle`（诊断→提案）、
`crystallize`（发布 + **开窗**）都不会发生。

A5 因此是**下游问题**：`EvolutionEngine.observe`（采样接缝）无调用方，即便把采样接进 worker
也仍然没人驱动 worker。A3 的进化半边（观察窗口进程内）同理——窗口不落盘则重启即丢，
而 ADR-0052 已如实记录该缺口。

## What Changes

- **驱动面（A10）**：①loop 收尾维护节拍给出一次**冷路径机会**（注入回调，缺省未注入则不做）——
  与 change `0049` 的记忆维护共用同一节拍闸门；②CLI 新增 `core-agent evolve run`（一次性、
  强制跑一轮 `maybe_run(force=True)`、打印结局）。**阈值门仍归 `EvolutionTrigger`**，驱动面不搬节奏语义。
- **采样来源（A5）**：每轮 `run_cycle` 后，对本批 trace 中**已开窗**的目标按 `plugin_id` 归因算
  成功率并各上报一次样本（线上指标口径，复用引擎既有 `observe`，无需新评测机制）。
- **窗口持久化（A3 进化半边）**：`ObservationRegistry` 加可选 `path`（基线 / 样本 / 冻结截止落盘，
  启动恢复）；缺省纯内存。
- **helper 提升**：`skills/persist.py` 的两个纯函数提升为 `src/core/persistence.py`
  （技能态与进化态共用；ADR-0053 决策 ① 的前提「只服务技能态」已不成立，决策见 ADR-0054）。
- spec delta：evolution（ADDED 冷路径驱动 + ADDED 窗口持久化 + MODIFIED 观察期回归自动溶解[采样来源]）、
  loop（MODIFIED 执行循环[维护节拍含冷路径]）、cli-ops（MODIFIED 运维命令集[`evolve run`]）。

## Non-Goals

- **不做** A4（`EvolutionEngine.confirm` 的生产调用方 / pending 队列驱动面）：那是「审批操作面」，
  与本 change 的「冷路径跑起来」不同层，留作下一步。
- **不做**常驻后台任务/定时器（无真实常驻宿主：`HarnessHost` 每条 CLI 命令各起一份）。
- **不做**跨进程并发写合并（沿用 ADR-0053 决策的整文件覆盖语义）。

## Impact

- `src/core/persistence.py`（新，helper 迁入）、`src/core/skills/{persist.py→删,library,feedback,sop,version}.py`
- `src/core/evolution/{observation,worker,engine}.py`、`src/core/loop/{default,protocol}.py`、
  `src/core/entry.py`、`src/core/runtime.py`
- spec：`doc/openspec/specs/{evolution,loop,cli-ops}/spec.md`
- 文档：`doc/03-interfaces/{evolution,loop,skills}-interface.md`、`coding-plan/cli-contract-baseline.md`、ADR-0054
- 账本：A10 新增、A5 关闭、A3 全闭
