# Loop Specification

## Purpose
核心执行循环是 CORE-Harness 的引擎主轴，负责"观察→推理→行动→记忆"的稳态循环，所有横切能力（权限、约束、遥测、上下文）在此主轴上插入。执行入口同步（run）与异步（arun / astream）同构：异步为主、同步为薄壳，astream 以 AsyncIterator[LoopEvent] 流式产出执行生命周期事件。

## Requirements

### Requirement: 执行循环
系统 SHALL 以固定节律运行"观察→推理→行动→记忆"循环，直到目标达成或达到停止条件。三个执行入口（`run`/`arun`/`astream`）SHALL 接受可选的会话标识 `session_id`（缺省空串，表示未归属会话），并在「记忆」步把该标识写入本轮沉淀 L2 条目的 `session_id`；标识随调用传递、**不驻留循环实例**（同一实例可并发服务多个会话，互不串号）。该标识 SHALL **经上下文包传递至推理（上下文装配）与技能路由阶段**，作为记忆检索与路由未命中记录归属的**会话维度**，SHALL NOT 只用于记忆写入；标识为空串时，各阶段的检索与归属语义 SHALL 与既往**逐字一致**。循环 SHALL 在「记忆」步把本轮的**行动与结果**序列（工具调用及其结果的**有界**渲染）沉淀为**另一条** L2 条目 —— 与轨迹条目**并存**，轨迹条目的内容口径 SHALL **除密钥形态脱敏外**逐字不变（写入前 SHALL 对整条内容执行与行动序列同源的 `redact_secrets`；未命中密钥形态时逐字不变）；轨迹条目承载「轮次/成败 + 语义正文」，行动序列条目承载「做了什么、得到什么」，二者共为压实的**抽取材料**。行动序列条目 SHALL **有界**（逐行截断 + 整体上界，不随轮次无限增长），且 SHALL 在写入前对每一行做**密钥形态脱敏**（判据与记忆侧关键事实抽取**同源**、方向 over-redact）—— 密钥只引用不读取、绝不进记忆。本轮**无工具调用**时 SHALL NOT 沉淀该条目（无行动不记忆）。循环 SHALL 在本轮开始时把**该会话的最近历史对话**载入上下文包的 `history` 字段（标识为空串时不载入），供推理期按「系统提示 → 历史 → 本轮消息」的次序组装请求；载入历史 SHALL 以**三层滑窗**组织：**短层**为最近若干轮**原文**，**中层**为紧邻短层之前若干轮的**中期模型摘要**，**长层**为该会话的**整体摘要**；三层 SHALL 由同一历史预算按份额切分（短 0.5 / 中 0.3 / 长 0.2，由确定性纯函数按 `loop.history_turns` 与历史预算算出、不含模型调用），且 `loop.history_turns` SHALL 为三层**轮数总量**（非仅短层）。两层摘要 SHALL 作为**独立系统块**注入（长层先于中层），SHALL NOT 折入 `history` 或本轮消息；两层摘要与前文历史的 token SHALL 一并计入本轮预算记账（否则预算终止与压实触发看不见它）。该会话**尚无任何摘要**时（冷会话）SHALL 退化为**仅短层原文回灌**，其轮数与 token 上界 SHALL 与既往「双重上界」**逐字一致**。两层摘要的注入 SHALL 与**历史回放开关解耦** —— `loop.history_turns` 为 `0`（关闭历史回放）时 SHALL NOT 连坐关闭摘要注入：该会话已有的两层摘要 SHALL **照常作为独立系统块注入**，而历史带为空（SHALL NOT 回灌任何历史原文）；`loop.history_turns` 大于 `0` 时行为 SHALL 与既往**逐字一致**。循环 SHALL 在收尾时把本轮「用户原话 + 最终回复」追加至该会话转录（标识为空串时 SHALL NOT 追加；本轮以**合成**终止原因结束——如预算耗尽——时，SHALL NOT 把合成文案当作模型回复追加）。循环收尾（「记忆」步之后）SHALL 检查**维护节拍**：距上次维护达 `maintenance_interval`（可配置，`<=0` 表示关闭）时执行一次维护；维护含①**会话级记忆维护**（按本轮会话标识触发一次记忆压实，产该会话整体摘要）②**中期摘要物化**（取该会话转录「中带」轮次经记忆压实通道滚合并为中层摘要，中带为空则不调用）③记忆遗忘与④冷路径节拍（注入的冷路径回调，缺省未注入则不做，见 evolution「冷路径驱动」），四者**各自失败降级、不中断本轮**；①② SHALL 仅在本轮会话标识非空时执行；节拍不改变终止条件与回复内容。

轮内上下文压实的**记忆固化步骤**（`memory.compact`）SHALL 亦按**本轮会话标识**收窄聚合范围（与会话级维护节拍①**同口径**）—— 仅聚合**该会话**的 L2 episodic 条目，SHALL NOT 顺手提炼他会话条目；本轮会话标识为空串时 SHALL 保持**全量**聚合（与既有语义逐字一致）。循环收尾 SHALL **在本轮全部遥测事件记录完毕之后**、按**轮**调用可选的 **trace 完成回调**（注入的 `trace_observer`，接收本轮 `trace_id`；缺省未注入则不做），其语义为「登记一条已完成的 trace」，SHALL **不受维护节拍节流**（每轮一次）、SHALL NOT 阻塞或改变本轮回复与终止语义，抛错时 SHALL 降级留痕、不中断本轮。循环 SHALL 经注入的 `tracer` 驱动 trace 生命周期：**开轮**调 `start_trace` 取回贯穿全链路的 `trace_id`（缺省未注入 tracer 时回退为本地生成 id，行为与其一致）；**收尾**在调用 trace 完成回调**之后**调 `end_trace(trace_id)` **封口**本轮 trace（交付导出器 + 释放内存；缺省未注入 tracer 则不做）。收尾顺序 SHALL 为「记录本轮全部遥测 → trace 完成回调 → `end_trace` 封口」，SHALL NOT 在回调之前封口（回调须能**完整回放**本轮事件）。循环自身失败时，其 `loop_finished` 遥测事件 SHALL 携带模块归因 `module_id="loop.default"`（正常收尾时该字段缺省为空）。

