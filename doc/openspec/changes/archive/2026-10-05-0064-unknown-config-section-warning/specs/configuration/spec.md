# configuration spec delta — unknown-config-section-warning

**把「未知配置段」从静默吞入改为仅告警**：`AppConfig.extra` 收纳「五个结构化段之外的一切」
（`llm`/`features`/`im`/`pet`/`judgment`），故拼错的段名（如 `llmm:`）被**静默**吞进 `extra`
——既没报「未知配置键」，也没提示拼错，用户只会看到「LLM 配置缺失」（E8 第 5 条转出为账本 E18）。

**用户裁决：仅告警（WARN 不阻断）** —— 收紧为白名单硬拒会**拒绝既有自定义段**
（改变既有接受行为），与 `extra` 的宽松契约冲突；而完全静默又让拼写错误无处暴露。

## MODIFIED Requirements

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。取值受所属能力规格约束的配置项（如 `permission.mode` 限于权限规格的 read-only / interactive / auto-approve / high-risk-block 四档）SHALL 在校验期拒绝非法取值，并列出可选值。**未知配置段**（顶层段名不在已知段之内——五个结构化段 `llm` / `features` / `im` / `pet` / `judgment`、`ConfigSpec` 声明段、以及寄居 `extra` 但有运行时语义的 `permission`）SHALL **仅告警**：SHALL 产生含该段名的校验告警（指明其被收纳进 `extra` 且未做校验），SHALL NOT 因此阻断启动，SHALL NOT 静默丢弃该段。告警口径 SHALL ONLY 作用于**顶层段名**，不递归校验已知段内部的未知子键。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警

#### Scenario: 非法权限模式被拒
- **GIVEN** 配置将 `permission.mode` 设为四档之外的取值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并列出可选的四档取值，阻断启动

#### Scenario: 未知配置段仅告警不阻断
- **GIVEN** config.yaml 含一个已知段之外的顶层段（如拼错的 `llmm:`），且其余配置完整
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该段名**的告警（指明其被收纳进 `extra`、未做校验），该段仍保留在 `extra` 中不丢失
