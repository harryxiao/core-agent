## MODIFIED Requirements

### Requirement: 单次推理多工具动作

一次推理产出多个原生工具调用时，系统 SHALL **执行全部调用**（按 provider `index` 升序），
SHALL NOT 只执行首个或静默丢弃其余调用。

- 每个调用 SHALL 作为独立动作走既有执行体：中间件 → 确认门 → 执行 → 观测回灌 → 事件
  （`action_started` / `action_completed` / `step_completed`）→ 压实阈值判定；载荷键集不变。
- **只读动作并发**：组内**连续**的只读动作（工具声明的 coeffects 不含 `write` / `spawn` /
  `outbound` / `delegate` 词元、且非终止、去重键互不相同）SHALL 并发执行；写类 / 有副作用 /
  未知工具的动作 SHALL 串行执行并作为并发批次之间的**屏障**（保证写序与撤销快照序）。并发批量
  SHALL NOT 越过 `max_rounds` 剩余额度；构造参数 `concurrent_reads=False` 时 SHALL 逐字回到
  串行路径。
- **按序提交**：并发执行的结果 SHALL 按动作原序提交（`action_started` 按原序在启动前发出；
  `action_completed` / `step_completed` / 观测回灌 / 失败回滚 / 轮次推进 SHALL 按原序）。
  压实阈值与 token 预算判定 SHALL 在该批动作提交完成后执行。
- 批次内任一调用无法解析（参数非 JSON 对象 / 缺函数名）时，SHALL 以**单个终止失败动作**
  （`LLM_PLAN_PARSE_FAILED`）结束本轮推理，SHALL NOT 部分执行该批次。
- 完全相同的调用（`tool_id` 与**规范化参数**逐字相同）在一个批次内 SHALL 只执行一次；同一轮内
  **紧邻重复**的写动作（`file_write` 非追加模式、`file_patch`）若上一次已成功，SHALL 跳过执行并
  复用上次结果。被抑制的调用 SHALL 仍产出正常动作事件、观测回灌，并记 `action_deduplicated`
  遥测（含 `scope` / `tool_id` / `round`；SHALL NOT 含参数正文）。
- **参数规范化面**（仅 `file_write` / `file_patch`，用于去重键，不改变执行参数）：`path` SHALL
  按 `~` 展开、绝对化、规范化（`..` / 重复分隔符）并在 Windows 折大小写；`content` /
  `old_content` / `new_content` SHALL 将 CRLF 归一为 LF；`file_write` 的 `mode` 缺省 SHALL 与
  显式 `"w"` 等价，`"a"` / `"append"` SHALL 归一为追加（仍与覆盖写不同）。`code_run` 与
  `web_fetch` SHALL 保持**精确参数**匹配（不做 shell / URL 语义归一）。
- 单调用、文本回复与非流式 planner 路径的事件序、观测与结果 SHALL 逐字不变。

#### Scenario: 批量调用全部执行
- **GIVEN** 一次推理返回按序排列的两个原生工具调用
- **WHEN** 循环执行该次推理
- **THEN** 两个工具各被执行一次，各产出一组动作事件与观测，轮次推进 2

#### Scenario: 组内只读动作并发执行
- **GIVEN** 一次推理返回两个相互独立的只读工具调用（处理器耗时均为 T）
- **WHEN** 循环执行该批次
- **THEN** 两个处理器**同时**在执行（总耗时显著小于 2T），且各产出一组动作事件与观测

#### Scenario: 写动作作为屏障
- **GIVEN** 一个批次依次包含只读动作与写动作
- **WHEN** 循环执行该批次
- **THEN** 写动作在只读动作完成**之后**才开始执行；写动作不与其他动作并发

#### Scenario: 委托动作作为屏障
- **GIVEN** 同一批次包含两个 coeffect 为 `agent:delegate` 的委托动作（子 Agent 可写文件）
- **WHEN** 循环执行该批次
- **THEN** 两个委托动作**串行**执行、互不重叠；它们作为并发批次之间的屏障

#### Scenario: 并发结果按原序提交
- **GIVEN** 并发段内两个只读动作，后一个先完成
- **WHEN** 循环提交结果
- **THEN** `action_started` / `action_completed` / 观测回灌仍按 provider `index` 顺序

#### Scenario: 关闭并发开关
- **GIVEN** 构造循环时 `concurrent_reads=False`
- **WHEN** 执行含多个只读动作的批次
- **THEN** 动作逐个串行执行，事件序与观测与变更前逐字一致

#### Scenario: 批内重复只执行一次
- **GIVEN** 同一批次内两个完全相同的工具调用
- **WHEN** 循环执行该批次
- **THEN** 工具处理器只被调用一次，另一次记 `action_deduplicated`（`scope="batch"`）

#### Scenario: 紧邻重复写复用结果
- **GIVEN** 同一轮内连续两次完全相同的 `file_write`（覆盖模式）且第一次成功
- **WHEN** 第二次动作执行
- **THEN** 不再写盘，返回第一次的结果并记 `action_deduplicated`（`scope="turn"`）

#### Scenario: 文件写参数规范化去重
- **GIVEN** 同一轮内连续两次 `file_write`：路径分别为 `~/x.txt` 与绝对路径 `$HOME/x.txt`，
  或正文仅 CRLF / LF 不同，或一次省略 `mode` 另一次显式 `"w"`
- **WHEN** 第二次动作执行
- **THEN** 判为重复（`action_deduplicated`，`scope="turn"`），不重复写盘；
  追加模式（`a` / `append`）与覆盖写 SHALL NOT 被合并

#### Scenario: 解析失败不部分执行
- **GIVEN** 一次推理的两个原生调用中有一个参数 JSON 非法
- **WHEN** 循环处理该批次
- **THEN** 本轮以 `LLM_PLAN_PARSE_FAILED` 终止失败收尾，两个调用**均未执行**
