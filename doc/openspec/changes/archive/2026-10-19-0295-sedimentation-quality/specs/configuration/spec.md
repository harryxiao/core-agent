## ADDED Requirements

### Requirement: 沉淀配置项

系统 SHALL 经 `ConfigSpec` **单一真源**声明以下两项（CLI flag / env / YAML 三面同源）：

| 键 | CLI | env | 缺省 |
|---|---|---|---|
| `notes.candidate_distill` | `--notes-candidate-distill` | `CORE_NOTES_CANDIDATE_DISTILL` | `true` |
| `notes.candidate_auto_promote` | `--notes-candidate-auto-promote` | `CORE_NOTES_CANDIDATE_AUTO_PROMOTE` | `false` |

两项 SHALL 以宽容 bool 归一（与 feature flag 同集：`true/1/yes/on` 为真，其余为假）。
`notes.candidate_distill=false` 时运行时 SHALL **不产候选、零模型调用**（沉淀链路整体关闭）；
`notes.candidate_auto_promote=true` 时候选 `support ≥ 2` 才尝试自动晋升（冲突保留候选）。

`config set notes.<key> <value>` SHALL 可写（`_key_to_patch` 允许 `notes.` 前缀）。

#### Scenario: 缺省值
- **GIVEN** 未配置 `notes` 段
- **WHEN** 运行时读取两项
- **THEN** `candidate_distill == true`、`candidate_auto_promote == false`

#### Scenario: 关闭提炼不产候选
- **GIVEN** `notes.candidate_distill=false`
- **WHEN** 一轮成功写效应任务收尾
- **THEN** 不调用提炼器、候选区无变化

#### Scenario: CLI 写配置
- **GIVEN** 用户执行 `config set notes.candidate_auto_promote true`
- **WHEN** 重新读取配置
- **THEN** 该键为 `true`（env / YAML 同名键按既有优先级覆盖）

#### Scenario: 非法值归一为关
- **GIVEN** `notes.candidate_auto_promote` 被写成任意非真值字符串
- **WHEN** 运行时读取
- **THEN** 视为 `false`（不自动晋升）
