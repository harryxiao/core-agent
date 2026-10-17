## MODIFIED Requirements

### Requirement: 技能候选内容生成

系统 SHALL 为**技能级**候选提供可选的内容生成接缝：经组合根注入的 writer 工厂
（`skill_content_writer_with(llm) -> writer`，照 SOP writer 先例）把诊断 `issue` 与有界
`failure_notes` 蒸馏为可执行内容（`task_types` / `instructions` / `param_schema`，及可选
`preconditions` / `description`）。内容 SHALL 以纯 dict 写入候选 `delta["content"]`，可
序列化往返。

- **DI 方向**：evolution SHALL NOT import 任何 LLM 抽象；模型调用由组合根提供。
- **失败即无 content**：writer 返回非法 JSON、结构不符、或调用异常时 SHALL 返回空结果；
  Proposer SHALL **不**写入 `content` 键（delta 仍仅含 `issue`），SHALL NOT 抛裸异常。
- **未注入逐字不变**：未注入 writer 时，技能级 delta SHALL 仍仅 `{"issue": ...}`，与既有
  实现逐字一致。
- **plugin 不受影响**：架构级候选 SHALL NOT 经本接缝生成 content。
- **解析容错**：writer SHALL 容忍模型输出包裹在代码围栏或前后杂文中 —— 直接 `json.loads`
  失败时 SHALL 截取**首个 `{` 至末个 `}`** 的片段再解析；仍不可解析 / 非对象 ⇒ 空结果。
- **内容有界**：`instructions` SHALL 不超过 `_MAX_INSTRUCTIONS_CHARS`（4000）、`description`
  不超过 `_MAX_DESCRIPTION_CHARS`（400）、`task_types` 不超过 `_MAX_TASK_TYPES`（16）项且每项
  不超过 `_MAX_TASK_TYPE_CHARS`（80）、`preconditions` 不超过 `_MAX_PRECONDITIONS`（8）项且
  每项不超过 `_MAX_PRECONDITION_CHARS`（200）。writer SHALL 对超界字段**裁剪**（保留可用内容，
  不整条丢弃）；`validate_skill_content` SHALL **拒绝**超界内容（持久化 delta / 外部注入的
  内容不经 writer，不构成信任边界）；`param_schema` 为结构化对象，不做文本截断。
- **有界 prompt**：注入 `failure_notes` 时 SHALL 有界（条数与单条字符上限由实现常量钉死，
  与诊断失败摘要同口径量级）。

#### Scenario: 注入 writer 后技能候选携带 content

- **GIVEN** Proposer 已注入合法 writer，且诊断归因产出 `kind="skill"`
- **WHEN** `propose` 运行且 writer 返回有效内容
- **THEN** 候选 `delta` 含 `issue` 与 `content`（dict，可 asdict 往返），`content` 经校验为有效

#### Scenario: writer 失败不写 content 键

- **GIVEN** Proposer 已注入 writer，但 writer 对本次 prompt 返回空（非法 JSON / 结构不符 / 异常）
- **WHEN** `propose` 运行
- **THEN** 候选 `delta` **仅**含 `issue`，SHALL NOT 含 `content` 键，SHALL NOT 向调用方抛裸异常

#### Scenario: 未注入 writer 逐字不变

- **GIVEN** Proposer 未注入 writer
- **WHEN** 对技能级诊断 `propose`
- **THEN** 候选 `delta` 仍仅 `{"issue": ...}`，与既有实现逐字一致

#### Scenario: 代码围栏包裹的 JSON 仍被解析
- **GIVEN** writer 的模型输出为代码围栏包裹的合法对象（或对象前后带解释文字）
- **WHEN** writer 解析
- **THEN** SHALL 返回有效 `SkillContent`，字段与对象内容一致

#### Scenario: 超长字段被裁剪到上界
- **GIVEN** writer 的模型输出各文本字段均超过上界
- **WHEN** writer 解析
- **THEN** 返回内容的 `instructions` / `description` / `task_types` / `preconditions`
  SHALL 分别不超过对应上界，且内容仍通过 `validate_skill_content`

#### Scenario: 校验拒绝超界内容
- **GIVEN** 一个 `SkillContent`（或 dict）其 `instructions` 超过上界
- **WHEN** 调用 `validate_skill_content`
- **THEN** SHALL 返回 `False`（不信任未经 writer 的内容）
