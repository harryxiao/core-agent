# Change: 新增 cli-ops 运维命令面 + configuration CLI 覆盖层 + permission-mode

## Why

架构审计（2026-09-26）维度 B/C：core-agent 自身运维 CLI 命令集缺失（仅三模入口 TUI/serve/app，无 status/doctor/install/mcp 等命令）；启动参数与配置参数无一一对应（configuration 只有 yaml+env+默认值，无 CLI 覆盖层；permission 无 permission-mode 启动开关）。本 change 闭合维度 B/C：新增横切能力 cli-ops（命令集 + 参数映射）、configuration 增加 CLI 覆盖层 + ConfigSpec 单一真源、permission 增加 permission-mode 四档启动开关。

## What Changes

- **cli-ops（新增 capability，第 26 spec）**：运维命令集六组（生命周期/状态/资产/连接/安全/网关）+ 启动参数映射优先级链 CLI flag > env > config.yaml > 默认值。
- **配置源与分层**（configuration，MODIFIED）：新增 CLI 覆盖层（最高优先级）；ConfigSpec 每项声明 cli_flag/env_var/default/map_to；暴露面按 core/advanced/hidden 分级。
- **权限模式**（permission，ADDED）：read-only / interactive / auto-approve / high-risk-block 四档，映射 config.permission.mode，CLI --permission-mode。
- **cli-ops 三件套**：新建 `openspec/specs/cli-ops/spec.md` + `03-interfaces/cli-ops-interface.md`。
- **delta 双写**：`changes/0029-cli-ops/specs/{cli-ops,configuration,permission}/spec.md`。
- **adr.md**：追加 ADR-0038（cli-ops 命令面 + 参数映射）。
- **architecture-overview.md**：6 处同步（横切 5→6、ASCII 横切行、横切能力表、核心组件表、运行时视图、部署目录树）。
- **requirements.md**：追加 1.26 CLI 运维命令面。
- **design-completeness-eval.md**：模块数字口径 25→26。

## Impact

- **Affected specs**：`cli-ops`（新增，第 26 spec）；`configuration`（扩展：Purpose + MODIFIED「配置源与分层」）；`permission`（扩展：Purpose + 追加「权限模式」）
- **Affected docs**：`openspec/specs/cli-ops/spec.md`（新建）、`03-interfaces/cli-ops-interface.md`（新建）、`openspec/specs/configuration/spec.md`（Purpose + Requirement）、`openspec/specs/permission/spec.md`（Purpose + Requirement）、`openspec/changes/0029-cli-ops/`（新建三件套 + delta）、`00-product/requirements.md`（+1.26）、`00-product/design-completeness-eval.md`（25→26）、`01-architecture/adr.md`（+ADR-0038）、`01-architecture/architecture-overview.md`（6 处同步）
- **Affected code**：M5（configuration：CLI 覆盖层 + ConfigSpec）、M6（permission：permission-mode 四档）本 Phase 回填；M4（cli-ops 命令面）代码随 Phase 3
- **Dependencies**：ADR 编号=当前最大+1（0038）；specs 25→26 需同步 requirements.md 1.x 清单与 design-completeness-eval.md 数字口径；ConfigSpec 必须全量声明，CLI/env/yml 三面由 ConfigSpec 生成，禁止硬编码第二真源
