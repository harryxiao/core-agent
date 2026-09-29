# Configuration Specification Delta

## ADDED Requirements

### Requirement: 决策模型配置
系统 SHALL 将决策模型（judgment）接入配置纳入 ConfigSpec 单一真源：judgment.provider / judgment.model / judgment.base_url / judgment.api_key / judgment.confidence_threshold；api_key 经 env/keychain 分级存储不落 yaml 明文，未配置时决策能力关闭、主 LLM 兜底。

#### Scenario: 决策模型配置经 ConfigSpec 声明
- **GIVEN** 配置了 judgment 段的 provider/model/base_url/api_key/confidence_threshold
- **WHEN** 系统启动加载配置
- **THEN** 配置经 ConfigSpec 单一真源解析（优先级链 CLI flag > env > config.yaml > 默认值），暴露面 core/hidden 分级

#### Scenario: 决策模型密钥不入 yaml 明文
- **GIVEN** judgment.api_key 为敏感密钥
- **WHEN** 系统做 schema 校验
- **THEN** api_key 必须为 `${VAR}` 引用，yaml 明文被拒绝

#### Scenario: 未配置决策模型回退主 LLM
- **GIVEN** 未配置 judgment 段或 provider 为空
- **WHEN** 系统需要决策
- **THEN** 决策能力关闭，回退主 LLM 兜底
