# Design

## Context

全局架构审查（2026-09-22）发现：涉及连接的模块（distributed / llm-provider / git）在断线 / 超时 / 认证失败等异常场景下缺少连接管理语义；tool-use 的 requirements R3/R4 已声明但 spec 正文缺失。本 change 补齐高优先级四模块的异常处理与连接管理语义。

## Decisions

- **distributed R8「A2A 连接管理」**：连接保活（keepalive 心跳 / heartbeat）+ 超时（timeout）检测 + 断线自动重连（reconnect，指数退避）+ 连接与任务资源显式释放 + 委派重试幂等（按任务 ID 去重，同一任务不重复执行）
- **llm-provider R6「模型调用可靠性」**：失败重试（retry，指数退避）+ 超时控制 + 降级切换备用 provider/model + 底层连接复用（connection reuse / keep-alive）+ 流式断流恢复；与既有 R4「错误归一化」不冲突（归一化是结果、可靠性是过程）
- **tool-use R3/R4**：补齐 requirements 已声明的「撤销函数 / 时间旅行回滚」（P0）与「超时 / 资源上限」（P1）spec 正文
- **git R5「远程操作可靠性」**：clone/pull/push 的超时（timeout）控制、认证失败明确报错不泄露凭据、断线重试（retry，指数退避）、操作结束释放连接资源
- **spec 扩展非新 cap**：四模块均归属既有 capability，不新建 capability

## Risks / Trade-offs

- **幂等去重依赖任务 ID 稳定**：委派幂等需 A2A 任务携带稳定 ID，与分布式既有任务标识约定保持一致
- **降级切换可用性**：llm-provider 降级依赖备用 provider 配置，未配置备用时降级退化为明确报错
- **工作区一致性**：git 断线重试达上限后须保证工作区一致（不半写），避免损坏工作区

## Open Questions

- 指数退避的具体参数（初始间隔 / 最大重试次数 / 退避因子）留待编码阶段确定
- 流式断流的「部分返回 vs 触发重试」策略粒度留待实现阶段确定
