# Tasks

> ci-cd 代码（1.x/2.x/6.x）已落地抽象层并测试；evolution「任务质量评测」（3.x）与 observability「指标导出/告警」（4.x/5.x）spec 已并入 base，代码依赖后续 Phase。

## 1. CICDPipeline 交付流水线（P0）

- [x] 1.1 lint/typecheck/test/build 四道门禁实现
- [x] 1.2 任一门禁失败阻断交付
- [x] 1.3 门禁引用 development-toolchain（GATE_COMMANDS 映射 ruff/pyright/pytest/uv build）

## 2. ArtifactPublisher 制品发布（P0）

- [x] 2.1 版本化制品打包
- [ ] 2.2 发布通道：发布候选 → 门禁 → 制品归档 → 发布—— 真实通道未接：门禁前置检查已落地，发布通道经注入 channel（默认 CHANNEL_UNREACHABLE）
- [x] 2.3 制品可追溯、可回滚（rollback → ARTIFACT_NOT_FOUND）

## 3. 任务质量评测（P0，扩展 evolution）

- [ ] 3.1 通用任务完成度评测—— spec 已并入 base，代码依赖后续 Phase
- [ ] 3.2 正确性评测—— spec 已并入 base，代码依赖后续 Phase
- [ ] 3.3 轨迹质量评测—— spec 已并入 base，代码依赖后续 Phase
- [ ] 3.4 复用评测基建三件套（基准集 + 评测运行器 + 指标对比基线）—— spec 已并入 base，代码依赖后续 Phase

## 4. 指标导出协议（P1，扩展 observability）

- [ ] 4.1 OTel 协议导出—— spec 已并入 base，代码依赖后续 Phase
- [ ] 4.2 Prometheus 协议导出—— spec 已并入 base，代码依赖后续 Phase

## 5. 告警规则（P1，扩展 observability）

- [ ] 5.1 阈值告警—— spec 已并入 base，代码依赖后续 Phase
- [ ] 5.2 异常告警—— spec 已并入 base，代码依赖后续 Phase
- [ ] 5.3 遥测故障告警—— spec 已并入 base，代码依赖后续 Phase

## 6. 错误码与收敛（P1）

- [x] 6.1 ci-cd 错误码（GATE_FAILED/ARTIFACT_NOT_FOUND/CHANNEL_UNREACHABLE，对齐 ci-cd-interface.md 错误码表）
- [x] 6.2 挂接 development-toolchain 语义引用（GATE_COMMANDS）；evolution/observability 语义引用 deferred（spec 已并入 base）
