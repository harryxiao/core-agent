# Design

## Context
0001 落地了六主轴能力。本变更在其上叠加六横切模块，形成"主轴 + 横切"双层结构：loop 是主轴，permission/constraints/observability/context 作为横切中间件插入 loop 关键节点；orchestration 包裹 loop 处理长周期任务；skills 与 evolution 构成结晶经济闭环上下半场。

## Decisions
- **权限是横切不是模块内嵌**：所有副作用动作统一走权限引擎，避免各工具各自实现一套鉴权。
- **Observability 是进化与审批的数据源**：遥测统一供给 evolution 经验采集与审批审计，单一数据源避免分歧。
- **Context 主动治理而非被动堆积**：token 预算 + 信息地图 + 压实三管齐下，对抗信息过载。
- **Skills 与 Evolution 分工**：evolution 负责"结晶/溶解"，skills 负责"版本/灰度/路由"，二者以技能库为唯一交接面。
- **Sandbox 默认开启**：代码执行默认沙箱隔离，失败 fail-closed，绝不降级宿主直跑。

## Risks / Trade-offs
- **审批引入延迟**：高危操作需人工介入，长任务可能阻塞；用审批 TTL + fail-closed 保证安全优先于效率。
- **遥测体量**：全链路 JSONL 可能膨胀，需异步落盘 + 采样 + 脱敏。
- **信息地图维护成本**：hash 失效重建有开销，用增量重建 + 降级全文检索对冲。

## Open Questions
- 沙箱技术选型（容器 vs 微内核 vs 语言级隔离）。
- 多 Agent 子 Agent 的进程模型（同进程 vs 独立进程 vs 网络节点）。
