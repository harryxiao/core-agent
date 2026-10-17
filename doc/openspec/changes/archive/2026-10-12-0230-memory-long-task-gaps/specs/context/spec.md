# Delta — change 0230（context：可注入 token 估算器）

## ADDED Requirements

### Requirement: 可注入的 token 估算器

上下文预算测量 SHALL 支持**可注入的 token 估算器**：`BudgetManager` 与 `DynamicAssembler`
SHALL 接受 `TokenEstimator` 协议实现（`estimate(text: str) -> int`），注入后预算测量与裁剪
SHALL 使用该实现；未注入时 SHALL 回落共享启发式估算器（`core.tokens.estimate_tokens`，
CJK 感知），行为与引入本能力前**逐字一致**。估算器 SHALL 由调用方注入，本能力 SHALL NOT
引入任何第三方 tokenizer 依赖。

#### Scenario: 缺省估算器保持启发式口径
- **GIVEN** `BudgetManager` / `DynamicAssembler` 未注入估算器
- **WHEN** 执行预算测量与裁剪
- **THEN** 使用共享启发式估算器，测量结果与引入本能力前逐字一致

#### Scenario: 注入估算器替换预算测量
- **GIVEN** 注入了返回固定分值的 `TokenEstimator` 实现
- **WHEN** `BudgetManager.enforce` 测量上下文包并裁剪
- **THEN** `token_used` 与裁剪判定取自注入实现，SHALL NOT 再调用启发式估算

#### Scenario: 装配器透传估算器
- **GIVEN** `DynamicAssembler` 构造时注入估算器
- **WHEN** 调用 `build` 装配上下文
- **THEN** 预算测量使用该估算器（含派生装配器 `with_allow_source_prefixes`）
