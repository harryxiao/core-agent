# Design: memory-compaction-hardening

## Context

走查（2026-10-17）确认六条记忆/进化链路机制完成，但存在三个结构性弱点：

1. **摘要质量漂移**：`summarize.py` 的滚动合并无轮次/版本感知，`MAX_SUMMARY_CHARS=2000` + `_elide_summary` 尾部 800 字截断在多次 compact 后可能丢掉早期仍有效的决策上下文。
2. **预算口径分裂**：`loop/default.py::_should_compact`（步数阈值）与 `context/budget.py::BudgetManager.enforce`（字符/预算）是两套独立估算，对「必留项」定义不一致，极端情况互相打架。
3. **checkpoint 非原子**：`scheduler.py` 默认 `.core/scheduler-checkpoint.json` 单文件整写，进程中途被 kill 会产生半截 JSON 导致 resume 失败。

## Goals / Non-Goals

**Goals**
- G1：摘要分层保留——结论区与事实区独立预算，分层 elide，消除多次 compact 的信息漂移
- G2：预算裁决收敛到 `BudgetManager` 单一口径，`_should_compact` 仅做触发
- G3：checkpoint 原子写 + 损坏降级留痕

**Non-Goals**
- KeyFact 语义去重、reject 教训 TTL、提炼丢弃 metrics（留待「记忆质量打磨」后续 change）
- 不新增任何 LLM 调用（分层 elide 是纯本地截断策略）
- 不改 memory↔LLM 依赖方向（保持 L5 注入，ADR-0045）

## Decisions

### D1：摘要分层（layered summary）

`Summarizer` 输出保持单一字符串，但内部约定两段结构，用哨兵标记分隔：结论区（`<conclusions>`...`</conclusions>`）与事实区（`<facts>`...`</facts>`）。

- `MAX_SUMMARY_CHARS` 拆为 `MAX_CONCLUSION_CHARS=800` 与 `MAX_FACT_CHARS=1200`，两者独立 elide（各自首尾保留节选），避免事实区溢出挤掉结论区。
- `_elide_summary` 改为 `_elide_layered`：先解析分层标记；无标记（旧摘要、LLM 未按格式返回）时回退现有整段 elide，向后兼容。
- 滚动合并 prompt 补充指令：输出必须包含两段标记，且保留既有结论的轮次序号前缀（`[r3]`、`[r7]`），使早期结论有稳定锚点，不被再压缩随意改写。

**Rationale**：不引入结构化存储，保持 `summarizer` 契约 `(list[MemoryEntry]) -> str` 不变，所有既有调用方零改动。

### D2：预算裁决单一口径

- `BudgetManager` 新增 `should_compact(transcript_chars, turn_count) -> bool`：预算关闭时退化为步数阈值判断（迁移 `loop/default.py::_should_compact` 的逻辑），预算开启时由 `enforce` 的裁决结果驱动。
- `loop/default.py` 删除 `_should_compact`，调用点改为 `budget.should_compact(...)`；`_budget_retry` 降级路径不变，仍由 loop 编排。
- 「必留项」定义收敛到 `budget.py` 单处（`_trim` 与 `should_compact` 共享同一份 keep-list 计算），消除两处口径漂移。

**Rationale**：触发与裁决分离——loop 只决定何时调用 compact 流程，预算是否真的压、压多少由 BudgetManager 唯一裁决。

### D3：checkpoint 原子写

- 默认 checkpoint 落盘改为：写 `<path>.tmp` → `os.replace(<path>.tmp, <path>)`（POSIX 原子替换）。
- `load(task_id)` 损坏处理：捕获 `json.JSONDecodeError`，将损坏文件重命名为 `<path>.corrupt-<ts>` 留痕，日志 `checkpoint_corrupted`，返回 `None` 降级为从头跑。
- 自定义 `CheckpointFn` 注入面不变（契约仍是整体读写函数），原子性保证只在默认实现内做；文档注明自定义实现建议遵循同样的 tmp+replace 模式。

**Rationale**：`os.replace` 在同文件系统上是原子操作，零额外依赖；tmp 与目标同目录保证同文件系统；损坏降级留痕符合「失败可观测」而非静默重置。

## Risks / Trade-offs

| 风险 | 缓解 |
|---|---|
| LLM 不按分层格式返回 | 无标记回退整段 elide（D1 内置）；merge prompt 显式要求格式；测试覆盖无标记旧摘要 |
| `should_compact` 迁移后步数行为变化 | 步数阈值逻辑逐字迁移，测试断言旧阈值边界不变 |
| 原子写跨文件系统失败 | tmp 与目标同目录，保证同文件系统 |
| 旧 checkpoint 兼容 | 读取格式未变，仅写入路径变，无迁移需求 |

## Migration Plan

1. `budget.py` 加 `should_compact`（纯新增，旧调用方零影响）
2. `loop/default.py` 切换调用点（`fix(loop): unify compaction trigger into BudgetManager`）
3. `summarize.py` 分层 elide + prompt 更新（`feat(memory): layered summary elide`）
4. `scheduler.py` 原子写 + 损坏降级（`fix(orchestration): atomic checkpoint writes`）

每步独立可验证，规格 delta 对应 tasks.md 的分项验收。
