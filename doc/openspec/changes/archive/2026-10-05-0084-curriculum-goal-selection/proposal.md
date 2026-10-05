# 0084 — 自动课程（目标生成与调度，账本 E5）

## 为什么（账本 E5）

E5「主 Agent 自动迭代内部模块」。一手核实（§design 决策 1 有完整证据链）：进化闭环
**四阶段与两个驱动面都已接线**（`EvolutionWorker.maybe_run` → `run_cycle` → 诊断/提案/验证/评测），
缺的不是闭环本身，而是**目标选择层**——「这一轮该迭代谁」。

今天的现实：`Diagnoser` 只会答「谁失败最多」，且**并列即弃权**（转人工、无归因）；冷路径
每一轮都从零重算，**没有任何跨轮记忆**：刚发布、仍在观察期的插件与已有待确认候选的插件，
照样会被再次选为迭代目标（churn）。人也没有**显式的目标入口**——`evolve run` 只能「跑一轮」，
不能说「迭代 X」。

## 用户裁决

- **先出设计再实现**（E5 立项口径）；
- **课程落点 = 引擎侧目标生成**（不进 loop / 不进 CLI 编排：目标选择是进化引擎的职责，
  两个驱动面只负责「给机会」）；
- **信号策略 = 结构化信号排序建议 + 显式目标入口 `evolve run --goal`**：
  **不用**记忆自由文本（`MemoryEntry.importance` 恒为 0、无结构化教训标记 ⇒ 只能靠关键词启发式，
  不可靠）、**不用** LLM（非确定性、无凭据不可验证、token 无界、失败模式是静默编造）。

## 变更

| 文件 | 动作 |
|---|---|
| `src/core/evolution/curriculum.py`（新） | `EvolutionGoal`（目标 + 先验权重 + 依据 + `directive`）+ `CurriculumPlanner.plan(traces, *, explicit, limit)`：结构化信号 → 有序有界议程（失败强度定序 / 已处理目标降权 / `plugin_id` 升序保确定性） |
| `src/core/evolution/diagnoser.py` | `diagnose(traces, *, prior=None)`：**可选**先验并入分数（权重 < 1.0 ⇒ 证据恒优先、先验只破并列） |
| `src/core/evolution/engine.py` | `run_cycle(traces, *, goals=None)`：`directive` 目标直接采用（跳过归因竞争）；否则议程整体作为诊断先验 |
| `src/core/evolution/worker.py` | `maybe_run(*, force=False, goal=None)` + `planner` 构造注入（缺省由 `engine.observations` / `engine.pending` 自建，同既有 `trigger` 惯用法）⇒ **生产自动开课** |
| `src/core/evolution/__init__.py` | 导出 `CurriculumPlanner` / `EvolutionGoal` |
| `src/core/entry.py` | `evolve run [--goal <plugin_id>]`（argparse 选项）+ 结局行回显本轮目标 |
| `tests/test_evolution_curriculum.py`（新） | 议程定序 / 降权只改并列顺序 / 先验不压证据 / 显式目标直接采用 / 空信号 / 预算 / 确定性 |
| `tests/test_evolution.py` | 诊断先验解并列（无先验仍转人工） |
| `tests/test_entry.py` | `evolve run --goal` 组合面（目标透传 + 回显） |

**规格改动**（`specs/evolution/spec.md` delta）：**ADDED**「自动课程（目标生成与调度）」；
**MODIFIED**「对比诊断」（可选先验）+「冷路径驱动」（自动开课 + `--goal`）。

## 明确不做（且已记后果）

- **不新增驱动面**：驱动面仍只有 `evolution/spec.md`「冷路径驱动」列的那两个（loop 收尾节拍、
  CLI `evolve run`）。课程是**引擎内**的目标选择层，不是第三个驱动者，也不常驻。
- **不给模型新工具**：不暴露 `evolution.*` / 课程工具给模型（模型的工具面仍是 9 个）——「自动迭代」
  指的是**冷路径自动选目标**，不是让模型自主发起进化。
- **不放宽人工门**：低风险候选仍须显式 `confirm`（规格「技能级候选仍须显式人工确认」原样有效）；
  课程只影响**提案给谁**，不影响**发布是否要人批**。
- **不读记忆自由文本 / 不调模型**（用户裁决）：记忆条目无结构化教训标记，关键词启发式会引入
  不可解释的排序；需要时另立变更。
- **不做「曾未过门/曾回滚」降权**：门禁失败提示的是**提案质量**问题而非目标问题，且证据仍可能
  正当指向它；已处理口径只取「观察期中」与「已有待确认候选」两条**明确已处理**的信号。
