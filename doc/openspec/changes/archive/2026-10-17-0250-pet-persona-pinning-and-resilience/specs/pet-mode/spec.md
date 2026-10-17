## MODIFIED Requirements

### Requirement: Background Pet Session Lifecycle
系统 SHALL 管理宠物会话的启动、休眠、恢复、异常退避、终止全生命周期，每次唤醒复用 `Loop.run()` 同步薄壳（asyncio.run 桥接）逐次执行，异常退避不残留半运行状态。

唤醒 SHALL **消费一个已派发任务**（队首先出队再执行，任务一次性）；**队列清空 ⇒ 会话进入休眠**（置让行态，复用既有 `SUSPENDED` 语义，**不新增状态枚举**，且 SHALL NOT 编造任务）；**新任务派发 ⇒ 自动唤醒**（清让行态）。休眠/让行中收到唤醒 SHALL 以 `PET_YIELDING` 拒绝（宿主驱动按既有预期态跳过，不空转、不刷屏）。

唤醒执行抛出的异常 SHALL 使会话转入 `BACKOFF` 并记录故障原因，且 SHALL **重新抛给宿主驱动**（驱动按 `FAILED` 记录、不中断其余宠物）—— SHALL NOT 静默吞掉。`BACKOFF` 会话 SHALL 可经控制面 `wake` 恢复为 `ACTIVE`（清故障），恢复后 SHALL 可继续派发与唤醒；失败任务 SHALL NOT 自动回队（是否重派由主人/控制面决定）。

#### Scenario: 启动与唤醒
- **GIVEN** 通过任一入口激活宠物会话
- **WHEN** 宠物会话启动 / 每次唤醒
- **THEN** 经 `Loop.run()` 同步薄壳执行一次自治任务，会话状态一致

#### Scenario: 任务执行后出队
- **GIVEN** 宠物队列中有若干已派发任务
- **WHEN** 宠物被唤醒执行
- **THEN** 队首任务被消费（出队）、交付真实 loop 执行，队列不再包含该任务

#### Scenario: 空闲自主入睡
- **GIVEN** 宠物队列中最后一个任务执行完毕（队列清空）
- **WHEN** 收尾
- **THEN** 会话进入休眠（让行态），**不编造新任务**，后续唤醒以 `PET_YIELDING` 拒绝

#### Scenario: 新任务自动唤醒
- **GIVEN** 宠物处于休眠（让行态）
- **WHEN** 主人派发新任务
- **THEN** 清让行态、自动唤醒，下次唤醒消费该新任务

#### Scenario: 休眠与恢复
- **GIVEN** 宠物会话处于让行或低优先级等待中
- **WHEN** 主循环释放资源
- **THEN** 宠物会话从休眠/让行态恢复，继续待办任务

#### Scenario: 异常退避
- **GIVEN** 宠物会话执行过程中出错
- **WHEN** 异常退避
- **THEN** 会话标记故障态、隔离，不残留半运行状态，不阻塞主循环

#### Scenario: 终止释放
- **GIVEN** 一个运行中的宠物会话
- **WHEN** 终止
- **THEN** 其任务与资源释放，无悬空引用

#### Scenario: 唤醒异常退避与恢复
- **GIVEN** 一只 `ACTIVE` 宠物且队列有待办任务
- **WHEN** 唤醒执行时 loop 抛出异常
- **THEN** 会话转入 `BACKOFF` 且故障原因可查，异常上抛给宿主驱动；控制面 `wake` 后恢复为 `ACTIVE`、故障清空，随后唤醒照常执行

### Requirement: Multi-Pet Management
系统 SHALL 支持同时管理多只宠物，每只宠物拥有独立会话、独立人格、独立任务队列，互不干扰、可独立启停。
宠物注册表 SHALL **跨进程存活**：注册、启停后落盘；新进程加载后可见已注册宠物并对其独立启停。

宠物注册表快照 SHALL 携带每只宠物的**人格**、任务队列与唤醒进度（唤醒计数 / 让行 / 故障 / 状态）；唤醒与任务派发后 SHALL 重新落盘（注册表路径存在时）。新进程恢复后 SHALL 还原人格、队列与计数：SHALL NOT 重放已消费任务，SHALL NOT 丢掉已派发任务。

#### Scenario: 多宠物并行调度
- **GIVEN** 已注册多只宠物
- **WHEN** 系统并行调度多只宠物
- **THEN** 每只独立会话与任务队列，A 宠物异常不影响 B 宠物

#### Scenario: 注册表跨进程存活
- **GIVEN** 某进程激活并注册了一只宠物
- **WHEN** 另一进程加载宠物注册表
- **THEN** 已注册宠物可见（`list`），并可对其独立启停（`stop`）

