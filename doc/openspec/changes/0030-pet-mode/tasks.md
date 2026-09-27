# Tasks

## 1. 契约层 — pet-mode spec delta（P0，本 Phase）

- [ ] 1.1 写 6 Requirement（Background Pet Session Lifecycle / Pet Task Types / Low-Priority Yielding / Preference Tracking / Three-Entry Activation / Periodic Feedback and Surprise）
- [ ] 1.2 proposal What Changes ADDED bullet 标题与 delta Requirement 逐字一致
- [ ] 1.3 delta 与 specs/pet-mode/spec.md 双写逐字一致

## 2. 编排层 — 后台自治循环扩展（契约层，代码随后续 Phase）

- [ ] 2.1 后台自治循环复用 Loop.run() 同步薄壳
- [ ] 2.2 让路策略：RLock + 低优先级让行 + SUSPENDED 休眠/让行态
- [ ] 2.3 主循环 busy 时不抢锁

## 3. 宿主层 — 三入口激活（契约层，代码随后续 Phase）

- [ ] 3.1 /pet 斜杠命令（UI 层，list_tools 拉取候选，不进内核接口）
- [ ] 3.2 pet <verb> CLI argv（cli-ops-interface CommandGroup 扩展）
- [ ] 3.3 WebUI 自然语言激活（UIAPILayer / IMGateway.on_message 消息驱动）

## 4. 偏好读写（契约层，代码随后续 Phase）

- [ ] 4.1 MemoryEntry.source=user 落 L2 facts 层
- [ ] 4.2 宠物写偏好不新造记忆层

## 5. pet-mode 8 Requirement 实现任务（契约层，代码随后续 Phase）

- [ ] 5.1 Pet Architecture Layers（四层架构）：实现解耦四层（基础属性层/自主目标循环层/探索工具集层/安全边界层），各层独立配置与替换。依赖：CORE-PET-R7。验收：替换任一层不影响其余层
- [ ] 5.2 Multi-Pet Management（多宠物调度）：多宠物独立会话/独立人格/独立任务队列，可独立启停。依赖：CORE-PET-R8。验收：A 宠物异常不影响 B 宠物
- [ ] 5.3 Pet Persona and Prompt（人格模型）：pet.md/prompt 设定角色/性格/喜好。依赖：CORE-PET-R9。验收：行为与输出风格受人格约束
- [ ] 5.4 Pet Character Library（角色库）：预置角色模板 + 自定义 + 导入/导出。依赖：CORE-PET-R10。验收：模板创建/自定义/导入导出可用
- [ ] 5.5 Exploration Toolset（探索工具集）：受限只读优先工具集，清单可配置、需授权。依赖：CORE-PET-R11。验收：仅授权只读工具可用
- [ ] 5.6 Pet Safety Bounds（安全边界）：只读优先、不可逆操作禁止、爆炸半径可控，越界即阻断、暂停并通知主人。依赖：CORE-PET-R12。验收：越界操作被阻断、宠物暂停并通知主人
- [ ] 5.7 Pet Notification（通知通道）：宠物主动通知主人，通知异步投递、不阻塞主循环。依赖：CORE-PET-R13。验收：异步投递、主循环不被阻塞
- [ ] 5.8 Pet Micro-tasks（微任务开关）：日常随机小任务（终端散步/系统小提示/无厘头注释），侵入性任务可配置关闭。依赖：CORE-PET-R14。验收：只执行已启用任务，侵入性可关闭