本轮**失败**（终止动作失败、预算/轮次终止、或不可解析输出）时，循环 SHALL 在「记忆」步**再另立一条**
L2 条目 `loop.failure.<trace_id>`（`tags=["loop","failure"]`、`kind="episodic"`、与轨迹条目及行动序列条目
**并存**、**同 trace / 同 session**），承载「任务文本 + 失败原因 + 失败轮次与失败动作序列」；该条目 SHALL
**有界**（逐行截断 + 整体不超过既有单条 L2 沉淀条目长度上界），且 SHALL 在写入前对**每一行**做**密钥形态
脱敏**（判据与行动序列条目**同源**、方向 over-redact）。本轮**未失败**时 SHALL NOT 写该条目（行为与既往
**逐字一致**）。循环 SHALL 在本轮开始时把**该会话的既往失败教训**载入上下文包的 `failure_lessons` 字段 —— 仅当注入了**教训取用钩子**（组合根闭包，入参为本轮会话标识；缺省未注入 ⇒ 该字段恒为空 ⇒ 提示词**逐字不变**）；推理规划器 SHALL 把非空该字段以**独立系统块**（「既往失败教训：」）注入，SHALL NOT 折入「相关事实」或历史消息。钩子抛错 SHALL 降级留痕、置空该字段，**不改变本轮结局**。

教训块 SHALL **有界**：最多 `5` 条、单条折叠为一行后不超过 `500` 字符、整块正文不超过
`1500` 字符（超出部分截断）—— SHALL NOT 以若干条长教训挤占事实 / 历史预算。

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

#### Scenario: 行动与结果另立一条 L2 条目
- **GIVEN** 一轮执行中产生了若干工具调用及其执行结果
- **WHEN** 循环完成「记忆」步的本轮沉淀
- **THEN** 除本轮轨迹条目外**另**沉淀一条 L2 条目，其内容含本轮的工具调用与结果序列（有界渲染）；
  **AND** 轨迹条目的内容**除密钥形态脱敏外逐字不变**（未命中密钥形态时与变更前逐字相同）

#### Scenario: 轨迹条目写入前脱敏
- **GIVEN** 本轮终态回复含密钥形态子串
- **WHEN** 收尾把轨迹条目写入 L2
- **THEN** 落库内容中该子串已替换为 `<redacted>`，且条目的轮次/成败结构与其余正文保持不变

#### Scenario: 行动序列条目脱敏且有界
- **GIVEN** 一轮执行中某工具的参数或结果含**明文密钥形态**字符串，且行动序列很长
- **WHEN** 循环完成「记忆」步的本轮沉淀
- **THEN** 行动序列条目**不含**该明文（脱敏为 `<redacted>`），且其长度/条数受**上界**约束

#### Scenario: 无工具调用不另立条目
- **GIVEN** 一轮执行仅有纯文字回复（未产生任何工具调用）
- **WHEN** 循环完成「记忆」步的本轮沉淀
- **THEN** 只沉淀轨迹条目，**不**沉淀行动序列条目

#### Scenario: 三层滑窗按比例分配

- **GIVEN** 某会话已有若干轮历史且 `loop.history_turns` 大于 `0`
- **WHEN** 该会话发起新一轮
- **THEN** 历史按三层组织：短层取最近按比例算出的若干轮**原文**，中层为其前若干轮的中期摘要，
  长层为该会话整体摘要；短层轮数**不**超过 `loop.history_turns`，且短层与中层的轮数之和**不**超过它

#### Scenario: 分层摘要作为独立系统块注入

- **GIVEN** 某会话已有长期摘要与（或）中期摘要
- **WHEN** 该会话发起新一轮
- **THEN** 两层摘要各自作为**独立系统块**注入，长层在中层之前；两摘要 SHALL NOT 折入 `history`
  或本轮消息；两层摘要的 token 计入本轮预算记账

#### Scenario: 冷会话退化为纯回灌

- **GIVEN** 某会话尚无任何摘要（冷会话）且 `loop.history_turns` 大于 `0`
- **WHEN** 该会话发起新一轮
- **THEN** 不注入任何摘要块，只回灌最近 `loop.history_turns` 轮原文（受独立 token 切片约束），
  请求与既往「双重上界」行为**逐字一致**

#### Scenario: 分层后短层收窄且更旧轮不再回灌原文

- **GIVEN** 某会话既有摘要，且其历史轮数超过按比例算出的短层轮数
- **WHEN** 该会话发起新一轮
- **THEN** 只回灌短层范围内的原文，更旧的轮次**不**以原文回灌（其内容由中层 / 长层摘要承接）

#### Scenario: 维护节拍产出会话摘要与中期摘要

- **GIVEN** 一次带会话标识的执行收尾时距上次维护已达 `maintenance_interval`，且记忆存储注入了摘要器
- **WHEN** 循环执行收尾维护节拍
- **THEN** 触发一次会话级记忆压实（产出该会话整体摘要，即长层）与一次中期摘要物化（产出中层摘要），
  本轮回复与终止语义不变

#### Scenario: 摘要读取失败降级

- **GIVEN** 某会话既有摘要，但读取摘要时发生异常
- **WHEN** 该会话发起新一轮
- **THEN** 摘要读取失败被**降级**（本轮不注入摘要、不中断本轮），且不阻断历史原文回灌

#### Scenario: 维护节拍会话级两步失败不中断本轮

