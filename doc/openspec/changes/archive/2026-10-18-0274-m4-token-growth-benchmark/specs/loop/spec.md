## ADDED Requirements

### Requirement: 长任务 token 增长基准

系统 SHALL 提供**离线、确定性**的长任务 token 增长基准（对应产品 M4：「长任务 token 增长随
任务数呈次线性」）：在**同一会话**内以固定任务序列驱动真实 `DefaultLoop`（`LLMPlanner` ＋
桩 provider ＋ 本地有界摘要器），逐轮采集装配后的 `prompt_tokens` 观测
（`LLMPlanner.last_prompt_tokens()`），输出增长曲线与斜率。

- 基准 SHALL NOT 依赖真实 LLM、embedder 或网络；时钟 SHALL 由注入的确定性时钟提供。
- 启用记忆外置（会话摘要 ＋ 三层滑窗）时，固定序列**远期**（窗口与摘要到界后）的逐轮
  `prompt_tokens` SHALL 恒定，且整体增长斜率 SHALL 低于「关闭摘要器与维护节拍、全量原文
  回灌」的线性基线。
- 同一输入两次重放 SHALL 产生逐轮一致的曲线。
- 基准 SHALL NOT 引入绝对 token 阈值门禁（选项 C 未采纳）；阈值与是否入门禁 SHALL 另行
  裁决。

#### Scenario: 固定序列采集
- **GIVEN** 固定任务序列（24 轮等长载荷）
- **WHEN** 在同一会话内逐轮驱动 `DefaultLoop`
- **THEN** 每轮采集到一个 `prompt_tokens` 观测，曲线长度 = 任务数且各值 > 0

#### Scenario: 记忆外置生效
- **GIVEN** 维护节拍按轮触发且会话摘要器已注入
- **WHEN** 首轮结束
- **THEN** 会话摘要条目存在，后续轮次按三层滑窗装配
- **AND** 窗口与摘要到界后的远期曲线逐轮恒定

#### Scenario: 次线性判定
- **GIVEN** 外置运行曲线与全量原文回灌的线性基线
- **WHEN** 比较整体斜率与末轮占用
- **THEN** 外置斜率低于基线斜率，且末轮 `prompt_tokens` 小于基线末轮

#### Scenario: 重放确定性
- **GIVEN** 同一 harness 与同一固定任务序列
- **WHEN** 独立运行两次
- **THEN** 两次的逐轮 `prompt_tokens` 曲线逐值一致
