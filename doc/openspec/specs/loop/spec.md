# Loop Specification

## Purpose
核心执行循环是 CORE-Harness 的引擎主轴，负责"观察→推理→行动→记忆"的稳态循环，所有横切能力（权限、约束、遥测、上下文）在此主轴上插入。执行入口同步（run）与异步（arun / astream）同构：异步为主、同步为薄壳，astream 以 AsyncIterator[LoopEvent] 流式产出执行生命周期事件。

## Requirements

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

### Requirement: 横切中间件插入
系统 SHALL 支持在循环关键节点插入横切中间件（权限、约束、遥测、上下文）。中间件分两类接缝：
① **动作前链**（`middlewares`）：每个动作执行前按注册序调用，接收（`LoopContext`, `Action`），
可改写动作或返回 `None`；任一返回 `None` 即短路（动作不执行，本轮以已拒绝回复终止）。
② **结果侧观察者链**（`action_observers`）：每个**非终止**动作完成后按注册序回调，接收
（`LoopContext`, `Action`, `ActionResult`）；**仅通知** —— 观察者抛错降级为遥测、
**不改变本轮的结局与终止语义**；终止动作（空 `tool_id`）不触发观察者。

#### Scenario: 中间件按序执行
- **GIVEN** 已注册一组横切中间件
- **WHEN** loop 执行到对应节点
- **THEN** 中间件按注册顺序执行，任一拒绝即短路

#### Scenario: 中间件拒绝短路
- **GIVEN** 权限中间件拦截了当前动作
- **WHEN** loop 尝试执行该动作
- **THEN** 动作不执行，loop 转入等待审批/修正分支

#### Scenario: 结果侧观察者按序执行
- **GIVEN** 已注册一组结果侧观察者，且一轮推理产出一个非终止动作
- **WHEN** 该动作执行完成后
- **THEN** 观察者按注册顺序各被调用一次，收到（上下文、动作、执行结果）

#### Scenario: 观察者异常降级不中断本轮
- **GIVEN** 已注册的结果侧观察者执行时抛错
- **WHEN** 该动作执行完成后
- **THEN** 该错误被降级留痕，本轮正常推进（回复与终止语义不变）

#### Scenario: 终止动作不触发结果侧观察者
- **GIVEN** 一轮推理产出终止动作（空 `tool_id`，如本轮回复）
- **WHEN** 该动作「执行」完成后
- **THEN** 结果侧观察者不被调用

### Requirement: 错误与预算控制
系统 SHALL 限制单任务最大循环次数与 token 预算，超出即终止或转人工。两项上限 SHALL 可经配置链
（CLI flag > env > config.yaml > 默认值）设定并经 ConfigSpec 单一真源声明：`loop.max_rounds`
（默认 `10`）与 `loop.output_reserve`（输出预留，默认 `8192`）。token 预算 SHALL 由模型上下文窗口
**派生** —— `llm.context_window` 大于 `0` 时 `token_budget = llm.context_window - loop.output_reserve`；
未配置（`0`）时回落内置缺省 `65536`。非法取值（非整数、`loop.max_rounds` < 1、
`loop.output_reserve` < 0、或 `llm.context_window` 不大于 `loop.output_reserve`）SHALL 在校验期拒绝并
阻断启动，SHALL NOT 静默兜底为缺省或非正预算（`token_budget` ≤ 0 的语义是**关闭** token 维度，
静默兜底会把配置错误变成「预算维度失效」）。

本轮记账值 `token_used` 的**口径** SHALL 覆盖**装配进本轮提示词的全部内容** —— 本轮消息（含动作与
观察回灌）＋ 回灌历史 ＋ planner 装配的**系统提示与工具 schema**；SHALL NOT 只计其中一部分
（只计「本轮输入 + 历史 + 每步工具输出」不足以界定提示词大小）。记账值 SHALL 以**最近一次模型调用
实测的提示 token 数**（provider 报告的 `usage.prompt_tokens`）为**下界**：该实测值可用时记账值
SHALL NOT 低于它；不可用（如流式响应不携带用量、或 planner 未暴露观测）时 SHALL 退化为**按装配
全量估算**。该口径 SHALL NOT 改变阈值语义（预算终止与压实同取 `token_budget`）、SHALL NOT 改变
窗口派生规则、SHALL NOT 引入任何第三方 tokenizer 依赖。

