# Change: 新增宠物模式（pet-mode）后台自治循环 + 宿主层三入口交互面

## Why

架构审计（`coding-plan/architecture-audit.md`，2026-09-26）后补充需求：core-agent 是纯核心运行时库（无 CLI/REPL/TUI），主循环 `Loop.run()`（同步薄壳）完成即返回，无「后台长驻低优先级任务通道」；宿主层（CLI/WebUI/IM）无宠物式交互入口。本 change 新增 pet-mode capability：在编排层扩展后台自治循环（复用 `Loop.run()` 同步薄壳 + orchestration 任务状态机 `SUSPENDED` 承载让行），宿主层新增三入口（`/pet` 斜杠命令、`pet <verb>` CLI argv、WebUI 自然语言激活）承载重复简单任务（信息收集/闲逛探索）、偏好追踪、定期反馈/惊喜，相当于"人类养宠物"——做当前不太重要的事、了解主人偏好、制造惊喜。

## What Changes

- **Background Pet Session Lifecycle**（pet-mode，ADDED）：系统 SHALL 管理宠物会话的启动、休眠、恢复、异常退避、终止全生命周期，复用 `Loop.run()` 同步薄壳逐次唤醒。
- **Pet Task Types**（pet-mode，ADDED）：系统 SHALL 支持重复简单任务（信息收集、闲逛探索）作为宠物会话的可分配任务类型。
- **Low-Priority Yielding**（pet-mode，ADDED）：系统 SHALL 保证宠物低优先级让行——休眠/让行复用 orchestration 任务状态机 `SUSPENDED`；主循环 busy 时宠物不抢锁。
- **Preference Tracking**（pet-mode，ADDED）：系统 SHALL 追踪主 Agent（主人）偏好，以 `MemoryEntry.source=user` 落 L2 facts 层。
- **Three-Entry Activation**（pet-mode，ADDED）：系统 SHALL 支持三入口激活——`/pet` 斜杠命令（UI 层，候选经统一 API `list_tools` 拉取）、`pet <verb>` CLI argv（cli-ops-interface `CommandGroup` 扩展）、WebUI 自然语言激活（消息驱动会话）。
- **Periodic Feedback and Surprise**（pet-mode，ADDED）：系统 SHALL 支持宠物定期与主 Agent 沟通/反馈，并基于主人偏好制造惊喜。
- **Pet Architecture Layers**（pet-mode，ADDED）：系统 SHALL 将宠物实现为解耦的四层架构：基础属性层（角色/性格/喜好/物种）、自主目标循环层、探索工具集层、安全边界层；各层可独立配置与替换。
- **Multi-Pet Management**（pet-mode，ADDED）：系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停。
- **Pet Persona and Prompt**（pet-mode，ADDED）：系统 SHALL 支持通过 pet.md/prompt 为每只宠物设定角色、性格、喜好，宠物行为与输出风格受其人格约束。
- **Pet Character Library**（pet-mode，ADDED）：系统 SHALL 提供宠物角色库，支持从预置角色模板创建宠物、自定义角色、导入/导出角色定义。
- **Exploration Toolset**（pet-mode，ADDED）：系统 SHALL 为宠物提供受限探索工具集（只读优先），供信息收集与闲逛探索使用，工具清单可配置、需授权。
- **Pet Safety Bounds**（pet-mode，ADDED）：系统 SHALL 为宠物行为施加安全边界：只读优先、不可逆操作禁止、爆炸半径可控、越界即暂停并通知主人。
- **Pet Notification**（pet-mode，ADDED）：系统 SHALL 支持宠物主动通知主人（如「发现插件X一键生成测试用例，帮你试3次都成功」），通知异步投递、不阻塞主循环。
- **Pet Micro-tasks**（pet-mode，ADDED）：系统 SHALL 支持宠物执行日常随机小任务（终端散步、系统小提示、给代码加无厘头注释），其中侵入性任务可配置关闭。
- **delta 双写**：`changes/0030-pet-mode/specs/pet-mode/spec.md`（delta 与 specs 根目录逐字一致）。
- **pet-mode-interface.md**：后续新建 `03-interfaces/pet-mode-interface.md`。
- **adr.md**：追加 ADR-0039（宠物模式定位与边界）。

## Impact

- **Affected specs**：`pet-mode`（新增 capability：14 Requirement）
- **Affected docs**：`openspec/changes/0030-pet-mode/`（新建三件套 + delta）、`openspec/specs/pet-mode/spec.md`（双写）、`03-interfaces/pet-mode-interface.md`（后续新建）、`01-architecture/adr.md`（+ADR-0039）、`01-architecture/architecture-overview.md`（后续补核心组件表/运行时视图）、`00-product/requirements.md`（1.27 段补模块清单）、`00-product/design-completeness-eval.md`（+1 capability，同步「N 模块/N capability」数字）、`coding-plan/phase-8.md`（新增）、`coding-plan/contracts_summary.md`（+pet-mode 条目）、`coding-plan/README.md`（+Phase 8 行）
- **Affected code**：本 Phase 只落契约（proposal/design/tasks/delta）；后台自治循环（编排层）+ 三入口（宿主层）+ 偏好读写代码随后续 Phase
- **Dependencies**：ADR 编号=当前最大+1（0039）；change 编号=changes/ 当前最大+1（0030，与 ADR 空间独立）；复用 `Loop.run()` 同步薄壳与 orchestration 任务状态机 `SUSPENDED`，不新造循环引擎
