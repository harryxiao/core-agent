# Configuration Specification

## Purpose

配置管理（configuration）能力提供统一的配置源、功能开关与密钥分级：以 config.yaml 为单一收口，CLI 覆盖 + env 覆盖 + 默认值兜底（优先级链 CLI flag > env > config.yaml > 默认值），配置项以 ConfigSpec 为单一真源（每项声明 cli_flag/env_var/default/map_to，暴露面 core/advanced/hidden 分级），模块级 feature flag 开关，LLM 配置为必选项（缺失阻断启动），IM 凭证与敏感密钥经 env/keychain 分级存储，schema 校验 + 变更即生效 + 失败回滚不留半写状态，作为 llm-provider / ui / im / git 配置语义的上层挂载能力（来源：exploration_findings.md，2026-09-25）。

## MODIFIED Requirements

### Requirement: 配置源与分层
系统 SHALL 以 config.yaml 为单一配置收口，支持 env 环境变量与 CLI 启动参数覆盖 yaml 值，未配置项取默认值兜底；优先级链为 CLI flag > env > config.yaml > 默认值。配置项以 ConfigSpec 为单一真源：每项声明 cli_flag / env_var / default / map_to 与暴露面分级（core/advanced/hidden），CLI flag / env / yaml 三面由 ConfigSpec 生成，非法 map_to 阻断启动。

#### Scenario: env 覆盖 yaml
- **GIVEN** config.yaml 与 env 环境变量同时定义了同一配置项
- **WHEN** 系统加载配置
- **THEN** env 值覆盖 yaml 值，且不影响其他配置项

#### Scenario: 缺省取默认值
- **GIVEN** 某可选配置项在 yaml 与 env 中均未定义
- **WHEN** 系统加载配置
- **THEN** 该配置项取内置默认值，系统正常启动

#### Scenario: CLI 覆盖 env 与 yaml
- **GIVEN** 同一配置项在 CLI flag、env 环境变量与 config.yaml 中均有定义
- **WHEN** 系统加载配置
- **THEN** CLI flag 值最高优先，覆盖 env 与 yaml 值，且不影响其他配置项

#### Scenario: 三面由 ConfigSpec 单一真源生成
- **GIVEN** 一个配置项已通过 ConfigSpec 声明 cli_flag / env_var / map_to
- **WHEN** 生成 CLI 参数面 / env 变量面 / yaml schema
- **THEN** 三面一一对应、无第二真源

#### Scenario: 非法 map_to 阻断启动
- **GIVEN** ConfigSpec 中某配置项 map_to 非法（目标不存在或冲突）
- **WHEN** 启动时校验 ConfigSpec
- **THEN** 阻断启动并报明确错误

#### Scenario: 暴露面分级
- **GIVEN** 配置项标注了暴露面分级（core/advanced/hidden）
- **WHEN** 生成 CLI 帮助与参数面
- **THEN** 按分级暴露，hidden 项不出现于默认帮助
