# Pet-Mode Specification Delta

## ADDED Requirements

### Requirement: Task Result Query

系统 SHALL 提供宠物**最近一次任务结果**的只读查询面：`PetControl.result(session_id=None)` SHALL 返回结构化字段
（会话 id / 是否有结果 / 结果正文 / 成败），并经 CLI `pet result` 与 `UIAPILayer` **复用同一实现**（照既有单一门面
口径）。寻址规则 SHALL 与既有控制动词**逐字一致**（未指定且仅注册一只 ⇒ 默认作用于该宠物；多只未指定 ⇒ 拒绝并
列出可选会话；指定但未注册 ⇒ 抛结构化 `PET_NOT_FOUND`）。该查询面 SHALL 只作用**本进程**已注册会话，SHALL 只
暴露**最近一次**结果，SHALL NOT 落盘（不进 `snapshot` / 跨进程注册表）。该查询面 SHALL NOT 改变 `status` 的返回面
—— `status` SHALL 仍**不含**主人偏好与任务正文。无结果时（会话尚未唤醒过）SHALL 明确报「无结果」，SHALL NOT 编造正文。

#### Scenario: 查询最近结果
- **GIVEN** 本进程有一只完成过一轮唤醒的宠物
- **WHEN** 控制面 `result`（CLI `pet result` / 前台 `/pet result`）
- **THEN** 返回结构化字段（会话 id / 是否有结果 / 结果正文 / 成败）

#### Scenario: status 返回面不受影响
- **GIVEN** 一只已有最近结果的宠物
- **WHEN** 控制面 `status`
- **THEN** 返回字段与既有口径**逐字不变**，SHALL NOT 含主人偏好与任务正文

#### Scenario: 无结果不谎报
- **GIVEN** 一只尚未唤醒过的宠物
- **WHEN** 控制面 `result`
- **THEN** 明确「无结果」（`has_result=false`），SHALL NOT 编造正文

#### Scenario: 未知会话被拒
- **GIVEN** 一个未注册的会话 id
- **WHEN** 控制面 `result`
- **THEN** 抛结构化 `PET_NOT_FOUND`，SHALL NOT 静默成功
