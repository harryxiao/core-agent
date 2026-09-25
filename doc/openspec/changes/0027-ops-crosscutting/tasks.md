# Tasks

> 设计落地，实现依赖后续 coding 阶段。

## 1. CICDPipeline 交付流水线（P0）

- [ ] 1.1 lint/typecheck/test/build 四道门禁实现
- [ ] 1.2 任一门禁失败阻断交付
- [ ] 1.3 门禁引用 development-toolchain（ruff/pyright/pytest/构建）

## 2. ArtifactPublisher 制品发布（P0）

- [ ] 2.1 版本化制品打包
- [ ] 2.2 发布通道：发布候选 → 门禁 → 制品归档 → 发布
- [ ] 2.3 制品可追溯、可回滚

## 3. 任务质量评测（P0，扩展 evolution）

- [ ] 3.1 通用任务完成度评测
- [ ] 3.2 正确性评测
- [ ] 3.3 轨迹质量评测
- [ ] 3.4 复用评测基建三件套（基准集 + 评测运行器 + 指标对比基线）

## 4. 指标导出协议（P1，扩展 observability）

- [ ] 4.1 OTel 协议导出
- [ ] 4.2 Prometheus 协议导出

## 5. 告警规则（P1，扩展 observability）

- [ ] 5.1 阈值告警
- [ ] 5.2 异常告警
- [ ] 5.3 遥测故障告警

## 6. 错误码与收敛（P1）

- [ ] 6.1 ci-cd 错误码（对齐 ci-cd-interface.md 错误码表）
- [ ] 6.2 挂接 development-toolchain / evolution / observability 语义引用
