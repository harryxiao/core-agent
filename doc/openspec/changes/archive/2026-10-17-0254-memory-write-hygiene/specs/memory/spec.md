## ADDED Requirements

### Requirement: 关键事实空值拒收

关键事实落库前的脱敏/清洗边界 SHALL 丢弃 `entity` 或 `value` 在 `strip()` 后为空串的条目。
该判据 SHALL 先于引用式判定执行：即便给出形如 `coeffect:<名称>` 的 `ref`，空 `value` 亦 SHALL
丢弃。被丢弃条目 SHALL NOT 产生 `keyfact.*` 写入，SHALL NOT 覆盖同实体既有条目（既有条目正文
逐字不变）。非空条目的既有脱敏、引用式取值、长度上界与同实体幂等覆盖语义 SHALL 逐字不变。

#### Scenario: 空取值不落库
- **GIVEN** 抽取器返回一条实体非空、取值为空白（或空串）的关键事实
- **WHEN** 压实抽取落库
- **THEN** 不产出该实体的 `keyfact.*` 条目；同批其余合规事实照常落库

#### Scenario: 空取值不覆盖既有事实
- **GIVEN** 某实体已有一条非空取值的既有关键事实
- **WHEN** 后续抽取返回同实体但取值为空白的条目
- **THEN** 既有条目正文与标签**逐字不变**（空值不构成一次有效更新）
