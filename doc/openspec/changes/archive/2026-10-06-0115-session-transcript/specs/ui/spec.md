# UI Specification Delta

## MODIFIED Requirements

### Requirement: 会话注册表持久化与跨入口共享
统一后端 API 层 SHALL 将对话会话标识登记于**跨进程共享的持久注册表**（落 `$CORE_STATE_DIR` 下 JSON 快照），使 CLI / Web / Desktop 三种入口（含各自独立进程）对会话标识的**创建与校验共享同一事实来源**。注册表 SHALL 采用**读透 + 写时合并**语义：校验（`exists`）与枚举（`list`）每次读回磁盘，创建（`create`）先读回磁盘再合并写回 —— 以支持「长驻 `serve` 进程看到另一进程（CLI）新建的会话」；创建 SHALL 以**进程内互斥**保护，使**同进程多线程**并发创建不相互覆盖。**跨进程**同刻并发创建 SHALL NOT 被声称受保护（进程内互斥不跨进程，属已知局限，不得据此断言跨进程安全）。

注册表持久化 SHALL NOT 放宽会话校验：未登记于注册表的 `session_id` SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`）。注册表为**派生状态**，其文件缺失或损坏 SHALL 使系统以空注册表启动，SHALL NOT 阻断启动。

后端 API 层 SHALL 提供**会话枚举**能力（HTTP `GET /sessions`），返回注册表内全部对话会话（标识 + 模式），三入口所见一致。

注：本 Requirement 与「三模统一内核启动」正交 —— 后者约束 `session_id` 的**值语义**（生成后无改写透传至循环与记忆写入），本 Requirement 约束会话标识的**持久化与跨入口可见性**。

#### Scenario: 跨进程会话可见
- **GIVEN** CLI 进程经 `create_session` 建立了一个会话
- **WHEN** 另一进程（如 `serve` 或另一次 CLI 调用）以该 `session_id` 发起 `run_loop` / 读记忆
- **THEN** 该会话被认作有效，不再返回 `UI_SESSION_NOT_FOUND`

#### Scenario: 会话枚举端点
- **GIVEN** 注册表内已有若干对话会话
- **WHEN** 经后端 API（`GET /sessions`）枚举会话
- **THEN** 返回注册表内全部对话会话（标识 + 模式，含创建时间），跨入口一致

#### Scenario: 未登记标识仍拒绝
- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 经后端 API 发起会话操作
- **THEN** 返回 `UI_SESSION_NOT_FOUND`（fail-closed，不放宽既有校验）

## ADDED Requirements

### Requirement: 会话转录的读取面

后端 API 层 SHALL 提供会话转录的读取面：HTTP `GET /session/{session_id}/messages` 返回该会话的
对话转录（按追加次序）。**未登记于注册表**的会话标识 SHALL 仍被拒绝（`UI_SESSION_NOT_FOUND`），
转录的读取面 SHALL NOT 放宽既有会话校验。

会话枚举（`GET /sessions`）的条目 SHALL 附**从转录派生**的 `title`（该会话**首条用户消息**截断；
该会话无用户消息 ⇒ 空串，SHALL NOT 以任何内容顶替）与 `updated_at`（最近一条转录的时间戳；
该会话无转录 ⇒ 回落注册表 `created_at`）：派生值 SHALL NOT 写入会话注册表（注册表只承载标识与
模式，不承载内容；避免第二真源）。**未注入转录存储**时（如库层直调 / 测试替身），枚举条目 SHALL
保持既有形状（只增不减 ⇒ 既有消费方不受影响）。

#### Scenario: 读取本会话转录

- **GIVEN** 一个已登记的会话，且其转录已有若干轮
- **WHEN** 经 HTTP `GET /session/{session_id}/messages` 读取
- **THEN** 按追加次序返回该会话的对话转录

#### Scenario: 未登记标识仍拒绝

- **GIVEN** 一个未登记于注册表的 `session_id`
- **WHEN** 请求该会话的转录
- **THEN** 返回 `UI_SESSION_NOT_FOUND`（fail-closed，不放宽既有校验）

#### Scenario: 会话枚举附派生标题与最近活跃

- **GIVEN** 注册表内已有若干会话，其中某会话的转录含用户消息
- **WHEN** 经 HTTP `GET /sessions` 枚举
- **THEN** 该会话条目附 `title`（其首条用户消息截断）与 `updated_at`；
  无用户消息的会话 `title` 为空串（SHALL NOT 伪造出标题），`updated_at` 回落其 `created_at`

#### Scenario: 转录缺席时枚举形状不变

- **GIVEN** 未注入转录存储
- **WHEN** 经 HTTP `GET /sessions` 枚举
- **THEN** 条目保持既有形状（标识 + 模式 + 创建时间），不新增派生字段
