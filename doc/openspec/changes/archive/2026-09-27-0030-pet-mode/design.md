# Design: 宠物模式后台自治循环 + 宿主层三入口的边界

## Context

架构审计（`coding-plan/architecture-audit.md`，2026-09-26）后补充：core-agent 是纯核心运行时库（无 CLI/REPL/TUI），主循环 `Loop.run()` 完成即返回；宿主层（CLI/WebUI/IM）无宠物式交互入口。本 change 在编排层扩展后台自治循环，宿主层新增三入口激活宠物会话，承载重复简单任务 / 偏好追踪 / 定期反馈。

## Decisions

- **定位 = 编排层扩展 + 宿主层三入口**：pet-mode 不是横切能力、不是独立内核模块、不是纯宿主组件；是编排层「后台自治循环」扩展 + 宿主层三入口交互面。
- **后台自治循环复用 `Loop.run()` 同步薄壳**：每次唤醒 = 一次 `run()` 调用（同步薄壳，asyncio.run 桥接），不新造循环引擎。
- **让路策略 = 同步 + RLock**：宠物低优先级让行——休眠/让行中复用 orchestration 任务状态机 `SUSPENDED`（真实存在）；异常退避为 pet-mode 自身会话态（语义对齐 plugin-registry 异常隔离「插件故障→标记+隔离」，但 plugin-registry 无 `FAULTED` 枚举，故宠物故障态在 pet-mode spec 内 ADDED 定义，不臆造 plugin 状态机枚举名）；主循环 busy 时宠物不抢锁。
- **三入口激活**：
  - `/pet` 斜杠命令：UI 层交互，候选来自 plugin-registry 注册的 command/tool 元数据经统一 API 的 `list_tools` 拉取（不进内核接口）。
  - `pet <verb>` CLI argv：cli-ops-interface 的 `CommandGroup` 扩展。
  - WebUI 自然语言「启动宠物 + 任务」：经 `UIAPILayer` / `IMGateway.on_message` 消息驱动会话（`on_message` 统一映射为会话事件进入内核 loop 执行），激活靠 Agent 理解（无现成 NL 路由层）。
- **偏好读写**：`MemoryEntry.source=user` 落 L2 facts 层（source 字段注释明确 loop/evolution/user），宠物写偏好；不新造记忆层。
- **四层架构（Pet Architecture Layers）**：宠物解耦为四层——基础属性层（角色/性格/喜好/物种）、自主目标循环层、探索工具集层、安全边界层；各层可独立配置与替换，替换任一层不影响其余层。
- **多宠物调度（Multi-Pet Management）**：同时管理多只宠物，每只独立会话、独立人格、独立任务队列，互不干扰、可独立启停；A 宠物异常不影响 B 宠物。
- **人格模型（Pet Persona and Prompt）**：通过 pet.md/prompt 为每只宠物设定角色、性格、喜好；宠物行为与输出风格受其人格约束。
- **角色库（Pet Character Library）**：提供宠物角色库，支持从预置角色模板创建、自定义角色、导入/导出角色定义。
- **探索工具集（Exploration Toolset）**：受限探索工具集（只读优先），供信息收集与闲逛探索使用；工具清单可配置、需授权。
- **安全边界（Pet Safety Bounds）**：只读优先、不可逆操作禁止、爆炸半径可控；越界即暂停并通知主人。
- **通知通道（Pet Notification）**：宠物主动通知主人，通知异步投递、不阻塞主循环。
- **微任务开关（Pet Micro-tasks）**：日常随机小任务（终端散步、系统小提示、给代码加无厘头注释）；侵入性任务可配置关闭。

## Non-Goals

- 不实现横切能力（不并入 ui）；pet-mode 是编排层扩展。
- 不改动 `Loop.run()` 主循环语义；后台循环是主循环之上的自治调度。
- 不新造 NL 路由层；WebUI 激活靠 Agent 理解。

## Risks

- 让路死锁：锁模型下宠物若抢锁可能阻塞主循环；以 RLock + 低优先级让行 + `SUSPENDED` 状态兜底。
- 偏好写脏：宠物写偏好若污染 L2 事实层；以 `MemoryEntry.source=user` 明确来源 + 偏好隔离兜底。
- 三入口语义漂移：`/pet`、`pet <verb>` CLI、WebUI 三入口若各自实现激活逻辑会产生第二真源；以统一 pet session 生命周期契约收口。

## Open Questions

- 后台自治循环的调度节律（唤醒周期 / 时间片）待实现确定。
- `/pet` 斜杠命令与 cli-ops 命令面（M4）的归属边界待实现收敛。
