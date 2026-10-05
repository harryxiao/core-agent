# UI Specification Delta

## ADDED Requirements

### Requirement: 会话注册表持久化与跨入口共享
统一后端 API 层 SHALL 将对话会话标识登记于**跨进程共享的持久注册表**（落 `$CORE_STATE_DIR` 下 JSON 快照），使 CLI / Web / Desktop 三种入口（含各自独立进程）对会话标识的**创建与校验共享同一事实来源**。注册表 SHALL 采用**读透 + 写时合并**语义：校验（`exists`）与枚举（`list`）每次读回磁盘，创建（`create`）先读回磁盘再合并写回 —— 以支持「长驻 `serve` 进程看到另一进程（CLI）新建的会话」与「并发创建不相互覆盖」。

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
