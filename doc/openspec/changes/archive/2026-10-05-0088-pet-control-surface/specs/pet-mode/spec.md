## ADDED Requirements

### Requirement: Pet Control Surface
系统 SHALL 提供统一的宠物**控制面**，让宿主层（前台 `/pet [cmd]`、`pet <verb>` CLI argv、WebUI 自然语言）
在宠物运行期间**随时**查看状态、让它停止工作 / 换一件活 / 睡觉 / 叫醒。控制面 SHALL 由**单一门面**
（`PetControl`：verb → 会话操作）收口，CLI 与 `UIAPILayer` 复用同一实现，SHALL NOT 各自实现一套。

控制面 SHALL 支持动词 `status` / `sleep` / `wake` / `assign` / `stop`；**寻址**规则：未指定会话且仅注册一只
宠物 ⇒ 默认作用于该宠物；多只而未指定 ⇒ 拒绝并列出可选会话（SHALL NOT 猜测）；指定但未注册 ⇒ 抛结构化
`PET_NOT_FOUND`（SHALL NOT 静默成功）。`status` SHALL 返回结构化字段（会话 id / 状态 / 是否休眠 / 待办数 /
唤醒计数 / 故障），SHALL NOT 外泄主人偏好与任务正文。控制面 SHALL 只作用**本进程**已注册会话
（跨进程注册表是快照，不驱动 live 会话 —— 有意不做跨进程）。

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