#### Scenario: 循环次数超限
- **GIVEN** 循环次数达到上限
- **WHEN** loop 尝试继续
- **THEN** 终止并返回 `LOOP_LIMIT_EXCEEDED`，写遥测

#### Scenario: token 预算超限
- **GIVEN** 累计 token 消耗超过预算
- **WHEN** 下一轮推理前
- **THEN** 触发上下文压实或转人工，不无限烧 token

#### Scenario: 循环次数上限可配
- **GIVEN** 配置链将 `loop.max_rounds` 设为 3（CLI flag / env / config.yaml 任一面）
- **WHEN** 非终止动作连续执行至第 3 轮
- **THEN** loop 终止并返回 `LOOP_LIMIT_EXCEEDED`

#### Scenario: 预算由上下文窗口派生
- **GIVEN** `llm.context_window` = 131072 且 `loop.output_reserve` 取缺省 8192
- **WHEN** 组合根装配执行循环
- **THEN** token 预算取 `131072 - 8192 = 122880`，压实触发阈值与硬停阈值同取该值

#### Scenario: 未配置窗口回落内置缺省
- **GIVEN** `llm.context_window` 未配置（0）或为 0
- **WHEN** 组合根装配执行循环
- **THEN** token 预算取内置缺省 `65536`，其余行为与变更前一致

#### Scenario: 窗口不敷输出预留被拒
- **GIVEN** `llm.context_window` = 4096 且 `loop.output_reserve` = 8192（派生结果非正）
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明上下文窗口不敷输出预留

#### Scenario: 记账计入系统提示与工具 schema
- **GIVEN** planner 装配出的提示词含非空系统提示（宪法规则 / 常驻笔记 / 相关事实 / 技能 / 工具 schema）
- **WHEN** 一轮工具步执行完毕
- **THEN** 本轮记账值**包含**系统提示与工具 schema 的占用（不再只计本轮消息与回灌历史），使预算终止
  与压实**看得见**固定前缀

#### Scenario: provider 实报为记账下界
- **GIVEN** 某次模型调用返回 provider 报告的提示 token 数（`usage.prompt_tokens`）
- **WHEN** 该步执行完毕后判定预算
- **THEN** 记账值**不低于**该实测值（估算偏低时以实测值抬升），预算终止与压实据此判定

### Requirement: 异步流式执行
系统 SHALL 提供异步执行入口 arun 与流式入口 astream，与同步 run 共用同一执行循环语义；astream 返回 AsyncIterator[LoopEvent]，以 loop_started / action_started / action_completed / step_completed / reply_delta / loop_finished / loop_failed 七类事件流式产出执行生命周期，支持事件循环内非阻塞调用与流式编排；run 保留为薄壳（thin wrapper），内部经事件循环桥接调用对应异步实现，调用方无需感知事件循环、零改动。工具动作事件仅对非终止动作（tool_id 非空）产出：action_started 于工具执行前携带 round/tool_id/args 节选，action_completed 于执行后携带 round/tool_id/ok/duration_ms/output 节选；节选有界（≤400 字符），既有五类事件的节奏与语义不变。除上述**事件流**外，循环 SHALL 在**非终止动作**完成后**另行产出工具调用遥测**（`kind="tool_call"`，载荷含工具 id / 参数 / 成败与耗时，且**有界**），使「按工具 id 归因」的证据在**生产**链路可得（见 evolution「经验采集」①工具调用类）；该产出 SHALL NOT 改变上述 `LoopEvent` 的外发路径、事件序与既有消费语义，未注入 tracer 时 SHALL 不产出（行为与既有缺省一致）。
planner 流式协议 SHALL **额外**支持**思考增量通道**：以独立的 `Thinking(delta)` item 承载推理原文增量，与既有 `str`（回复增量）与 `Action`（终态动作）**并存**，SHALL NOT 改变既有两类 item 的语义与外发路径。循环 SHALL 在**思考回显开启**时把该 item 转为 `loop.reasoning` 事件（载荷 `{"text": <增量>}`，与 `reply_delta` 的 `{"text": …}` 同形、**类型相异**），**未开启**时 SHALL NOT 产出该事件（事件面与既有缺省逐字一致）；非流式路径（`__call__` 与无 `astream` 的降级分支）SHALL **同样支持终态思考**（一次性全文外发）。
`loop.reasoning` SHALL ONLY 用于**呈现**：SHALL NOT 写入**转录**、SHALL NOT 写入**记忆**、SHALL NOT 写入**日志**、SHALL NOT 进入 **trace 遥测**（与 `reply_delta` 同为「未定稿原文」，守「思考回显是纯呈现层」边界）；SHALL NOT 经编排层**子任务运行态回流**外发（思考原文不上子任务回流通道）。

