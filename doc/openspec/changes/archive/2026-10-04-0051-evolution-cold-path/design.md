# Design — evolution-cold-path

## 决策 1：驱动面 = loop 收尾节拍 + CLI 显式入口（与 0049 同款手法）

无真实常驻宿主（`HarnessHost` 在 `entry.py` 每条命令各起一份、serve 也非长驻调度器），
因此「谁来定期驱动冷路径」只有两个诚实的答案：**在有真实驱动的路径上搭节拍**，以及**显式入口**。
loop 收尾是唯一每轮必然经过的位置 → 与 change `0049` 的记忆维护**共用同一节拍闸门**
（`maintenance_interval`，缺省 900s），注入一个可选冷路径回调；`core-agent evolve run` 提供
「我现在就要跑一轮」的一次性入口（`force=True` 跳过阈值门）。

**不采纳**「loop 直接持 `EvolutionWorker`」：loop 属 L3、evolution 属 L4，loop 只能拿到一个
`Callable[[], None]`（与 `hints` / `TurnObserver` 同一 DI 手法），装配由组合根做。

## 决策 2：阈值门留在 `EvolutionTrigger`，节拍只给「机会」

节拍不判断「该不该跑」（那是冷路径的节奏语义，已由 `EvolutionTrigger` 累计 trace 数决定），
只提供一次调用机会：`maybe_run()` 未达阈值返回 `None`（零模型调用、零状态变更）。
**不采纳**「节拍自己维护第二套阈值」：两处阈值必然漂移。

## 决策 3：采样来源 = 冷路径批次成功率（按 `plugin_id` 归因）

台账 A5 给的两条路是「`Evaluator` 评测轮次回灌」与「外部上报」。前者需要再造一条评测驱动
（同一「无人驱动」问题）、且要为目标产物重跑留出集；后者在生产没有上游。取**已有数据的最近似口径**：
`EvolutionWorker` 本批 trace 里**已归因到该目标**的成功率——批次级、零额外评测成本、
与开窗基线（`held_out_score`，0..1）同量纲，且天然受 `min_samples(3)` + 冻结冷却期保护。

**已知口径张力（如实记录）**：批次成功率与留出评测分**不是同一指标**（前者是线上代理指标），
绝对分差容差 `0.2` 只是近似可比。宁可漏报不误杀——溶解是不可逆方向的重动作（同 ADR-0052 决策 ②）。

## 决策 4：窗口持久化沿用既有形状，helper 提升到 `core/`

`ObservationRegistry` 加 `path: Path | None`（缺省纯内存），落盘 `{target: {baseline, samples, frozen_until}}`。
冻结截止**一并落盘**：否则重启即解冻，冷却期形同虚设（ADR-0052 决策 ④ 的同一理由）。

`skills/persist.py` 的两个纯函数改放 `src/core/persistence.py`：ADR-0053 决策 ① 把它放在 skills 包内的
前提是「只服务技能态」，进化侧成为第二个消费者后该前提不成立；留在 skills 包则 evolution 得反向
import skills 内部模块（依赖方向错）。提升到 `core/` 顶层的中性模块（不 import 任何能力包、
不构成横切能力）是唯一不制造错误箭头的选择。决策记 **ADR-0054**。

## 决策 5：CLI 只跑一轮、只打印结局、不改运行态

`evolve run` = 装配 runtime → `runtime.evolution.maybe_run(force=True)` → 打印
`status` / `skill_id`（`no_op` 时打印「无候选」）→ 退出码 0；装配失败 → stderr + 退出码 1
（与 `memory maintain` 同形状）。**不采纳**「`evolve pending` / `evolve confirm`」：那是 A4 的审批操作面。

## 备选与否决

- 定时器 / 后台线程：无宿主，且引入调度语义（同 A1 的结论）。
- loop 直接 import evolution：违反分层与 DI 约定。
- 采样只在 CLI 触发：节拍覆盖不到「长会话中自动回滚」这一价值主张。
