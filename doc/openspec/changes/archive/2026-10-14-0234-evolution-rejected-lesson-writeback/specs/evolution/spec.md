## ADDED Requirements

### Requirement: 未过门教训写回

系统 SHALL 在结晶面验证门未通过、候选被丢弃时，把教训写回记忆后端（兑现「验证门 /
未过门丢弃」场景的 L2/L3 承诺），并遵守分层语义：

- **L2（完整教训）**：id `evolution.gate_rejected.<candidate_id>`；内容含目标插件、诊断
  `issue`、门禁 `review` 与各门结果。`issue` SHALL **有界**（实现常量，缺省 **400** 字符，
  超出截断）。写前 SHALL `redact_secrets`。
- **L3（短指针）**：id `evolution.gate_rejected.l3.<candidate_id>`；内容 SHALL 为指向 L2
  条目的短指针（含 L2 id 引用、目标插件、review 判定词），**SHALL NOT** 与 L2 同文，
  **SHALL NOT** 再嵌入完整 `issue` 正文。写前 SHALL `redact_secrets`。
- **未注入跳过**：记忆后端未注入时 SHALL 静默跳过写回，SHALL NOT 抛错、SHALL NOT 改变
  `EvolutionOutcome(status="rejected")`。
- **前缀错开**：与人工 `reject` 的 `evolution.rejected.<candidate_id>`、以及
  `evolution.dissolve.*` **互不覆盖**。
- **不经 Crystallizer**：本写回 SHALL NOT 调用 `memory_crystallizer.crystallize`
  （该钩子不落盘）。

#### Scenario: 门禁拒绝写回 L2 全文与 L3 指针

- **GIVEN** 候选经 Validator 判定未过门，且记忆后端已注入
- **WHEN** `run_cycle` 走 rejected 分支
- **THEN** 可 `get` 到 L2 `evolution.gate_rejected.<candidate_id>`（内容含 issue 与 review）
  与 L3 `evolution.gate_rejected.l3.<candidate_id>`（内容含对 L2 id 的引用，且**不等于**
  L2 全文）；outcome 仍为 `rejected`

#### Scenario: 超长 issue 在 L2 被截断

- **GIVEN** 候选 `delta.issue` 长度超过实现上界（400 字符），且记忆后端已注入
- **WHEN** rejected 写回
- **THEN** L2 content 中的 issue 片段长度不超过上界；L3 仍为短指针、不含完整超长 issue

#### Scenario: 未注入记忆时零写不抛

- **GIVEN** 候选未过门，且记忆后端未注入
- **WHEN** `run_cycle` 走 rejected 分支
- **THEN** 不写盘、不抛错，outcome 仍为 `rejected`

#### Scenario: 与人工拒绝条目并存

- **GIVEN** 同一候选先因门禁拒绝写回 `gate_rejected*`，再经人工 `reject(reason=...)`
- **WHEN** 查询记忆
- **THEN** `evolution.gate_rejected*` 与 `evolution.rejected.<candidate_id>` 均可 get、互不覆盖
