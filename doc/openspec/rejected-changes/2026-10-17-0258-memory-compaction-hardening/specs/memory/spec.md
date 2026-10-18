# memory — 摘要分层保留（change 0258 提案）

## ADDED Requirements

### Requirement: 摘要分层保留（结论区 / 事实区）

摘要器产出 SHALL 以哨兵标记分两段：结论区 `<conclusions>…</conclusions>` 与事实区
`<facts>…</facts>`；两区 SHALL 各有独立字符预算（`MAX_CONCLUSION_CHARS=800`、
`MAX_FACT_CHARS=1200`），合计 SHALL NOT 超过 `MAX_SUMMARY_CHARS`。既有摘要越界时 SHALL
按区分层 elide（结论区保全文、事实区尾部截断）；仅单区超限时 SHALL 才整段截断。无标记的
摘要（旧摘要 / 模型未按格式返回）SHALL 回退现有整段**首尾保留** elide，行为与现状逐字一致。
滚动合并 prompt SHALL 要求模型输出两段标记，并保留既有结论的轮次序号前缀（`[rN]`）。

#### Scenario: 分层 elide 保结论区
- **GIVEN** 既有摘要带两段标记且结论区与事实区合计越过 `MAX_SUMMARY_CHARS`
- **WHEN** 摘要投喂摘要器
- **THEN** 结论区内容**逐字保留**，事实区按尾部预算截断，总节选长度不超过 `MAX_SUMMARY_CHARS`

#### Scenario: 无标记旧摘要回退
- **GIVEN** 既有摘要不含分层标记（旧数据）
- **WHEN** 摘要越界节选
- **THEN** 回退整段首尾保留 elide，产出与 change `0193` 的现行为逐字一致

#### Scenario: 单区超限整段截断
- **GIVEN** 结论区单独超过其预算
- **WHEN** 分层 elide
- **THEN** 该区整段截断（不侵入事实区预算），总长仍不超过 `MAX_SUMMARY_CHARS`
