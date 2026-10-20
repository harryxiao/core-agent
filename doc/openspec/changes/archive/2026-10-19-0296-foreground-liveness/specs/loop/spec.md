# loop — 前台轮不被后台收尾与压实拖死（change 0296）

## MODIFIED Requirements

### Requirement: 收尾与维护工作的执行线程

循环的收尾与维护工作（轮内上下文压实、收尾钩子 `turn_observer`、维护节拍含冷路径回调）SHALL 在
**事件循环之外**执行：循环 SHALL 在**工作线程**上运行这三段工作，SHALL NOT 在事件循环线程上
同步执行它们。

理由是这三段工作**可能含同步模型调用**（组合根注入的 `_llm_text` 接缝：会话摘要、结构化关键事实抽取、
SOP 提炼、技能迭代、进化 review / patch author），而本仓 LLM 传输层的同步形态（`LLMProvider.completion`）
以 `asyncio.run` 桥接、**在运行中的事件循环线程上必然失败**（`RuntimeError`）；同时该工作段的耗时为
**模型网络往返**（秒级），在事件循环线程上执行会阻塞其余任务与呈现。

轮末收尾（`turn_observer` + 维护节拍）SHALL **不阻塞下一轮**：

- 流式执行入口（`astream`）在轮首 SHALL NOT 等待上一轮的后台收尾；上一轮收尾仍在执行时
  SHALL 仅留痕（`post_turn_overlap`），并立即进入本轮感知。
- 各轮收尾 SHALL 在后台**单链路串行**：后一轮收尾排在前一轮收尾结束之后执行，SHALL NOT
  在上一轮收尾未结束时并发启动新收尾（避免技能/记忆写入并发踩踏）。
- 同步执行入口（`arun` / `run`）可等待本链末端以保持「返回即含完整收尾」的既有语义，但该等待
  SHALL 有上限（缺省 `120` 秒，可经构造注入覆盖）；超时 SHALL 留痕（`post_turn_timeout`）
  并正常返回本轮结果，SHALL NOT 无限期挂起。
- 维护节拍 SHALL 有总时长上限（缺省 `120` 秒，可经构造注入覆盖）：截止后 SHALL 跳过尚未执行的
  步骤，并逐项留痕 `maintenance_failed`（`error="deadline_exceeded"`），SHALL NOT 发起新的
  模型调用。

本条 SHALL NOT 改变：三段工作各自的**失败降级**语义（仍逐段捕获、仍降级留痕、仍不中断本轮）、
其**触发条件**（压实阈值 / 轮维护节拍）、其**产物与终态语义**（回复、事件序、终止条件、转录追加），
以及各**注入接缝的同步契约**（`turn_observer` / `cold_path` / `summarizer` / `key_fact_extractor`
仍为同步可调用对象）—— 卸载的是**执行线程与前台等待**，不变的是**接口与语义**。

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

#### Scenario: 上一轮收尾挂起不阻塞下一轮

- **GIVEN** 上一轮的 `turn_observer` 或维护节拍仍在执行（阻塞替身）
- **WHEN** 宿主发起下一轮流式执行
- **THEN** 下一轮 SHALL 在**不等待**上一轮收尾的情况下产出首条业务事件与正常终态；
  并留痕 `post_turn_overlap`

#### Scenario: 后台收尾单链路串行

- **GIVEN** 连续两轮均触发收尾，且第一轮收尾尚未结束
- **WHEN** 第二轮收尾被调度
- **THEN** 第二轮收尾 SHALL 等第一轮收尾结束后才执行；两轮观察者调用顺序与轮序一致

#### Scenario: 同步入口有界等待

- **GIVEN** 收尾钩子阻塞时间超过注入的等待上限
- **WHEN** 调用 `arun` / `run`
- **THEN** 调用 SHALL 在上限附近返回本轮结果，并留痕 `post_turn_timeout`；SHALL NOT 挂起至收尾结束

#### Scenario: 维护节拍截止后跳过剩余步骤

- **GIVEN** 一次维护节拍的第 1 步耗时超过注入的总时长上限
- **WHEN** 循环继续执行后续步骤
- **THEN** 后续步骤 SHALL 被跳过，并逐项留痕
  `maintenance_failed`（`error="deadline_exceeded"`）；本轮回复与终态不变

#### Scenario: 含同步模型调用的压实产出真的落库

- **GIVEN** 会话摘要接缝以**同步**模型调用桥接（`asyncio.run` 形态）注入，且本轮触发压实
- **WHEN** 本轮完成
- **THEN** 会话摘要**被写入**（不因 `RuntimeError` 而被吞），且**不产出** `maintenance_failed` 遥测

#### Scenario: 降级语义零回归

- **GIVEN** 已注入的收尾观察者 / 冷路径回调执行时抛错
- **WHEN** 本轮收尾
- **THEN** 仅降级留痕（`turn_observer_failed` / `cold_path_failed` / `maintenance_failed`），
  本轮回复、终止条件、事件序与既有实现**逐字一致**

### Requirement: 轮内压实进度与上限

轮内压实（阈值触发与预算降级触发）SHALL 有可观测的进度与总时长上限：

- 阈值压实前后 SHALL 各产出一条事件：`loop.compacting`（载荷含 `round`）与
  `loop.compacted`（载荷含 `round`、`elapsed_ms`、`timeout`）；载荷 SHALL NOT 含正文或摘要。
- 压实总时长 SHALL 有上限（缺省 `60` 秒，可经 `loop.compact_timeout` 配置覆盖，亦可经构造注入
  直接覆盖；`None` ⇒ 不设上限）。超过上限时 SHALL 记 `maintenance_failed`
  （`step="compaction_timeout"`）并**放行本轮**：本轮继续推进、至多再压实一次，SHALL NOT
  因压实超时中断或挂起。
- 该上限 SHALL 同时作为压实工作线程的**协作式截止时间**传给 `MemoryStore.compact`：
  截止后工作线程 SHALL NOT 发起新的模型调用（见 memory「压实的协作式截止与单飞」）。
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

#### Scenario: 超时后工作线程不再发起新调用
- **GIVEN** 压实工作线程收到与等待上限相同的截止时间，且单次模型调用在截止前已开始
- **WHEN** 该调用返回时已越过截止时间
- **THEN** 工作线程 SHALL 在下一个检查点停止，不再发起后续模型调用（不提交新的摘要）