- **GIVEN** 会话级记忆压实或中期摘要物化执行时抛错
- **WHEN** 循环执行收尾维护节拍
- **THEN** 该错误被降级留痕，其余维护步（遗忘 / 冷路径）照常尝试，本轮正常收尾

#### Scenario: 失败轮另立一条 L2 条目

- **GIVEN** 一轮以**失败**收尾（终止动作失败 / 预算或轮次终止 / 不可解析输出），且循环注入了记忆存储
- **WHEN** 该轮进入「记忆」步
- **THEN** 除轨迹条目与行动序列条目外，**另立**一条 L2 条目 `loop.failure.<trace_id>`：
  `tags` 含 `loop` 与 `failure`、`kind` 为 `episodic`、`source` / `trace_id` / `session_id` 与同轮轨迹条目一致，
  内容含任务文本、失败原因与失败轮次（或失败动作）行；该条目**并存**，不改动轨迹条目与行动序列条目

#### Scenario: 成功轮不写失败条目

- **GIVEN** 一轮以**成功**收尾
- **WHEN** 该轮进入「记忆」步
- **THEN** **不写**任何 `loop.failure.*` 条目；轨迹条目与行动序列条目的内容与层级**逐字不变**

#### Scenario: 失败条目脱敏且有界

- **GIVEN** 失败原因或失败动作渲染中含**明文密钥形态**字符串且整体超长
- **WHEN** 失败条目落库
- **THEN** 落库内容**不含**该明文（逐行脱敏为 `<redacted>`）且长度不超过既有单条 L2 沉淀条目长度上界

#### Scenario: 轮内压实按会话收窄聚合
- **GIVEN** 会话 A 与会话 B 各有 L2 episodic 条目，且会话 A 的一轮触发轮内上下文压实
- **WHEN** 该轮的记忆固化步骤执行
- **THEN** 仅会话 A 的条目被聚合提炼（会话 B 的条目层级与内容不变），压实产物归会话 A

#### Scenario: 关闭历史回放仍注入摘要

- **GIVEN** 某会话已有摘要，且 `loop.history_turns` 为 `0`（关闭历史原文回放）
- **WHEN** 该会话发起新一轮
- **THEN** 历史带为空（不注入任何历史原文），但该会话已有的两层摘要仍作为独立系统块注入

#### Scenario: 既往失败教训作为独立块注入

- **GIVEN** 某会话有失败条目，且已注入「既往失败教训」取用钩子
- **WHEN** 该会话发起新一轮
- **THEN** 教训以**独立系统块**（「既往失败教训：」）注入推理提示，SHALL NOT 折入「相关事实」
  或历史消息；块按会话取数、有界

#### Scenario: 未注入教训钩子时提示词逐字不变

- **GIVEN** 未注入「既往失败教训」取用钩子（缺省）
- **WHEN** 装配本轮推理提示
- **THEN** 不产教训块，`failure_lessons` 字段恒为空，提示词与引入本能力前**逐字不变**

#### Scenario: 失败教训块有界
- **GIVEN** 某会话有 5 条超长失败条目
- **WHEN** 组合根渲染「既往失败教训」注入块
- **THEN** 块内至多 5 条、单条正文 ≤500 字符、总正文 ≤1500 字符

### Requirement: 横切中间件插入
系统 SHALL 支持在循环关键节点插入横切中间件（权限、约束、遥测、上下文）。中间件分两类接缝：
① **动作前链**（`middlewares`）：每个动作执行前按注册序调用，接收（`LoopContext`, `Action`），
可改写动作或返回 `None`；任一返回 `None` 即短路（动作不执行，本轮以已拒绝回复终止）。
② **结果侧观察者链**（`action_observers`）：每个**非终止**动作完成后按注册序回调，接收
（`LoopContext`, `Action`, `ActionResult`）；**仅通知** —— 观察者抛错降级为遥测、
**不改变本轮的结局与终止语义**；终止动作（空 `tool_id`）不触发观察者。

两类接缝的返回值 MAY 为可等待对象（coroutine）；系统 SHALL 逐个 `await` 后再继续。同步实现
（不返回可等待对象）SHALL 与引入该能力前**逐字等价**。轮首 / 轮尾另有同步注入点
（`turn_before` / `turn_after`）：`turn_before` 返回 `False` ⇒ 本轮以已拒绝回复终止；
`turn_after` 仅留痕、SHALL NOT 改变本轮结局。

#### Scenario: 中间件按序执行
- **GIVEN** 已注册一组横切中间件（同步或异步）
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

#### Scenario: 轮首注入点可否决本轮
- **GIVEN** 已注入 `turn_before` 且其返回 `False`
- **WHEN** 新一轮开始
- **THEN** 推理 SHALL NOT 被调用，本轮以已拒绝回复终止；轮尾注入点仍照常投递

### Requirement: 错误与预算控制
系统 SHALL 限制单任务最大循环次数与 token 预算，超出即终止或转人工。两项上限 SHALL 可经配置链
（CLI flag > env > config.yaml > 默认值）设定并经 ConfigSpec 单一真源声明：`loop.max_rounds`
（默认 `20`）与 `loop.output_reserve`（输出预留，默认 `8192`）。token 预算 SHALL 由模型上下文窗口
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

#### Scenario: 缺省轮数放宽至 20
- **GIVEN** 配置链未设置 `loop.max_rounds`
- **WHEN** 组合根装配执行循环
- **THEN** 单任务最大循环次数取 `20`；显式配置值仍逐字生效

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

### Requirement: 推理动作解析与失败可见

循环 SHALL 把推理输出解析为**终止动作**（空 `tool_id`，本轮进入回复收尾）或**工具动作**
（非空 `tool_id`，交给执行链）。解析 SHALL 覆盖五种形态，且**只认严格形态、不做启发式猜测**：

