# Tasks

## 1. 四阶段闭环规格（P1）

- [x] 1.1 对比诊断：Diagnoser 归因缺陷到单个插件，target_plugin=None 表示系统级
- [x] 1.2 模块级提案：Proposer 生成 GenerationCandidate（含 delta 与 kind=skill/plugin）
- [x] 1.3 验证门：Validator review + 运行时测试，GateReport.passed 才放行
- [x] 1.4 留出评测：Evaluator 留出集防退化，verdict=publish/rollback/freeze