#### Scenario: 唤醒进度与人格跨进程还原
- **GIVEN** 一只已注册宠物（队首 2 个任务、带人格），被唤醒 1 次
- **WHEN** 同一注册表文件被新进程加载
- **THEN** 剩余任务 1 个、唤醒计数 1、人格字段完整（恢复后的唤醒 prompt 仍含该人格）

### Requirement: Pet Persona and Prompt
系统 SHALL 支持通过 pet.md/prompt 为每只宠物设定角色、性格、喜好，宠物行为与输出风格受其人格约束

人格 SHALL **随会话固定**（persona pinning）：激活时注入的人格 SHALL 随注册表快照落盘，进程恢复后 SHALL 重建同一人格（角色/性格/喜好/prompt 逐字一致）；恢复时显式注入的人格 SHALL 优先于快照。未配置人格的会话 SHALL 保持既有裸任务行为（逐字不变）。

#### Scenario: 人格约束行为
- **GIVEN** 一只宠物配置了 pet.md 人格
- **WHEN** 宠物执行任务并产出行为
- **THEN** 行为与输出风格符合其角色、性格、喜好设定

#### Scenario: 人格跨进程固定
- **GIVEN** 以 pet.md 人格激活并注册宠物
- **WHEN** 新进程从注册表恢复会话并唤醒
- **THEN** 唤醒 prompt 仍含该人格（名称/性格/喜好/prompt），SHALL NOT 退化为裸任务文本

### Requirement: Pet Control Surface
系统 SHALL 提供统一的宠物**控制面**，让宿主层（前台 `/pet [cmd]`、`pet <verb>` CLI argv、WebUI 自然语言）
在宠物运行期间**随时**查看状态、让它停止工作 / 换一件活 / 睡觉 / 叫醒。控制面 SHALL 由**单一门面**
（`PetControl`：verb → 会话操作）收口，CLI 与 `UIAPILayer` 复用同一实现，SHALL NOT 各自实现一套。

控制面 SHALL 支持动词 `status` / `sleep` / `wake` / `assign` / `stop`；**寻址**规则：未指定会话且仅注册一只
宠物 ⇒ 默认作用于该宠物；多只而未指定 ⇒ 拒绝并列出可选会话（SHALL NOT 猜测）；指定但未注册 ⇒ 抛结构化
`PET_NOT_FOUND`（SHALL NOT 静默成功）。`status` SHALL 返回结构化字段（会话 id / 状态 / 是否休眠 / 待办数 /
唤醒计数 / 故障），SHALL NOT 外泄主人偏好与任务正文。控制面 SHALL 只作用**本进程**已注册会话
（跨进程注册表是快照，不驱动 live 会话 —— 有意不做跨进程）。

`wake` 对 `ACTIVE` 会话 SHALL 清让行（既有语义），对 `BACKOFF` 会话 SHALL 执行故障恢复（`BACKOFF → ACTIVE`、清故障）。控制面的变更动词（`sleep` / `wake` / `assign` / `stop`）SHALL 在返回前把注册表落盘（注册表路径存在时），使新进程可见其效果。

#### Scenario: 查看状态
- **GIVEN** 本进程有一只运行中的宠物
- **WHEN** 前台 `/pet status`
- **THEN** 返回结构化状态（会话 id / 状态 / 是否休眠 / 待办数 / 唤醒计数 / 故障），不含主人偏好与任务正文

#### Scenario: 睡觉与叫醒
- **GIVEN** 一只 `ACTIVE` 的宠物
- **WHEN** 控制面 `sleep`，其后 `wake`
- **THEN** `sleep` 置让行态（休眠，后续唤醒被拒 `PET_YIELDING`）；`wake` 清让行态恢复

#### Scenario: 换一件活
- **GIVEN** 一只宠物（可处于让行/休眠）
- **WHEN** 控制面 `assign` 一件新任务
- **THEN** 新任务入队并清让行态（自动唤醒），下次唤醒消费之

#### Scenario: 单宠物默认寻址
- **GIVEN** 本进程仅注册一只宠物
- **WHEN** 控制动词未指定会话
- **THEN** 默认作用于该宠物

#### Scenario: 多宠物未指定被拒
- **GIVEN** 本进程注册多只宠物
- **WHEN** 控制动词未指定会话
- **THEN** 拒绝并列出可选会话 id，SHALL NOT 猜测

#### Scenario: 未知会话被拒
- **GIVEN** 一个未注册的会话 id
- **WHEN** 任一控制动词
- **THEN** 抛结构化 `PET_NOT_FOUND`（CLI 退出码 1），SHALL NOT 静默成功

#### Scenario: 退避恢复
- **GIVEN** 一只 `BACKOFF` 宠物（故障已记录）
- **WHEN** 控制面 `wake`
- **THEN** 状态恢复为 `ACTIVE`、故障字段清空，随后可派发与唤醒
