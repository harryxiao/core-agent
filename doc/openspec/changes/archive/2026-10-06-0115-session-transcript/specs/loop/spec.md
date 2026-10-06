# Loop Specification Delta

## MODIFIED Requirements

### Requirement: 执行循环
系统 SHALL 以固定节律运行"观察→推理→行动→记忆"循环，直到目标达成或达到停止条件。三个执行入口（`run`/`arun`/`astream`）SHALL 接受可选的会话标识 `session_id`（缺省空串，表示未归属会话），并在「记忆」步把该标识写入本轮沉淀 L2 条目的 `session_id`；标识随调用传递、**不驻留循环实例**（同一实例可并发服务多个会话，互不串号）。该标识 SHALL **经上下文包传递至推理（上下文装配）与技能路由阶段**，作为记忆检索与路由未命中记录归属的**会话维度**，SHALL NOT 只用于记忆写入；标识为空串时，各阶段的检索与归属语义 SHALL 与既往**逐字一致**。循环 SHALL 在本轮开始时把**该会话的最近历史对话**载入上下文包的 `history` 字段（标识为空串时不载入），供推理期按「系统提示 → 历史 → 本轮消息」的次序组装请求；载入历史 SHALL 受**双重上界**约束——最近 `loop.history_turns` 轮与**独立 token 切片**，且其 token SHALL 计入本轮预算记账（否则预算终止与压实触发看不见它）。循环 SHALL 在收尾时把本轮「用户原话 + 最终回复」追加至该会话转录（标识为空串时 SHALL NOT 追加；本轮以**合成**终止原因结束——如预算耗尽——时，SHALL NOT 把合成文案当作模型回复追加）。循环收尾（「记忆」步之后）SHALL 检查**维护节拍**：距上次维护达 `maintenance_interval`（可配置，`<=0` 表示关闭）时执行一次维护；维护含①记忆维护（遗忘）与②冷路径节拍（注入的冷路径回调，缺省未注入则不做，见 evolution「冷路径驱动」），二者**各自失败降级、不中断本轮**；节拍不改变终止条件与回复内容。循环收尾 SHALL **在本轮全部遥测事件记录完毕之后**、按**轮**调用可选的 **trace 完成回调**（注入的 `trace_observer`，接收本轮 `trace_id`；缺省未注入则不做），其语义为「登记一条已完成的 trace」，SHALL **不受维护节拍节流**（每轮一次）、SHALL NOT 阻塞或改变本轮回复与终止语义，抛错时 SHALL 降级留痕、不中断本轮。循环 SHALL 经注入的 `tracer` 驱动 trace 生命周期：**开轮**调 `start_trace` 取回贯穿全链路的 `trace_id`（缺省未注入 tracer 时回退为本地生成 id，行为与其一致）；**收尾**在调用 trace 完成回调**之后**调 `end_trace(trace_id)` **封口**本轮 trace（交付导出器 + 释放内存；缺省未注入 tracer 则不做）。收尾顺序 SHALL 为「记录本轮全部遥测 → trace 完成回调 → `end_trace` 封口」，SHALL NOT 在回调之前封口（回调须能**完整回放**本轮事件）。循环自身失败时，其 `loop_finished` 遥测事件 SHALL 携带模块归因 `module_id="loop.default"`（正常收尾时该字段缺省为空）。

#### Scenario: 单轮循环闭环
- **GIVEN** 一个待执行任务
- **WHEN** loop 引擎运行一轮
- **THEN** 完成观察、推理、行动、记忆四步，且每步产出被遥测记录

#### Scenario: 记忆沉淀携带会话标识
- **GIVEN** 一次带会话标识的执行（`session_id` 非空）
- **WHEN** 循环完成「记忆」步的本轮沉淀
- **THEN** 沉淀的 L2 条目 `session_id` 等于该标识

#### Scenario: 会话标识参与推理期检索
- **GIVEN** 一次带会话标识的执行，且记忆库中含他会话沉淀的事实
- **WHEN** 循环进入「推理」步（上下文装配）
- **THEN** 本轮事实检索以该会话标识为会话维度，他会话事实**不进入**本轮推理上下文

#### Scenario: 会话历史回灌进推理请求

- **GIVEN** 某会话已有若干轮历史，且 `loop.history_turns` 大于 `0`
- **WHEN** 该会话发起新一轮
- **THEN** 本轮请求按「系统提示 → 历史 → 本轮消息」组装，历史以「用户原话 / 最终回复」成对回灌

#### Scenario: 历史受双重上界约束

- **GIVEN** 某会话的历史轮数超过 `loop.history_turns`，或其历史 token 超过独立切片
- **WHEN** 该会话发起新一轮
- **THEN** 只载入最近的、且在两个上界之内的历史，其 token 计入本轮预算记账

#### Scenario: 本轮对话追加至转录

- **GIVEN** 一次带会话标识的成功执行
- **WHEN** 循环收尾
- **THEN** 该会话转录新增本轮「用户原话 + 最终回复」两条

#### Scenario: 合成终止不写入转录

- **GIVEN** 一次带会话标识的执行因预算耗尽而终止（回复为合成文案）
- **WHEN** 循环收尾
- **THEN** 该合成文案 SHALL NOT 作为模型回复写入转录

#### Scenario: 未指定会话标识时不落盘不回灌

