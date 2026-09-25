# Design: durability 持久化 capability 的边界与执行态抽象

## Context

上轮与 CrewAI / MAF 架构对比发现 durability 缺失：grep 全 doc/ 英文 checkpoint/time-travel/durable + 中文「状态持久化/崩溃恢复」均 0 命中（来源：exploration_findings.md，2026-09-25）。对照主流框架：

- CrewAI：任务状态持久化 + memory 分层；
- Microsoft Agent Framework（MAF）：checkpointing 快照 + time-travel 调试回放；
- Core-Agent 现状：orchestration「断点续跑」仅任务级、tool-use「时间旅行回滚」仅副作用级，执行态级持久化/恢复/回滚整体缺失。

现有 capability 语义边界：

- `orchestration`：任务级编排——断点续跑覆盖挂起/恢复/取消 + 持久化执行上下文 + 幂等恢复；
- `tool-use`：副作用级撤销——EffectId undo 栈覆盖写类工具回滚；
- 两者都不回答「执行态整体如何保存、崩溃后如何恢复、如何回滚到历史检查点」，故需独立 `durability` capability。

关键约束：`data-model.md` 已有「4. 待补定义实体」预留点；`loop` 四阶段（perceive/decide/act/observe）无执行态持久化钩子。

## Decisions

1. **独立 capability，而非并入 orchestration/tool-use**（决策1C）：durability 只描述执行态级持久化/恢复/回滚，与任务级编排、副作用级撤销正交，避免语义耦合。
2. **Requirement 按四类能力划分 R1-R4**（决策2A）：检查点快照（R1）/崩溃恢复（R2）/时间旅行（R3）/生命周期保留策略（R4），各含独立 Scenario 全集。
3. **时间旅行复用 tool-use EffectId undo 栈，不新建撤销机制**（决策3A）：执行态回滚沿历史逆序调用写类工具撤销函数，与副作用级回滚协同，避免双套撤销实现。
4. **保留策略含 pinned 关键检查点保护**（决策4A）：按数量上限/时间窗口/存储配额自动清理过期检查点，pinned 检查点不受自动清理影响，避免无限增长。
5. **挂载点标注而非改写**：orchestration「断点续跑」与 tool-use「时间旅行回滚」仅加交叉引用注释指向 durability，不改原 Requirement 正文，保持既有规格稳定。

## Risks

- **与 orchestration/tool-use 语义重叠**：断点续跑、时间旅行回滚原语已在两 capability 内，durability 若越界会重复定义；已通过「挂载点标注 + 执行态级聚焦」规避。
- **检查点存储后端未定**：存储介质（内存/文件/数据库）与序列化格式未在规格中锁定，留待工程实现收敛，规格只定义抽象语义。
- **执行态范围膨胀**：执行态若扩展到 LLM 上下文全量快照会引发成本/体积问题；本次限定执行上下文、任务状态、中间结果、记忆、会话状态五类。

## Open Questions

- 检查点存储后端（内存/文件/数据库）与序列化格式待工程实现确定。
- 崩溃恢复的检测机制（watchdog 探活 vs 进程退出钩子）待落地选择。
- 时间旅行回滚与 tool-use 副作用级撤销的调用顺序边界（谁先谁后）待实现时明确。
