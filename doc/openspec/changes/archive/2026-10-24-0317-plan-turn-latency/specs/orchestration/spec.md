# Spec Delta — orchestration（0317 拆解与验收的输出上界）

## ADDED Requirements

### Requirement: 拆解与验收调用的输出上界

LLM 拆解器（`LLMSubtaskPlanner`）与 LLM 验收器（`LLMVerifier`）SHALL 接受可选的**输出 token
上界**：注入**正数**上界时，二者发出的每次 `LLMRequest` SHALL 携带该上界（`max_tokens`）；
组合根 SHALL 以主循环**同一来源**（`loop.output_reserve`）注入，SHALL NOT 引入独立配置键。

未注入上界（缺省 / `None` / 非正值）时，二者 SHALL NOT 写该字段，请求内容与既往**逐字一致**。
该上界 SHALL 只约束输出长度，SHALL NOT 改变拆解口径、验收口径、拓扑序或离线回落语义。

#### Scenario: 注入上界后拆解与验收请求携带
- **GIVEN** 以正数上界构造的 LLM 拆解器与 LLM 验收器
- **WHEN** 各发起一次拆解 / 验收调用
- **THEN** 两次 `LLMRequest` 的 `max_tokens` 均等于该上界

#### Scenario: 未注入时请求逐字不变
- **GIVEN** 未指定上界构造的 LLM 拆解器与 LLM 验收器
- **WHEN** 各发起一次拆解 / 验收调用
- **THEN** 两次 `LLMRequest` 的 `max_tokens` 为「未设置」，其余字段与既往一致
