# Design: ci-cd 交付流水线 + evolution/observability 扩展的边界

## Context

14 维架构覆盖评估（2026-09-25）：CI/CD 为唯一真缺口（specs 24 cap 无 ci-cd），评测框架/监控指标为部分覆盖。本 change 新开 ci-cd capability（交付流水线 + 制品发布），并扩展 evolution（任务质量评测）、observability（指标导出协议 + 告警规则），其余部分维度（消息队列、提示词层）P2 暂缓。

## Decisions

- **ci-cd 门禁引用 toolchain**：lint/typecheck/test/build 四道门禁引用 0025-configuration 已落地的 development-toolchain（ruff/pyright/pytest/构建），不新引入工具。
- **evolution 泛化复用三件套**：任务质量评测复用评测基建三件套（基准集 + 评测运行器 + 指标对比基线），不另建独立评测框架，避免与进化内环评测语义重复。
- **observability 导出 OTel/Prometheus**：指标导出协议为导出语义，复用现有指标监控聚合快照，不重复采集；OTel/Prometheus 为协议而非运行时依赖，不引入新框架。

## Non-Goals

- **消息队列/后台工作进程**：P2 暂缓，仅留痕不建（本轮不动）。
- **提示词与策略层**：P2 暂缓，仅留痕不建（本轮不动）。

## Risks

- **门禁过严阻断交付**：门禁分级（lint/typecheck/test 阻断级、build 视工程阶段），避免早期工程被过严门禁卡死。
- **导出协议与指标监控重复**：导出层复用现有聚合快照，不新增采集源，避免双采集漂移。

## Open Questions

- 制品发布到本地归档还是远程 registry，待工程实现选择。
- 告警触达通道（webhook / IM）待工程实现确定。
- OTel/Prometheus 导出器选型待实现收敛。
