## MODIFIED Requirements

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
