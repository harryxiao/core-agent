# Change: 新增 deployment 部署/托管 capability（运行环境 / 发布升级 / 健康检查）

## Why

上轮 SDD 功能设计全面性评估（design-completeness-eval.md）三维度之一「托管/部署平台」判定 Core-Agent 缺失，表 63 打分为 ○ 纯自托管（概念层有、工程层缺失）。对照主流 Agent 产品（Devin/Manus 云端 VM、Claude Code 本地进程、OpenClaw/Hermes 云托管 BYOC 模式），Core-Agent 需要一条独立的部署/托管 capability 来描述「跑在哪、怎么跑、怎么升级」：

- 现有 `composition` 只回答「装什么」（bundle 打包分发），`distributed` 只回答「和谁协作」（跨设备拓扑），两者都不覆盖运行环境、发布、健康检查语义。
- 沙箱/容器选型尚未定（0002/0012 design 标注「容器 vs VM vs 进程级未定」），故 deployment 只描述运行环境抽象，不锁定具体选型，避免与后续沙箱落地矛盾。

## What Changes

- **deployment**：新增 capability，4 条 Requirement（自托管运行环境、可选云托管 BYOC、发布与升级、健康检查与生命周期），5 条 Scenario，与 composition/distributed 正交。
- **03-interfaces**：新建 `deployment-interface.md`，固化部署接口契约（启动/停止/探活/升级/回滚/环境配置）。
- **adr.md**：追加 ADR-0028（deployment 作为独立 capability 的边界与运行环境抽象决策）。
- **README.md**：回写三处——03-interfaces 目录树、specs 索引、changes 索引。

## Impact

- **Affected specs**：`deployment`（新增，4 Requirement）
- **Affected docs**：`03-interfaces/deployment-interface.md`（新建）、`01-architecture/adr.md`（+ADR-0028）、`README.md`（3 处回写）
- **Affected code**：无（规格与设计文档落地；工程实现依赖后续任务）
- **Dependencies**：与 composition/distributed 语义正交；运行环境抽象对齐沙箱选型未定（不锁容器 vs VM）；ADR 编号=当前最大+1（0028）
