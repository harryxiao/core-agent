# Design: cli-ops 命令面 + 参数映射 + permission-mode 的边界

## Context

架构审计（2026-09-26）维度 B/C：无运维命令集、无启动参数映射、无 permission-mode。本 change 新增横切能力 cli-ops（命令集 + 参数映射），configuration 增加 CLI 覆盖层与 ConfigSpec 单一真源，permission 增加 permission-mode 四档。

## Decisions

- **cli-ops 作为新增横切能力**：横切 5→6，不并入 ui（D2），独立 spec+interface 双文档（照 durability 先例）。
- **ConfigSpec 单一真源**：每项声明 cli_flag/env_var/default/map_to，CLI flag/env/yml 三面由 ConfigSpec 生成，禁止硬编码第二真源（D5）。
- **参数映射优先级链**：CLI flag > env > config.yaml > 默认值，映射 `--foo.bar=value ↔ config.foo.bar ↔ CORE_AGENT_FOO_BAR`。
- **permission-mode 四档先落地**：read-only/interactive/auto-approve/high-risk-block，dangerous-permission 走配置层声明 risk，CLI 侧暂不加专用 flag（D4）。

## Non-Goals

- **M4 命令面代码**：本 Phase 只落契约，命令面实现随 Phase 3（需 M1/M2/M3 资产命令就位后收口）。
- **不新增分层**：cli-ops 作为横切能力，不改变 L0-L5 主链。

## Risks

- **参数映射漂移**：三面若未由 ConfigSpec 生成将产生第二真源；以 ConfigSpec 生成 + 非法 map_to 阻断启动兜底。
- **permission-mode 与审批流叠加**：四档与现有审批流叠加，auto-approve 仍需对高危走审批（不绕过审批流）。

## Open Questions

- 进程守护（start/stop/restart/kill）在 MVP 单进程模型下的实现形态（systemd/子进程）待实现确定。
- gateway 命令的本地服务网关形态待实现收敛。
