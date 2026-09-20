# LLM Provider Specification

## Purpose

LLM Provider（三方大模型归一化接入）让 core-agent 通过统一 LLMProvider 抽象接口调用任意三方大模型：配置任意模型 API Key 与 URL 即自动路由接入，LiteLLM 作默认实现、经依赖注入隔离可无缝替换或自研，调用方零改动。

## Requirements

### Requirement: LLMProvider 抽象接口
系统 SHALL 提供统一的 LLMProvider 抽象接口（completion / stream / embedding 三个入口与统一请求 / 响应模型），内核只依赖该接口、不感知具体供应商实现。

#### Scenario: 统一接口调用
- **GIVEN** 内核 loop 需要调用大模型
- **WHEN** 经 LLMProvider 接口发起请求
- **THEN** 内核无需关心底层供应商协议，仅面向统一请求 / 响应模型

### Requirement: LiteLLM 默认实现与配置归一化
系统 SHALL 提供 LiteLLM 默认实现，任意三方 API Key + URL 配置即自动路由到对应 provider 协议，无需逐家编写适配代码。

#### Scenario: 任意三方模型接入
- **GIVEN** 用户配置某三方模型的 API Key 与 URL
- **WHEN** 发起模型调用
- **THEN** 系统自动解析并路由到对应 provider 协议，返回归一化结果

### Requirement: 依赖注入可替换
系统 SHALL 通过依赖注入隔离 LLMProvider 实现，替换 LiteLLM 或接入自研后端时，内核 loop 及所有调用方无需改动即可切换。

#### Scenario: 替换底层实现
- **GIVEN** 需要替换 LiteLLM 为自研或其他后端
- **WHEN** 注册新的 Provider 实现
- **THEN** 内核 loop 及所有调用方无需改动即可切换

### Requirement: 错误归一化
系统 SHALL 将超时 / 限流 / 鉴权 / 网络异常统一为领域异常，上层只处理一类错误语义。

#### Scenario: 底层异常归一
- **GIVEN** 底层供应商返回超时 / 限流 / 鉴权等不同错误
- **WHEN** 调用失败
- **THEN** 统一映射为对应领域异常，不泄漏供应商原始错误结构

### Requirement: 模型调用审计
系统 SHALL 对模型调用做可观测审计，标注 provider / model 与调用结果，复用既有 observability 链路。

#### Scenario: 调用留痕
- **GIVEN** 任意一次模型调用
- **WHEN** 调用结束
- **THEN** 审计记录标注 provider / model 与结果，可追溯