#### Scenario: 异步执行入口
- **GIVEN** 内核运行于事件循环中，需并发驱动多个执行循环
- **WHEN** 经 arun 发起执行
- **THEN** 调用不阻塞事件循环，返回 awaitable，多个执行循环可并发运行

#### Scenario: 流式事件产出
- **GIVEN** 一个执行循环按"观察→推理→行动→记忆"逐轮推进
- **WHEN** 经 astream 发起流式执行
- **THEN** 返回 AsyncIterator[LoopEvent]，按生命周期顺序产出 loop_started、每轮 step_completed、逐 token reply_delta、终态 loop_finished 或 loop_failed

#### Scenario: 工具动作事件
- **GIVEN** 一轮推理产出非终止动作（tool_id 非空）
- **WHEN** 该动作经 act 执行
- **THEN** 执行前产出 action_started（round/tool_id/args 节选）、执行后产出 action_completed（round/tool_id/ok/duration_ms/output 节选），两者先于该轮 step_completed

#### Scenario: 终止动作不产出动作事件
- **GIVEN** 一轮推理产出终止动作（tool_id 为空，本轮进入回复收尾）
- **WHEN** 该动作经 act 执行
- **THEN** 不产出 action_started / action_completed（终止动作非工具调用）

#### Scenario: 同步薄壳等价
- **GIVEN** 调用方处于同步上下文
- **WHEN** 调用 run 同步入口
- **THEN** 语义与 arun 一致，内部经事件循环桥接（asyncio.run）完成调用，调用方无需改动、无需感知事件循环

#### Scenario: 工具动作产出工具调用遥测
- **GIVEN** 已注入 `tracer`，且一轮推理产出一个非终止动作
- **WHEN** 该动作经 act 执行完成
- **THEN** trace 流新增一条 `kind="tool_call"` 事件（含工具 id / 成败 / 耗时，载荷**有界**），并可由本轮的 trace 完成回调回放——按工具 id 归因的证据链在生产可得

#### Scenario: 终止动作不产出工具调用遥测
- **GIVEN** 一轮推理产出终止动作（tool_id 为空，本轮进入回复收尾）
- **WHEN** 该动作经 act「执行」完成
- **THEN** 不产出 `kind="tool_call"` 遥测（终止动作非工具调用，与 `action_completed` 同判据）

#### Scenario: 未注入 tracer 不产出工具调用遥测
- **GIVEN** 未注入 `tracer` 的一次执行
- **WHEN** 非终止动作经 act 执行完成
- **THEN** 不产出工具调用遥测，本轮回复、事件序与终止语义均与既有缺省一致

#### Scenario: 思考回显开启时逐段产出 loop.reasoning
- **GIVEN** 思考回显**已开启**，且本轮推理的模型响应携思考原文
- **WHEN** 经 astream 发起流式执行
- **THEN** 按模型返回次序逐段产出 `loop.reasoning`（载荷 `{"text": <该段思考>}`），且**先于/夹于** `reply_delta` 之间、SHALL NOT 与 `reply_delta` 共用一个类型；本轮回复正文、事件序与终态语义不受影响

#### Scenario: 思考回显关闭时事件面零新增
- **GIVEN** 思考回显**未开启**（缺省），且本轮推理的模型响应携思考原文
- **WHEN** 经 astream 发起流式执行
- **THEN** **不产出**任何 `loop.reasoning`，事件面与既有缺省**逐字一致**（含终态全文补发判据不被思考事件干扰）

#### Scenario: 非流式路径支持终态思考
- **GIVEN** 思考回显已开启，且 provider 不支持流式（无 `astream`）—— planner 走降级分支
- **WHEN** 该轮推理完成
- **THEN** 该次响应的思考原文以**一次性全文**经 `loop.reasoning` 外发（先于终态动作），回复正文与终态语义与既有实现一致

#### Scenario: 思考原文不进持久面与子任务回流
- **GIVEN** 思考回显已开启且本轮产出 `loop.reasoning`
- **WHEN** 本轮结束
- **THEN** 会话转录、记忆沉淀、日志与 trace 遥测均**不含**思考原文；该事件亦**不**经编排层子任务运行态回流外发（回流白名单不含该类型）
