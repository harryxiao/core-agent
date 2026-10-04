# configuration spec delta — config-validation-symmetry

密钥引用的校验口径**对称化**（`im.secret` / `judgment.api_key` 对齐 `llm.api_key`），
并补上「取值受所属能力规格约束的配置项须校验枚举合法性」（`permission.mode`）。
（来源：账本 `phase-19.md` §2 E8 第 3/7 条实测 —— 空 IM secret 静默过校验、权限模式取值无校验，2026-10-04）

## MODIFIED Requirements

### Requirement: 密钥分级与安全
系统 SHALL 保证敏感密钥不入 yaml 明文，日志与报错输出对密钥脱敏（对齐 observability）。所有密钥引用（`llm.api_key` / `im.secret` / `judgment.api_key`）SHALL 在 schema 校验期**同口径**校验：非空且可经 env/keychain 解析，否则校验失败并阻断启动。

- **对称校验**：SHALL NOT 出现「主 LLM 强制非空且可解析、IM / 决策模型密钥放行空值或不可解析引用」的不对称。
- **可选段语义**：段未配置时 SHALL NOT 参与校验（IM 段缺失即不校验 `im.secret`）；决策模型段仅在 `provider` 非空（能力启用）时校验 `judgment.api_key`。

#### Scenario: 日志不泄露密钥
- **GIVEN** 配置含 LLM api_key / IM secret 等敏感密钥
- **WHEN** 系统记录日志或抛出配置错误
- **THEN** 密钥值被脱敏（掩码或占位符），不出现明文

#### Scenario: yaml 拒绝明文密钥
- **GIVEN** config.yaml 中直接书写了密钥明文
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并提示改用 env/keychain 引用

#### Scenario: 空或不可解析的密钥引用被拒
- **GIVEN** IM 段已配置但 secret 为空，或其引用的环境变量 / keychain 条目不存在
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并指明该密钥引用缺失或无法解析，阻断启动

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。取值受所属能力规格约束的配置项（如 `permission.mode` 限于权限规格的 read-only / interactive / auto-approve / high-risk-block 四档）SHALL 在校验期拒绝非法取值，并列出可选值。

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
