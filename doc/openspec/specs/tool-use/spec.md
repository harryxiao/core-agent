# Tool Use Specification

## Purpose
工具使用把模型动作转化为带 schema 的可执行调用，通过 coeffect 约束注入副作用契约，是"插件即原子"的运行时侧实现。

## Requirements

### Requirement: 工具定义与注册
系统 SHALL 用 schema 定义工具，并在启动时校验注册，非法定义拒绝载入。

#### Scenario: schema 合法注册
- **GIVEN** 一个 schema 合法的工具定义
- **WHEN** 启动时注册
- **THEN** 工具进入可调用集合

#### Scenario: schema 非法拒绝
- **GIVEN** 一个 schema 非法的工具定义
- **WHEN** 启动时注册
- **THEN** 返回 `INVALID_TOOL_SCHEMA` 且不载入

### Requirement: 参数校验
系统 SHALL 在调用前按 schema 校验参数，缺参/错型直接拒绝。

#### Scenario: 参数缺失拒绝
- **GIVEN** 一个工具调用缺少必需参数
- **WHEN** 执行前校验
- **THEN** 调用被拒绝并返回结构化错误

### Requirement: coeffect 副作用契约
系统 SHALL 用 coeffect 声明工具副作用类型（read-only/write/secret/external），执行前由权限引擎校验。

#### Scenario: 副作用校验
- **GIVEN** 一个声明为 `secret` 的工具
- **WHEN** 调用该工具
- **THEN** 权限引擎按 secret 规则校验，未授权则拒绝

#### Scenario: 声明与行为不符告警
- **GIVEN** 工具实际产生超出 coeffect 声明的副作用
- **WHEN** 遥测观测到偏差
- **THEN** 记录偏差并标记该工具待复核
