## ADDED Requirements

### Requirement: 单次推理多工具动作

一次推理产出多个原生工具调用时，系统 SHALL **执行全部调用**（按 provider `index` 升序），
SHALL NOT 只执行首个或静默丢弃其余调用。

- 每个调用 SHALL 作为独立动作走既有执行体：中间件 → 确认门 → 执行 → 观测回灌 → 事件
  （`action_started` / `action_completed` / `step_completed`）→ 压实阈值判定；载荷键集不变。
- 批次内任一调用无法解析（参数非 JSON 对象 / 缺函数名）时，SHALL 以**单个终止失败动作**
  （`LLM_PLAN_PARSE_FAILED`）结束本轮推理，SHALL NOT 部分执行该批次。
- 完全相同的调用（`tool_id` 与规范化参数逐字相同）在一个批次内 SHALL 只执行一次；同一轮内
  **紧邻重复**的写动作（`file_write` 非追加模式、`file_patch`）若上一次已成功，SHALL 跳过执行并
  复用上次结果。被抑制的调用 SHALL 仍产出正常动作事件、观测回灌，并记 `action_deduplicated`
  遥测（含 `scope` / `tool_id` / `round`；SHALL NOT 含参数正文）。
- 单调用、文本回复与非流式 planner 路径的事件序、观测与结果 SHALL 逐字不变。

#### Scenario: 批量调用全部执行
- **GIVEN** 一次推理返回按序排列的两个原生工具调用
- **WHEN** 循环执行该次推理
- **THEN** 两个工具各被执行一次，各产出一组动作事件与观测，轮次推进 2

#### Scenario: 批内重复只执行一次
- **GIVEN** 同一批次内两个完全相同的工具调用
- **WHEN** 循环执行该批次
- **THEN** 工具处理器只被调用一次，另一次记 `action_deduplicated`（`scope="batch"`）

#### Scenario: 紧邻重复写复用结果
- **GIVEN** 同一轮内连续两次完全相同的 `file_write`（覆盖模式）且第一次成功
- **WHEN** 第二次动作执行
- **THEN** 不再写盘，返回第一次的结果并记 `action_deduplicated`（`scope="turn"`）

#### Scenario: 解析失败不部分执行
- **GIVEN** 一次推理的两个原生调用中有一个参数 JSON 非法
- **WHEN** 循环处理该批次
- **THEN** 本轮以 `LLM_PLAN_PARSE_FAILED` 终止失败收尾，两个调用**均未执行**
