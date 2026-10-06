# configuration — spec delta（change 0130）

## MODIFIED Requirements

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。取值受所属能力规格约束的配置项（如 `permission.mode` 限于权限规格的 read-only / interactive / auto-approve / high-risk-block 四档）SHALL 在校验期拒绝非法取值，并列出可选值。**写回 yaml 的变更 SHALL 记录可逆效应**：`write_patch` 落盘前 SHALL 向效应账注册一条撤销（恢复**写盘前的 yaml 原文**），并与内存变更（`apply_change`）记在**同一 trace** 之下——按该 trace 回滚时 SHALL 使**磁盘态与内存态一并回退**，SHALL NOT 只回退其一而留下内存/磁盘不一致。**未知配置段**（顶层段名不在已知段之内——五个结构化段 `llm` / `features` / `im` / `pet` / `judgment`、`ConfigSpec` 声明段、以及寄居 `extra` 但有运行时语义的 `permission`）SHALL **仅告警**：SHALL 产生含该段名的校验告警（指明其被收纳进 `extra` 且未做校验），SHALL NOT 因此阻断启动，SHALL NOT 静默丢弃该段。告警口径 SHALL ONLY 作用于**顶层段名**，不递归校验已知段内部的未知子键；**唯一例外是 `features` 段**——其子键是**模块名**，SHALL 以**组合根维护的已知模块名集合**（经注入提供）校验：子键不在集合内时 SHALL 产生含该子键名的告警（指明疑似拼写错误、模块名拼错将静默不生效），SHALL NOT 因此阻断启动；已知模块名集合**未注入**时 SHALL NOT 校验 `features` 段子键。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警

#### Scenario: 写回可逆：回滚恢复磁盘原文
- **GIVEN** 已加载配置，且 `apply_change` + `write_patch` 已把一个变更同时生效到内存与 config.yaml
- **WHEN** 对该变更所在的 trace 回滚
- **THEN** config.yaml 恢复为**写盘前的原文**（逐字节），内存配置同时回退 ⇒ 磁盘态与内存态**一致**，且 SHALL NOT 留下「内存已回退、磁盘仍是新值」的不一致

#### Scenario: 非法权限模式被拒
- **GIVEN** 配置将 `permission.mode` 设为四档之外的取值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并列出可选的四档取值，阻断启动

#### Scenario: 未知配置段仅告警不阻断
- **GIVEN** config.yaml 含一个已知段之外的顶层段（如拼错的 `llmm:`），且其余配置完整
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该段名**的告警（指明其被收纳进 `extra`、未做校验），该段仍保留在 `extra` 中不丢失

#### Scenario: features 段未知模块名仅告警
- **GIVEN** 已注入已知模块名集合（如 `pet` / `beast` / `evolution`），且 config.yaml 的 `features` 段含一个集合之外的子键（如拼错的 `peet:`）
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该子键名**的告警（指明疑似拼写、模块名拼错将静默不生效）

#### Scenario: 未注入已知模块名时不校验子键
- **GIVEN** 未注入已知模块名集合，且 config.yaml 的 `features` 段含任意自定义子键
- **WHEN** 系统加载并校验配置
- **THEN** 不产生 `features` 子键告警（与既有顶层段名口径一致）
