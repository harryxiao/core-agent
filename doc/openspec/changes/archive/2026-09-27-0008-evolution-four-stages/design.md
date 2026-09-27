# Design

## Context

evolution capability 此前仅有「经验采集 / 结晶为技能/SOP / 溶解与回收」三条 Requirement，缺「诊断 → 提案 → 验证门 → 留出评测」四阶段闭环；而 evolution-interface.md 已定义完整四插件接口（Diagnoser / Proposer / Validator / Evaluator + 4 数据结构 + run_cycle 编排），requirements CORE-EVO-R1 也已写明四阶段。spec、接口、requirements 三者脱节，四阶段无规格追踪、无法验收。本 change 以 delta spec 补齐四阶段 Requirement，本 design 固化四阶段各自决策，作为 spec 与 evolution-interface.md 的映射依据。

## Decisions

- **四阶段闭环**：诊断 → 提案 → 验证门 → 留出评测，对应 evolution-interface.md 四插件 Diagnoser / Proposer / Validator / Evaluator，由 run_cycle 编排、逐阶段流转。
- **对比诊断**：Diagnoser 把缺陷归因到单个插件，输出 DiagnosisReport（target_plugin=None 表示系统级）；无法归因则转人工，不进入提案阶段。
- **模块级提案**：Proposer 生成世代化候选 GenerationCandidate（含 delta 与 kind，kind = skill/plugin）。
- **验证门**：Validator 执行 review + 运行时测试，GateReport.passed 才放行；未过门丢弃候选、教训写回 L2/L3。
- **留出评测**：Evaluator 在留出集上评测防退化，verdict = publish / rollback / freeze；rollback 自动回滚并冻结冷却期。
- **规格追踪**：四阶段各对应 delta spec 一条 Requirement，Scenario 逐一对齐四插件，使四阶段可验收。

## Risks / Trade-offs

- **接口名/字段名逐字一致**：spec 的 DiagnosisReport / target_plugin / GenerationCandidate / GateReport.passed / verdict 等字段须与 evolution-interface.md 完全一致，否则四阶段仍无法验收（沿用 delta 与接口正文逐字一致约定）。
- **无代码变更**：本 change 仅补规格与设计文档（Affected code = 无），四阶段实现落地依赖后续任务；design 只固化接口层契约，不引入新实现假设。

## Open Questions

- freeze（冻结）语义与冷却期解除条件：spec 仅写「verdict=rollback 自动回滚并冻结冷却期」，冻结后的解除/复活路径未定义，待实现期明确。
