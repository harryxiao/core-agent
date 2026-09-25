# Change: 新增 ci-cd 能力（交付流水线+制品发布）+ 扩展 evolution（任务质量评测）+ observability（指标导出协议+告警规则）

## Why

14 维架构覆盖评估（2026-09-25 实测，来源：requirements 24 模块 + architecture-overview 全文 + 5 spec 实测）结论：9 维完整、4 维部分（评测框架/监控指标/消息队列/提示词层）、1 维真缺口（CI/CD）。本 change 闭合真缺口 + 补齐 4 个部分维度中的 2 个可落地项：

- **CI/CD 真缺口**：specs 24 capability 无 ci-cd，全库无交付流水线与制品发布语义（grep 零命中）。工程落地后（见 0025-configuration 落地的 ruff/pyright/pre-commit/GitHub Actions）缺少统一的 lint/typecheck/test/build 质量门禁与版本化制品发布通道，是唯一的全新建 capability。
- **评测框架部分覆盖**：evolution 已有评测基建（基准集 + 评测运行器 + 指标对比基线），但仅服务"留出评测防退化"这一进化内环语义，未泛化为通用任务质量评测（任务完成度/正确性/轨迹质量），无法支撑跨任务的通用评测需求。
- **监控与指标部分覆盖**：observability 已有指标监控（采集聚合）+ 遥测缓冲与导出重试，但缺少标准化指标导出协议（OTel/Prometheus）与分级告警规则，指标无法对接外部监控栈、异常无法分级触达。
- **消息队列 + 提示词层**：P2 项，本轮仅留痕不建（见 design.md Non-Goals）。

## What Changes

- **交付流水线**：新增 ci-cd capability 质量门禁——lint/typecheck/test/build 四道门禁，任一失败阻断交付；门禁引用 development-toolchain（ruff/pyright/pytest/构建）。
- **制品发布**：版本化制品 + 发布通道（发布候选 → 门禁 → 制品归档 → 发布），制品可追溯、可回滚。
- **任务质量评测**：扩展 evolution——通用任务完成度/正确性/轨迹质量评测，复用评测基建三件套（基准集 + 评测运行器 + 指标对比基线）。
- **指标导出协议**：扩展 observability——指标以 OTel/Prometheus 协议导出，对接外部监控栈。
- **告警规则**：扩展 observability——分级告警（阈值告警/异常告警/遥测故障告警），分级触达。
- **ci-cd 三件套**：新建 `openspec/specs/ci-cd/spec.md`（照 spec 双格式）+ `03-interfaces/ci-cd-interface.md`（照 durability interface 骨架）。
- **delta 双写**：`changes/0027-ops-crosscutting/specs/{ci-cd,evolution,observability}/spec.md`（delta 与 specs 根目录逐字一致）。
- **adr.md**：追加 ADR-0036（新增 ci-cd 能力 + evolution 泛化 + observability 导出/告警）。
- **architecture-overview.md**：核心组件表加 CICDPipeline 行、部署视图目录树加 ci-cd 条目（ci-cd 非运行时横切，不改"5 个横切能力"计数）。
- **requirements.md**：追加 1.25 CI/CD 交付流水线模块。

## Impact

- **Affected specs**：`ci-cd`（新增，第 25 spec）；`evolution`（扩展：Purpose 泛化 + 追加「任务质量评测」）；`observability`（扩展：追加「指标导出协议」「告警规则」）
- **Affected docs**：`openspec/specs/ci-cd/spec.md`（新建）、`03-interfaces/ci-cd-interface.md`（新建）、`openspec/specs/evolution/spec.md`（Purpose + Requirement）、`openspec/specs/observability/spec.md`（+2 Requirement）、`openspec/changes/0027-ops-crosscutting/`（新建 delta 三件）、`00-product/requirements.md`（+1.25）、`00-product/design-completeness-eval.md`（N 模块数字口径 24→25）、`01-architecture/adr.md`（+ADR-0036）、`01-architecture/architecture-overview.md`（组件表 + 目录树）
- **Affected code**：无（架构设计与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：ADR 编号=当前最大+1（0036）；specs 24→25 需同步 requirements.md 1.x 清单与 design-completeness-eval.md「N 模块」数字口径；不引入新框架（OTel/Prometheus 为导出协议语义，非运行时依赖）
