## ADDED Requirements

### Requirement: 进化写回与技能内容的密钥形态脱敏

系统 SHALL 在进化侧把任何**自由文本**写入记忆后端或技能库之前，无条件执行 `redact_secrets`
（与 memory 侧同一判据、方向 over-redact）；注入的模型输出或人工输入**不构成信任边界**。

- `dissolve(target, reason)` 写回的 L2 教训内容 SHALL 先行脱敏。
- `reject(candidate, reason=...)` 写回的 L2 教训内容 SHALL 先行脱敏。
- `_crystallize_skill` 的 `description` / `preconditions` / `task_types`（以及既有 `instructions`）
  SHALL 先行脱敏；结构化 `param_schema` 不做文本改写（其字段名 / 类型不承载自由文本）。
- `_crystallize_plugin` 交付给 crystallizer 的 `content`（`issue`）SHALL 先行脱敏。
- 脱敏 SHALL NOT 改变未命中密钥形态的正文（逐字不变）；SHALL NOT 因脱敏改变结局
  （`redact_secrets` 为纯函数）。

#### Scenario: 溶解原因含密钥形态
- **GIVEN** 调用 `dissolve` 的 `reason` 含明文密钥形态子串，且记忆后端已注入
- **WHEN** 溶解写回 L2
- **THEN** 落库内容不含该明文（替换为 `<redacted>`），其余正文不变

#### Scenario: 人工拒绝理由含密钥形态
- **GIVEN** 调用 `reject(reason=...)` 的理由含明文密钥形态子串，且记忆后端已注入
- **WHEN** 拒绝写回 L2
- **THEN** 落库内容不含该明文（替换为 `<redacted>`），其余正文不变

#### Scenario: 技能内容字段含密钥形态
- **GIVEN** 候选 `delta["content"]` 的 `description` / `preconditions` / `task_types` 含明文密钥形态子串
- **WHEN** `crystallize` 写入技能库
- **THEN** 技能对象中对应字段不含该明文（替换为 `<redacted>`），其余内容不变