- **GIVEN** 一次未指定会话标识（`session_id` 为空串）的执行
- **WHEN** 循环开始与收尾
- **THEN** 既不载入历史也不追加转录，语义与既往逐字一致

#### Scenario: 未指定会话标识时归缺省分组
- **GIVEN** 一次未指定会话标识的执行
- **WHEN** 循环完成「记忆」步的本轮沉淀
- **THEN** 沉淀条目的 `session_id` 为缺省空串，与既有未归属语义一致

#### Scenario: 维护节拍触发遗忘
- **GIVEN** 一次执行收尾时距上次记忆维护已达 `maintenance_interval`
- **WHEN** 循环执行收尾维护节拍
- **THEN** 触发一次记忆遗忘（归档低价值 L2 episodic），本轮回复与终止语义不变

#### Scenario: 维护节拍触发冷路径
- **GIVEN** 一次执行收尾时距上次维护已达 `maintenance_interval`，且已注入冷路径回调
- **WHEN** 循环执行收尾维护节拍
- **THEN** 该回调被调用一次（是否真正运行进化 cycle 由其自身触发门决定），本轮回复与终止语义不变

#### Scenario: 冷路径失败不中断本轮
- **GIVEN** 已注入的冷路径回调执行时抛错
- **WHEN** 循环执行收尾维护节拍
- **THEN** 该错误被降级留痕，本轮正常收尾（回复与终止语义不变）

#### Scenario: 未达间隔不重复维护
- **GIVEN** 距上次记忆维护尚未达 `maintenance_interval`（或间隔配置为 `<=0`）
- **WHEN** 循环执行收尾维护节拍
- **THEN** 不触发维护（不产生额外存储扫描）

#### Scenario: 工具观察回灌
- **GIVEN** 一轮推理产出工具调用且已执行（无论成败）
- **WHEN** 进入下一轮推理
- **THEN** 上下文消息包含该工具调用与执行结果（assistant + tool 消息），模型可据此推进至终态

#### Scenario: 停止条件触发
- **GIVEN** 任务达到停止条件（目标达成/预算耗尽/审批拒绝）
- **WHEN** loop 检查停止条件
- **THEN** 循环退出并返回最终状态

#### Scenario: 单轮回滚
- **GIVEN** 行动阶段某 action 执行异常
- **WHEN** 该轮需要回滚
- **THEN** 按可逆追踪记录逆序撤销该轮已产生的副作用，回到该轮开始前状态并写遥测

#### Scenario: 不可逆动作人工审批
- **GIVEN** 一轮推理产出不可逆动作且确认门判定需确认
- **WHEN** loop 已注入审批通道
- **THEN** 经通道请求人工批准：批准则放行执行且本轮不再重复询问；拒绝或无通道则动作不执行、本轮以已拒绝回复终止（fail-closed）

#### Scenario: trace 完成回调按轮提交
- **GIVEN** 已注入 trace 完成回调的一次执行
- **WHEN** 循环收尾
- **THEN** 该回调被调用一次并收到本轮的 `trace_id`

#### Scenario: trace 完成回调在本轮遥测齐全之后
- **GIVEN** 已注入 trace 完成回调
- **WHEN** 回调被调用时回放本轮 trace
- **THEN** 本轮全部遥测事件（含 `loop_finished`）均已记录，回调可完整回放

#### Scenario: trace 完成回调不受维护节拍节流
- **GIVEN** 距上次维护尚未达 `maintenance_interval`，且已注入 trace 完成回调
- **WHEN** 循环收尾
- **THEN** 该回调仍被调用一次（其节律按轮、与维护节拍无关）

#### Scenario: trace 完成回调失败不中断本轮
- **GIVEN** 已注入的 trace 完成回调执行时抛错
- **WHEN** 循环收尾
- **THEN** 该错误被降级留痕（`trace_observer_failed`），本轮正常收尾（回复与终止语义不变）

#### Scenario: 收尾封口在本轮 trace 完成回调之后
- **GIVEN** 已注入 tracer 与 trace 完成回调的一次执行
- **WHEN** 循环收尾
- **THEN** `end_trace` 在回调**之后**调用：回调被调用时本轮事件**尚可完整回放**，封口后本轮 trace **不再驻留内存**

#### Scenario: 封口交付导出器
- **GIVEN** 已注入一个装配了导出器的 tracer
- **WHEN** 循环收尾封口本轮 trace
- **THEN** 本轮遥测事件经导出器产出（落盘真路径打通）

#### Scenario: 未注入 tracer 收尾仍正常
- **GIVEN** 未注入 tracer 的一次执行
- **WHEN** 循环收尾
- **THEN** 不调用 `start_trace`/`end_trace`，本轮回复与终止语义不变（行为与既有缺省一致）

#### Scenario: 循环自身失败带模块归因
- **GIVEN** 一轮执行因达到停止条件（轮数上限 / token 预算耗尽）失败收尾
- **WHEN** 记录本轮 `loop_finished` 遥测事件
- **THEN** 该事件携带 `module_id="loop.default"`，供进化引擎把缺陷归因到该模块

#### Scenario: 正常收尾不带模块归因
- **GIVEN** 一轮执行正常达成收尾
- **WHEN** 记录本轮 `loop_finished` 遥测事件
- **THEN** 该事件 `module_id` 缺省为空（不产生虚假缺陷证据）