1. **原生工具调用**（provider 返回的 `tool_calls`）：优先于内容协议，行为与既有实现逐字一致；
2. **纯 JSON 对象**（整段内容即 `{"tool_id": …, "args": …}`；**允许其后跟随退化残渣** ——
   即仅由结构性符号构成的余部（多余闭合符 / 围栏符 / 零散标点 / 空白），**不含**字母、数字、
   CJK 等**词元**字符；残渣是产出退化、非夹带正文）：行为与既有实现逐字一致；
3. **尾部动作 JSON**（内容不以 `{` 开头，但其**尾部**为一个可解析的 JSON 对象、且含非空
   `tool_id`；允许其后跟随**退化残渣** —— 与形态 2 **同一定义**，含以 Markdown 围栏收尾）：
   SHALL 按工具动作处理，与形态 2 **同一套语义**（参数校验仍由工具调用链承担，本层不另造副本）；
4. **未闭合的动作载荷**（内容不以 `{` 开头、尾部亦无可解析的含 `tool_id` JSON 对象，但
   **尾部存在**一处以 `"tool_id"` 标记起、**到内容结束仍未闭合**的 JSON 结构 —— 即模型确实在
   **发出**动作协议，只是产出被截断或被写坏）：SHALL 以**失败态终止动作**收尾，SHALL NOT
   把该段原文当作最终回复。
5. **夹带的动作 JSON**（内容不以 `{` 开头、**非尾部**处存在一处**已闭合**的可解析 JSON 对象、
   且含非空 `tool_id` —— 即模型确实写出了一个完整动作协议，却又在其后追加了**正文**）：SHALL 以
   **失败态终止动作**收尾（`LLM_PLAN_PARSE_FAILED`），SHALL NOT 把该段原文当作最终回复、
   SHALL NOT 执行该动作（本层 SHALL NOT 做「JSON 在正文中间该不该执行」的启发式猜测）。
   本条判据中的「正文」SHALL 限定为**含词元**的余部；其后**仅**为**退化残渣**（不含词元，
   与形态 2 同一定义）时 SHALL NOT 命中本形态 —— 残渣不构成「追加了正文」的证据，据此丢弃一个
   **完整可用**的动作 SHALL NOT 发生（本形态的判据 SHALL 与形态 2 的容残渣判据**同一谓词、朝向相反**）。

形态 4 的判据 SHALL 为**严格形态**：自**最后一次**出现的 `"tool_id"` 回退至其外层 `{`，做
**字符串感知**的括号深度扫描，深度**从未**回到 0 即命中。**闭合**的尾部对象 —— 不论其后是否
仍有正文、是否含 `tool_id` —— SHALL NOT 命中本形态。

内容不以 `{` 开头、且**尾部无可解析的动作对象、文本中亦无夹带的动作对象**时，整段内容 SHALL
作为**自然语言回复**（终止动作）—— 与既有实现逐字一致。正文中间夹带的**非动作** JSON 对象
（**无** `tool_id` 字段，如示例 / 配置）SHALL NOT 触发动作解析（仍按回复）；正文中间夹带的
**动作** JSON 对象（含非空 `tool_id`）SHALL 归一为**形态 5**。本条 SHALL **取代**既有「正文
中间夹带一律按回复」的语义 —— 旧语义把「完整动作协议 + 尾随正文」整段当答复（记成功、JSON
进转录与记忆的**静默零执行**），其代价高于一次**可见**的解析失败。

推理产出**不可用**（解析失败 `LLM_PLAN_PARSE_FAILED` 各分支、模型调用失败）时，循环 SHALL 以
**失败态终止动作**收尾：该轮 `trajectory` 记 `ok=False`、`loop_finished` 载荷 `failed=true`、
`LoopResult.failed=true`、收尾观察者 SHALL 收到 `ok=False`。该失败态 SHALL NOT 外溢为工具执行
语义 —— 工具动作失败是否影响本轮成败 SHALL NOT 由本条约束（另议）。

失败态终止动作中，「内容以 `{` 开头但无法解析」、**形态 4** 与**形态 5** 三类 SHALL 另带**有界的原始产出**
（`Action.raw_output`，上界由实现定，超出即截断），供呈现层折叠展示与 trace 留痕；该原始产出
SHALL NOT 写入转录 / 记忆 / 笔记，SHALL NOT 并入 `reply`（`reply` SHALL 为**可读提示**）。
**形态 4** 与「内容以 `{` 开头但无法解析」的成因措辞 SHALL 在判据命中时区分：命中**未闭合载荷**
判据（复用形态 4 的严格判据）⇒ provider 报告 `finish_reason="length"` 时提示 SHALL 明示**被截断**、
信号不可用时提示为**未闭合**（疑似截断或写坏）；命中**夹带**判据（复用形态 5 的判据，含**对象在前、
正文在后**的形态）⇒ 提示 SHALL 明示「动作 JSON 之后仍跟有正文」；皆不命中 ⇒ 通用「无法解析」提示。
三类措辞**失败语义相同**（失败态、有界原始产出、不进持久面均不变），只改提示信息量。

解析失败的**回喂重试** SHALL 受配置门控（`loop.parse_retry`，缺省**关**）：开启时，推理产出不可用
（`LLM_PLAN_PARSE_FAILED` 各分支）且本轮**未外发任何内容增量**的场合，规划器 SHALL 以同一上下文
追加一条**用户角色**的回喂消息后重试推理**恰一次** —— 消息内容为**失败成因**与**输出格式协议重申**
（含「较长内容分多次、每次写一小段」的用法提示），SHALL NOT 携带该轮原始退化产出（守「有界原始
产出不回模型、不进持久面」的既有边界）；重试可解析 ⇒ 按正常结果处理（工具动作或终止回复）；
重试仍不可用 ⇒ 维持本条失败语义（两次模型调用，不第三次重试）。已外发内容增量（自然语言流已
逐段外发）的场合 SHALL NOT 重试（不得让已见内容「回滚」）；配置关闭（缺省）⇒ 请求形状、模型
调用次数与失败语义与既有实现**逐字一致**。

