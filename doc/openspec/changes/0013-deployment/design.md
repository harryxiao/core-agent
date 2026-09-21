# Design: deployment 部署/托管 capability 的边界与运行环境抽象

## Context

SDD 功能设计全面性评估（design-completeness-eval.md）三维度之一「托管/部署平台」判定 Core-Agent 缺失，表 63 打分为 ○ 纯自托管（概念层有、工程层无规格）。对照主流产品：

- Devin/Manus：云端 VM 托管，用户零环境成本；
- Claude Code：本地进程，零托管；
- OpenClaw/Hermes：自托管 + 可选云托管（BYOC，bring your own cloud）。

现有 capability 语义边界：

- `composition`：决定「装什么」——bundle 打包与分发；
- `distributed`：决定「和谁协作」——跨设备拓扑（A2A/MCP、NAT 穿透等）；
- 两者都不回答「跑在哪、怎么跑、怎么升级」，故需独立 `deployment` capability。

关键约束：沙箱/容器选型尚未定（0002-sandbox、0012-gap-closure 的 design 均标注「容器 vs VM vs 进程级未定」）。若 deployment 过早锁定具体运行形态（如硬编码 Docker），会与后续沙箱落地冲突。

## Decisions

1. **独立 capability，而非并入 composition/distributed**：deployment 只描述运行环境抽象与生命周期，与「装什么」「和谁协作」正交，避免语义耦合。
2. **运行环境抽象，不锁定具体选型**：以「运行环境」抽象概念（进程 / 容器）描述，Spec 中不硬编码 Docker/K8s/VM，具体选型留给后续沙箱与部署落地 change 收敛。
3. **自托管优先，可选云托管 BYOC**：默认自托管（贴合 Core-Agent 本地/私有定位），同时预留可选云托管 BYOC 接口，覆盖 Devin/Manus 类云端形态但不强绑定。
4. **发布与升级含回滚语义**：升级失败自动回滚，保证运行环境不处于半升级状态（对齐「版本升级与回滚」Scenario）。
5. **健康检查与生命周期独立成 Requirement**：探活端点 + 启动/停止/重启，供监控与恢复依赖，不与权限/沙箱耦合。

## Risks

- **与后续沙箱落地冲突**：若沙箱最终选择容器，deployment 的「运行环境抽象」需能收敛到容器；已通过「抽象不锁选型」规避。
- **云托管 BYOC 范围膨胀**：BYOC 若扩展到多租户/计费/配额，会超出 capability 边界；本次只固化「可选云托管」接口契约，不引入平台运营语义。
- **发布/升级与 composition 的分发语义重叠**：composition 打包 bundle、deployment 负责升级流程，两者边界需在实现时明确（升级入口在 deployment，产物来源在 composition）。

## Open Questions

- 运行环境抽象的落地选型（进程级 supervisor / 容器 / VM）待沙箱 decision 收敛后确定。
- 健康探活端点的具体协议（HTTP / gRPC / 本地 socket）留待工程实现。
- 云托管 BYOC 是否纳入首个 coding 里程碑，还是先自托管单机跑通。
