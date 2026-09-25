# Configuration Specification

## Purpose

配置管理（configuration）能力提供统一的配置源、功能开关与密钥分级：以 config.yaml 为单一收口，env 覆盖 + 默认值兜底，模块级 feature flag 开关，LLM 配置为必选项（缺失阻断启动），IM 凭证与敏感密钥经 env/keychain 分级存储，schema 校验 + 变更即生效 + 失败回滚不留半写状态，作为 llm-provider / ui / im / git 配置语义的上层挂载能力（来源：exploration_findings.md，2026-09-25）。

## ADDED Requirements

### Requirement: 配置源与分层
系统 SHALL 以 config.yaml 为单一配置收口，支持 env 环境变量覆盖 yaml 值，未配置项取默认值兜底，避免多配置源冲突。

#### Scenario: env 覆盖 yaml
- **GIVEN** config.yaml 与 env 环境变量同时定义了同一配置项
- **WHEN** 系统加载配置
- **THEN** env 值覆盖 yaml 值，且不影响其他配置项

#### Scenario: 缺省取默认值
- **GIVEN** 某可选配置项在 yaml 与 env 中均未定义
- **WHEN** 系统加载配置
- **THEN** 该配置项取内置默认值，系统正常启动

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断启动并报明确错误。

#### Scenario: 缺失 LLM 配置阻断启动
- **GIVEN** config.yaml 缺少 llm 段或 api_key 未解析
- **WHEN** 系统启动加载配置
- **THEN** 启动失败，报明确错误指明缺失的 LLM 配置项

#### Scenario: LLM 配置完整正常启动
- **GIVEN** llm 段包含 provider/model/endpoint/api_key 且 api_key 经 env 引用解析成功
- **WHEN** 系统启动加载配置
- **THEN** 系统正常启动并初始化 LLM 客户端

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。

#### Scenario: 关闭模块不初始化
- **GIVEN** features 段将某模块（如 voice_output）设为 false
- **WHEN** 系统启动
- **THEN** 该模块不加载、不初始化，其依赖资源不占用

#### Scenario: 开启模块正常初始化
- **GIVEN** features 段将某模块设为 true
- **WHEN** 系统启动
- **THEN** 该模块按正常流程初始化

### Requirement: IM 接入配置
系统 SHALL 支持 IM 接入配置（gateway/账户/ID/密钥），其中密钥经 env/keychain 分级存储，不落 yaml 明文。

#### Scenario: IM 凭证经 keychain 存储
- **GIVEN** im 段配置了 gateway/corp_id 与 secret 引用
- **WHEN** 系统加载 IM 接入配置
- **THEN** secret 从 env/keychain 解析，yaml 中仅存 `${VAR}` 引用

#### Scenario: IM 可选不配置
- **GIVEN** 未配置 im 段
- **WHEN** 系统启动
- **THEN** IM 网关不初始化，其余功能不受影响

### Requirement: 密钥分级与安全
系统 SHALL 保证敏感密钥不入 yaml 明文，日志与报错输出对密钥脱敏（对齐 observability）。

#### Scenario: 日志不泄露密钥
- **GIVEN** 配置含 LLM api_key / IM secret 等敏感密钥
- **WHEN** 系统记录日志或抛出配置错误
- **THEN** 密钥值被脱敏（掩码或占位符），不出现明文

#### Scenario: yaml 拒绝明文密钥
- **GIVEN** config.yaml 中直接书写了密钥明文
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并提示改用 env/keychain 引用

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警
