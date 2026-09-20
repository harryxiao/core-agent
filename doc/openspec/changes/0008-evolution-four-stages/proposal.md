# Change: Evolution 四阶段闭环补全（诊断 → 提案 → 验证门 → 留出评测）

## Why

evolution/spec.md 仅 3 条 Requirement（经验采集 / 结晶为技能/SOP / 溶解与回收），缺「诊断 → 提案 → 验证 → 评测」四阶段闭环；但 evolution-interface.md 已有完整四阶段插件接口（Diagnoser / Proposer / Validator / Evaluator + 4 数据结构 + run_cycle 编排），requirements CORE-EVO-R1 也已写「诊断→提案→验证→评测四阶段」。spec 与接口、requirements 脱节，四阶段无规格追踪、无法验收。

## What Changes

- evolution/spec.md 追加 4 条 Requirement（对比诊断 / 模块级提案 / 验证门 / 留出评测），Scenario 逐一对齐 evolution-interface.md 四插件
- **对比诊断**：Diagnoser 把缺陷归因到单个插件（target_plugin，None 表示系统级）
- **模块级提案**：Proposer 生成世代化候选（GenerationCandidate，kind = skill/plugin）
- **验证门**：Validator 执行 review + 运行时测试，GateReport.passed 才放行
- **留出评测**：Evaluator 在留出集上防退化，verdict = publish / rollback / freeze

## Impact

- **Affected specs**：`evolution`（追加 4 条 Requirement）
- **Affected docs**：无（spec 补全；evolution-interface.md 已含四插件接口）
- **Affected code**：无
- **Dependencies**：依赖 `evolution-interface.md`（四插件接口定义）；与 `requirements` CORE-EVO-R1 对齐