#### Scenario: 混写正文的动作 JSON 被识别为工具调用

- **GIVEN** 模型内容为「一段解释文字 + 换行 + `{"tool_id": "tools.code_run", "args": {…}}`」
- **WHEN** 循环解析该输出
- **THEN** 得到**工具动作**（`tool_id` 为该 JSON 的 `tool_id`、`args` 为其 `args`），本轮进入执行
- **AND** SHALL NOT 把整段文字当作最终回复

#### Scenario: 围栏包裹的尾部动作 JSON 被识别

- **GIVEN** 模型内容为解释文字 + ```` ```json ```` 围栏包裹的 `{"tool_id": …, "args": …}`
- **WHEN** 循环解析该输出
- **THEN** 同样得到**工具动作**

#### Scenario: 非动作 JSON 的自然语言回复不被误判

- **GIVEN** 模型内容不含任何**含非空 `tool_id`** 的 JSON（纯文本、或正文中夹带**无** `tool_id`
  的示例 JSON、或示例对象在文末但**无** `tool_id` 字段、或示例对象在文末但**已闭合**）
- **WHEN** 循环解析该输出
- **THEN** 得到**终止动作**，`reply` 为该段原文，且**不标记**失败
- **AND** 与既有实现逐字一致（零回归）

#### Scenario: 夹带的动作 JSON 归一为可见失败

- **GIVEN** 模型内容为「正文 + 一处**已闭合**的 `{"tool_id": …, "args": {…}}` + 其后的正文」
  （动作 JSON **不在**文末，即尾部对象之外另有可解析的含 `tool_id` 对象）
- **WHEN** 循环解析该输出
- **THEN** 得到**失败态终止动作**，`reply` 为 `LLM_PLAN_PARSE_FAILED` 可读提示且**不含** `"tool_id"`
- **AND** 该动作 **SHALL NOT** 被执行，SHALL NOT 把整段原文当作最终回复
- **AND** `Action.raw_output` 非空有界，本轮 `trajectory` 该步 `ok=False`

#### Scenario: 动作 JSON 之后的退化残渣不阻止执行

- **GIVEN** 模型内容为一个**完整**的 `{"tool_id": "tools.file_write", "args": {…}}`，其后**仅**为
  **退化残渣**（产出退化多出的一个 `}`、或围栏符、或零散标点），**不含**任何词元字符
- **WHEN** 循环解析该输出
- **THEN** 得到**工具动作**（`tool_id` / `args` 取自该对象），本轮进入执行
- **AND** SHALL NOT 标记失败、SHALL NOT 记 `raw_output`（未发生解析失败）
- **AND** 与形态 2 / 形态 3 的容残渣判据**同一谓词、朝向相反**（形态 5 要求余部含词元）

#### Scenario: 残渣容错不适用于其后含词元的内容

- **GIVEN** 模型内容为一个**完整**的动作 JSON，其后跟随**含词元**的正文（字母 / 数字 / CJK）
- **WHEN** 循环解析该输出
- **THEN** 得到**失败态终止动作**（形态 5 语义**不变**，`reply` 明示「动作 JSON 之后仍跟有正文」）
- **AND** 该动作 SHALL NOT 被执行；`Action.raw_output` 非空有界

#### Scenario: 解析失败使本轮失败

- **GIVEN** 模型内容无法解析为动作（如 `{"tool_id": "tools.echo",` 截断的 JSON）
- **WHEN** 循环完成该轮
- **THEN** 本轮 `trajectory` 的该步 `ok=False`
- **AND** `loop_finished` 载荷 `failed=true` 且 `LoopResult.failed=true`
- **AND** 收尾观察者收到的成败为 `ok=False`

#### Scenario: 纯 JSON 与原生工具调用路径零回归

- **GIVEN** 模型输出为纯 JSON 对象、或 provider 返回原生 `tool_calls`
- **WHEN** 循环解析该输出
- **THEN** 解析结果与既有实现**逐字一致**（含缺 `tool_id`/`reply` 时的 `LLM_PLAN_PARSE_FAILED` 文案）

#### Scenario: 未闭合的动作载荷不再被当作正文

- **GIVEN** 模型内容为「一段解释文字 + 换行 + `{"tool_id": "tools.file_write", "args": {"path":
  "a.md", "content": "一段长正文` 」（外层对象**未闭合**，文本末尾止于内层字符串）
- **WHEN** 循环完成该轮
- **THEN** 得到**失败态终止动作**，`reply` 为可读提示且**不含** `"tool_id"`
- **AND** 本轮 `trajectory` 的该步 `ok=False`、`loop_finished` 载荷 `failed=true`、
  `LoopResult.failed=true`、收尾观察者收到 `ok=False`

#### Scenario: 未闭合载荷的原始产出有界且不进持久面

- **GIVEN** 模型内容命中形态 4（未闭合动作载荷）
- **WHEN** 循环完成该轮
- **THEN** 该终止动作的 `Action.raw_output` 非空且长度不超过实现上界，`LoopResult.raw_output` 与之一致
- **AND** 本轮转录与记忆沉淀 SHALL NOT 含该原始产出（只含可读提示）

#### Scenario: provider 报告截断时提示区分成因

- **GIVEN** 模型内容命中形态 4，且 provider 报告 `finish_reason="length"`
- **WHEN** 循环完成该轮
- **THEN** `reply` 的提示 SHALL 明示「截断」
- **AND** `finish_reason` 不可用（未携带 / 空串）时，提示 SHALL 为「未闭合」措辞，且失败语义
  （`failed=true` / `ok=False`）与前者**相同**

#### Scenario: 首字符花括号的未闭合载荷区分成因

- **GIVEN** 模型内容以 `{` 开头、整体无法 `json.loads` 解析，且命中**未闭合载荷**判据
- **WHEN** 循环解析该输出
- **THEN** 得到失败态终止动作：`finish_reason="length"` ⇒ `reply` 明示「被截断」；信号不可用 ⇒
  `reply` 为「未闭合」措辞；二者失败语义相同，`Action.raw_output` 非空有界

#### Scenario: 首字符花括号闭合对象后仍有正文明示成因

- **GIVEN** 模型内容以 `{` 开头、整体无法解析，其中含一处**已闭合**的动作对象、其后仍有正文
- **WHEN** 循环解析该输出
- **THEN** `reply` 明示「动作 JSON 之后仍跟有正文」，失败语义与形态 5 相同

#### Scenario: 首字符花括号皆不命中判据时维持通用文案

- **GIVEN** 模型内容以 `{` 开头、整体无法解析，且既无未闭合动作载荷、亦无夹带的动作对象
- **WHEN** 循环解析该输出
- **THEN** `reply` 为通用「无法解析模型输出为动作」提示（逐字），失败语义不变

#### Scenario: 解析失败回喂重试恰一次

- **GIVEN** `loop.parse_retry` 已开启，模型首次输出不可解析，且本轮未外发任何内容增量
- **WHEN** 该轮推理执行
- **THEN** 规划器以同一上下文追加一条**用户角色**回喂消息重试**恰一次**：消息含失败成因与输出
  格式协议重申、**不含**原始退化产出；重试可解析 ⇒ 按正常结果处理（本轮不因首次失败而失败）

#### Scenario: 重试仍失败恰两次模型调用

- **GIVEN** `loop.parse_retry` 已开启，模型两次输出均不可解析
- **WHEN** 该轮推理执行
- **THEN** 本轮以失败态终止动作收尾（`reply` 为 `LLM_PLAN_PARSE_FAILED` 可读提示），模型调用
  **恰两次**、不发起第三次重试

#### Scenario: 已外发流式内容不重试

- **GIVEN** `loop.parse_retry` 已开启，流式推理已判定为自然语言回复并**逐段外发**了内容增量，
  最终整段无法解析为动作
- **WHEN** 该轮推理执行
- **THEN** 不重试（模型调用恰一次），维持既有失败语义

#### Scenario: 缺省关闭零重试

- **GIVEN** `loop.parse_retry` 未开启（缺省）
- **WHEN** 模型输出不可解析
- **THEN** 模型调用恰一次、请求不含回喂消息，请求形状与失败语义与既有实现**逐字一致**

### Requirement: 收尾与维护工作的执行线程

循环的收尾与维护工作（轮内上下文压实、收尾钩子 `turn_observer`、维护节拍含冷路径回调）SHALL 在
**事件循环之外**执行：循环 SHALL 在**工作线程**上运行这三段工作并等待其完成，SHALL NOT 在事件循环
线程上同步执行它们。

理由是这三段工作**可能含同步模型调用**（组合根注入的 `_llm_text` 接缝：会话摘要、结构化关键事实抽取、
SOP 提炼、技能迭代、进化 review / patch author），而本仓 LLM 传输层的同步形态（`LLMProvider.completion`）
以 `asyncio.run` 桥接、**在运行中的事件循环线程上必然失败**（`RuntimeError`）；同时该工作段的耗时为
**模型网络往返**（秒级），在事件循环线程上执行会阻塞其余任务与呈现。

本条 SHALL NOT 改变：三段工作各自的**失败降级**语义（仍逐段捕获、仍降级留痕、仍不中断本轮）、
其**触发条件**（压实阈值 / 轮维护节拍）、其**产物与终态语义**（回复、事件序、终止条件、转录追加），
以及各**注入接缝的同步契约**（`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor`
仍为同步可调用对象）—— 卸载的是**执行线程**，不变的是**接口与语义**。

#### Scenario: 收尾钩子在工作线程上执行

- **GIVEN** 已注入 `turn_observer` 的一次执行
- **WHEN** 本轮收尾调用该观察者
- **THEN** 观察者在**没有运行中事件循环**的线程上被调用（其内可安全使用以 `asyncio.run` 桥接的同步调用）

#### Scenario: 冷路径回调在工作线程上执行

- **GIVEN** 一次执行收尾时距上次维护已达 `maintenance_interval`，且已注入冷路径回调
- **WHEN** 循环执行收尾维护节拍
- **THEN** 冷路径回调在**没有运行中事件循环**的线程上被调用

#### Scenario: 轮内压实不阻塞事件循环

- **GIVEN** 本轮触发上下文压实，且压实过程含**阻塞**的模型调用（耗时可控的替身）
- **WHEN** 压实进行中
- **THEN** 事件循环 SHALL 仍能推进**其他**协程任务（压实不占用事件循环线程）

#### Scenario: 含同步模型调用的压实产出真的落库

- **GIVEN** 会话摘要接缝以**同步**模型调用桥接（`asyncio.run` 形态）注入，且本轮触发压实
- **WHEN** 本轮完成
- **THEN** 会话摘要**被写入**（不因 `RuntimeError` 而被吞），且**不产出** `maintenance_failed` 遥测

#### Scenario: 降级语义零回归

- **GIVEN** 已注入的收尾观察者 / 冷路径回调执行时抛错
- **WHEN** 本轮收尾
- **THEN** 仅降级留痕（`turn_observer_failed` / `cold_path_failed` / `maintenance_failed`），
  本轮回复、终止条件、事件序与既有实现**逐字一致**

### Requirement: 运行环境事实

系统 SHALL 在推理用系统提示中提供可选的**运行环境事实**块，使模型按**宿主实际 OS 与默认
shell 方言**规划命令，而非假定一切为 POSIX bash。

- **事实内容**：块 SHALL 至少包含操作系统标识（Windows / Darwin / Linux 等）与默认 shell
  方言（powershell / bash / unknown）；SHALL 在可得时附带壳的简短标签（含主次版本更佳）；
  SHALL 含与该方言相关的路径与句法约束（有界、不得无界膨胀）。
- **可用性与标签**：块 SHALL 列出宿主 PATH 上**实际可用**的 shell（`pwsh` / `powershell` /
  `bash` 中可用者）；SHALL 区分 `PowerShell 7+（pwsh）` 与 `Windows PowerShell 5.1
  （powershell）` 两种标签；默认 shell 的解释器不可用时 SHALL 明确建议改用 `type=python`
  （当前解释器始终可用）。
- **进程与目录语义**：块 SHALL 说明每次 `code_run` 都是**全新进程**（`cd` 与环境变量不跨调用
  保留），需要指定目录时使用 `cwd`（绝对路径；支持 `~` 展开）。
- **有界回退**：块 SHALL 给出**有界**的 Python 回退规则 —— 仅在目标方言不可用或脚本无法用该
  方言表达时回退 `type=python`，优先 `pathlib` / `tempfile` 等标准库，SHALL NOT 硬编码
  `/tmp`，且 SHALL NOT 用 Python 回退掩盖方言错误。
- **未知 OS 诚实**：OS 不在已知集合时，块 SHALL 声明默认 shell 未知并建议显式 `type`，
  SHALL NOT 声称默认壳为 bash。
- **装配位置**：事实块 SHALL 作为系统提示的**独立块**注入，SHALL NOT 仅埋在工具 description
  里才算满足本 Requirement。
- **注入方向**：环境快照由组合根或测试替身注入；loop/planner SHALL NOT 在热路径强依赖不可
  替换的全局单例而导致单测打到真实 PATH。
- **未注入逐字不变**：未注入环境快照时，系统提示 SHALL NOT 新增「运行环境」块，与既有装配
  **逐字一致**。
- **不替代执行契约**：本 Requirement 只约束提示事实；命令实际执行方言与缺解释器行为见
  tool-use「内置原子工具」。

#### Scenario: 注入后系统提示含运行环境块

- **GIVEN** planner 已注入非空环境快照（含 OS 与默认 shell）
- **WHEN** 装配本轮系统提示
- **THEN** 提示中含独立「运行环境」类块，且可见该 OS 与默认 shell 关键字

#### Scenario: 未注入时不产块

- **GIVEN** planner 未注入环境快照
- **WHEN** 装配本轮系统提示
- **THEN** 不出现「运行环境」块，其余块序与既有行为兼容（无该块时的提示与未引入本能力前一致）

#### Scenario: Windows 且 bash 可用时提示可用方言与版本标签

- **GIVEN** 宿主为 Windows，PATH 上同时存在 `pwsh` 与 `bash`
- **WHEN** 渲染运行环境块
- **THEN** 块中可见 `pwsh` 与 `bash` 两项可用 shell，且默认 shell 标签含 `PowerShell 7+`

#### Scenario: 默认 shell 不可用时建议 python

- **GIVEN** 宿主为 Windows，但 PATH 上既无 `pwsh` 也无 `powershell`
- **WHEN** 渲染运行环境块
- **THEN** 块中明确建议 `type=python`，且不声称默认 PowerShell 可用

#### Scenario: 提示声明全新进程与 cwd 语义

- **GIVEN** planner 已注入任一非空环境快照
- **WHEN** 渲染运行环境块
- **THEN** 块中说明每次 `code_run` 为全新进程、`cd` 与环境变量不保留，并指出用 `cwd`
  （支持 `~`）指定目录

### Requirement: 预算溢出的降级续跑

token 预算触顶 SHALL 先尝试**一次降级**再终止：已注入压实器时，本轮 SHALL 至多触发一次
强制压实（复用轮内 `compacted` 闸门防重入），并为模型**再给一轮**收尾机会；该收尾轮内任务
完成（`ctx.done()`）⇒ SHALL 按正常完成收口，SHALL NOT 以 `TOKEN_BUDGET_EXCEEDED` 覆盖已完成的
回复；收尾轮仍未完成 ⇒ SHALL 以 `TOKEN_BUDGET_EXCEEDED` 终止。降级 SHALL 每轮至多一次
（`budget_retried` 标记），SHALL NOT 无限重试。未注入压实器 ⇒ SHALL 保持既有行为（预算触顶
立即终止，零额外轮次）。降级发生 SHALL 经 trace 留痕（便于诊断预算配置过小），SHALL NOT
改变既有终止码或事件类型。

#### Scenario: 预算触顶先压实再重试一轮
- **GIVEN** 已注入压实器且本轮记账值达到 token 预算
- **WHEN** 一步执行完毕判定预算
- **THEN** 先触发一次强制压实（若本轮尚未压实），记 `budget_retry` 留痕，再允许模型执行一轮

#### Scenario: 收尾轮完成则正常收口
- **GIVEN** 预算触顶并进入收尾轮
- **WHEN** 收尾轮产出终止动作并完成本轮
- **THEN** 按正常完成收口，回复为模型产出，不标记 `TOKEN_BUDGET_EXCEEDED`

#### Scenario: 收尾轮仍未完成则终止
- **GIVEN** 预算触顶并进入收尾轮
- **WHEN** 收尾轮仍未完成且记账值仍不低于预算
- **THEN** 以 `TOKEN_BUDGET_EXCEEDED` 终止（每轮至多一次降级，不重复重试）

#### Scenario: 未注入压实器行为不变
- **GIVEN** 未注入压实器
- **WHEN** 本轮记账值达到 token 预算
- **THEN** 立即以 `TOKEN_BUDGET_EXCEEDED` 终止，SHALL NOT 额外执行轮次

### Requirement: 流式中断留痕

`astream` SHALL 在**未正常收尾**时留下可落盘的遥测证据：消费方提前关闭（`GeneratorExit`）、
调用被取消（`CancelledError`）或执行体抛出未收尾异常时，循环 SHALL 先记录一条
`loop_aborted` 遥测事件（载荷含**有界**的 `reason`，SHALL NOT 含用户文本 / 异常消息 / 密钥），
随后 `end_trace` **封口**，使本轮已记录的事件经导出器落盘，SHALL NOT 静默丢失。

正常收尾路径 SHALL NOT 产出 `loop_aborted`，其事件序、`trace_observer` 回调时机与
`end_trace` 封口时机 SHALL 逐字不变（回调仍能完整回放，封口仍在回调之后）。中断路径
SHALL NOT 追加助手转录、SHALL NOT 写轮末完成记忆、SHALL NOT 改变既有回滚语义。

#### Scenario: 消费方提前关闭留痕
- **GIVEN** 一次流式执行已产出部分事件，消费方在终态前关闭事件流
- **WHEN** 事件流被关闭
- **THEN** 本轮 trace 新增 `loop_aborted` 并经导出器落盘，trace 不再驻留内存

#### Scenario: 执行体异常留痕
- **GIVEN** 已注入 tracer，执行体在正常收尾前抛出异常
- **WHEN** 异常向外传播
- **THEN** 先记录 `loop_aborted` 并封口本轮 trace，再原样抛出该异常

#### Scenario: 正常收尾不产中断事件
- **GIVEN** 一次正常完成的执行
- **WHEN** 本轮收尾
- **THEN** trace 中**不含** `loop_aborted`，既有事件与封口语义不变

### Requirement: 轮内压实进度与上限

轮内压实（阈值触发与预算降级触发）SHALL 有可观测的进度与总时长上限：

- 阈值压实前后 SHALL 各产出一条事件：`loop.compacting`（载荷含 `round`）与
  `loop.compacted`（载荷含 `round`、`elapsed_ms`、`timeout`）；载荷 SHALL NOT 含正文或摘要。
- 压实总时长 SHALL 有上限（缺省 `120` 秒，可经构造注入覆盖；`None` ⇒ 不设上限）。
  超过上限时 SHALL 记 `maintenance_failed`（`step="compaction_timeout"`）并**放行本轮**：
  本轮继续推进、至多再压实一次，SHALL NOT 因压实超时中断或挂起。
- 未注入压实器时 SHALL NOT 产出上述两条事件（事件面与既有缺省一致）。

#### Scenario: 压实前后产出进度事件
- **GIVEN** 注入压实器且本轮达到压实阈值
- **WHEN** 轮内压实执行
- **THEN** 依次产出 `loop.compacting` 与 `loop.compacted`，后者含非负 `elapsed_ms` 且
  `timeout=False`，其后本轮正常收尾

#### Scenario: 压实超时放行本轮
- **GIVEN** 压实执行超过注入的总时长上限
- **WHEN** 等待超时
- **THEN** 产出 `loop.compacted`（`timeout=True`）并记录
  `maintenance_failed.step="compaction_timeout"`，本轮继续推进至正常终态

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

### Requirement: 失败回滚可见性

动作失败触发回滚时，系统 SHALL 让**模型与运维侧**都能看到回滚结果，SHALL NOT 静默丢弃
`RollbackReport`。

- 回滚范围 SHALL 保持**按 trace 整轮**（逆序撤销该轮已记录的全部可逆效应），SHALL NOT 缩窄为
  只撤销失败动作自身的效应。
- 当回滚**确有撤销或撤销失败**（`reverted` 或 `undo_failed` 非空）时，循环 SHALL 产出
  `kind="trace_rolled_back"` 遥测，载荷键 SHALL 恰为 `reverted` / `undo_failed`（非负计数）；
  SHALL NOT 含 `EffectId`、路径、参数、错误正文或其他正文。
- 失败动作回灌给模型的 tool observation SHALL 在**非空**回滚时附加
  `rollback: {"reverted": <count>, "undo_failed": <count>}`；空回滚时 observation 的键集与
  既有逐字一致（SHALL NOT 出现空的 `rollback` 键）。
- 回滚 SHALL 在观测回灌**之前**完成：模型看到失败结果时，先前成功写入已按逆序撤销（或已记录
  撤销失败）。
- 撤销失败的效应 SHALL 留在账目隔离（既有 QUARANTINE 语义），SHALL NOT 自动重试或删除。
- 终止动作不产生 observation（既有语义），但其失败触发的回滚 SHALL 照常产出遥测。
- 事件流七类 `LoopEvent` 契约 SHALL 不变（本能力只走 `Tracer`）。

#### Scenario: 先前写入被撤销且模型可见
- **GIVEN** 本轮先有一个成功的可逆写动作，随后另一个动作失败
- **WHEN** 循环执行失败回滚
- **THEN** 该写动作的 undo 被调用；失败动作的 tool observation 含
  `rollback.reverted=1`、`rollback.undo_failed=0`；trace 记 `trace_rolled_back`（同计数）

#### Scenario: 无效应可撤销时保持逐字一致
- **GIVEN** 失败动作之前本轮没有任何已记录效应
- **WHEN** 循环执行失败回滚
- **THEN** tool observation 不含 `rollback` 键，且不产出 `trace_rolled_back` 遥测

#### Scenario: 撤销失败被如实上报
- **GIVEN** 本轮成功写入的效应 undo 抛错，随后另一个动作失败
- **WHEN** 循环执行失败回滚
- **THEN** observation 与 `trace_rolled_back` 均报 `undo_failed=1`；该效应仍留在账目隔离
