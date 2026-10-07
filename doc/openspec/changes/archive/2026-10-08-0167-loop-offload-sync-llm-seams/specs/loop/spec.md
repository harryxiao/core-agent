# loop 规格 delta：loop-offload-sync-llm-seams

## ADDED Requirements

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
