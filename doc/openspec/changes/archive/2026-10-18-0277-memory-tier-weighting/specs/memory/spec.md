# Memory Specification Delta — 内容分区权重（change 0277）

## ADDED Requirements

### Requirement: 内容分区权重（tags 三档）

系统 SHALL 在相关性得分 `relevance` 上叠加一维**内容分区权重**（加法项），按条目 `tags` 判定
三档：`milestone` / `decision` ⇒ **高档**（`tier = +1`）；`log` / `transcript` ⇒ **低档**
（`tier = −1`）；其余（含未知 / 无标签）⇒ **默认档**（`tier = 0`）。权重系数 SHALL 为
`0.15`，即 `relevance = 0.5·sim + 0.2·layer_priority + 0.15·tier`。

默认档 SHALL 取零偏移（而非正常量）：`rank` 是 `relevance × 复用/重要度调制` 的乘性结构，
任何非零默认偏移都会被调制放大——1 万条基准实测默认档 `+0.075` 会使高复用填充项反超
gold，recall@5 由 `1.000` 降至 `0.45`。零偏移使未分档条目得分与分档前**逐位相同**。

- 同一输入下 SHALL 满足：高档 `relevance` > 默认档 > 低档（其余字段相同）。
- 同一条目同时命中高低档 ⇒ SHALL 按**高档**处理；标签匹配 SHALL **精确且区分大小写**
  （约定小写），未知标签 SHALL 落默认档。
- 分区权重 SHALL 为**加性项**，SHALL NOT 改变层优先级与时间 / 复用 / 重要度调制的既有语义；
  默认档偏移为零 ⇒ **未分档条目之间的相对排序 SHALL 逐位不变**（与分档前得分完全相同）。
- 分区权重 SHALL **默认启用**，SHALL NOT 引入配置开关；档位判定 SHALL 只看 `tags`，
  SHALL NOT 从 `source` / `kind` 推断。

#### Scenario: 三档定序
- **GIVEN** 三个条目内容 / 层 / 时间戳 / 复用 / 重要度完全相同，仅 `tags` 分别为
  `["milestone"]`、`["bench"]`、`["log"]`
- **WHEN** 计算 `relevance` 与 `rank`
- **THEN** 高档 > 默认档 > 低档

#### Scenario: 冲突与未知
- **GIVEN** 条目 tags 分别为 `["milestone", "log"]`、`["unknown"]`、`["Milestone"]`
- **WHEN** 计算档位
- **THEN** 依次为高档、默认档、默认档（冲突高档优先；精确小写匹配）

#### Scenario: 同档排序不变
- **GIVEN** 两个未分档条目仅层不同（L2 vs L3），其余字段相同
- **WHEN** 比较 `rank`
- **THEN** L3 仍高于 L2，且两者 `relevance` 与分档前公式逐位相同（默认档零偏移）

#### Scenario: 基准不回退
- **GIVEN** `0261`（26 条排序语义）与 `0275`（1 万条规模）既有基准语料
- **WHEN** 启用分区权重后重跑
- **THEN** recall@5 / MRR@5 阈值仍通过（实测 1.000），且 1 万条检索中位仍 <100ms
