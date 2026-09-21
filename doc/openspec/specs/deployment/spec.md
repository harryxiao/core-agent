# Deployment Specification

## Purpose

Deployment（部署与托管层）让 Core-Agent 具备可落地的运行环境与发布能力：描述运行环境抽象（进程/容器，不锁定具体选型）、自托管优先的运行形态、可选云托管 BYOC、发布与升级、健康检查与生命周期管理。它与 Composition（决定「装什么」——bundle 打包分发）和 Distributed（决定「和谁协作」——跨设备拓扑）正交：Deployment 只回答「跑在哪、怎么跑、怎么升级」。

## Requirements

### Requirement: 自托管运行环境
系统 SHALL 支持自托管优先的运行环境：以抽象的运行环境概念（进程级或容器级，不锁定具体选型）承载 Core-Agent 及其子模块，提供环境配置、依赖装配与启动引导能力，使一套部署可在个人 PC、服务器、边缘设备上运行。

#### Scenario: 本地自托管启动
- **GIVEN** 一台已安装 Core-Agent 与依赖的宿主机
- **WHEN** 执行启动引导
- **THEN** Core-Agent 以自托管运行环境形态启动并对外提供服务，环境配置从声明式配置读取

#### Scenario: 环境配置可移植
- **GIVEN** 一套 Core-Agent 环境配置
- **WHEN** 迁移到另一台宿主机（PC / 服务器 / 边缘设备）
- **THEN** 复用同一环境配置即可完成装配与启动，无需修改业务逻辑

### Requirement: 可选云托管 BYOC
系统 SHALL 支持可选的云托管 BYOC（Bring Your Own Cloud）：允许用户将 Core-Agent 部署到自己选择的云平台，云托管形态与自托管形态共享同一套部署抽象与配置，不强制绑定特定云厂商。

#### Scenario: 迁移至用户自有云
- **GIVEN** 一套已在本地自托管运行的 Core-Agent
- **WHEN** 用户选择部署到自己的云平台（BYOC）
- **THEN** 复用同一环境配置与部署抽象即可在云平台运行，自托管与云托管行为一致

### Requirement: 发布与升级
系统 SHALL 提供发布与升级能力：支持版本化发布、滚动升级与回滚，升级失败时回到上一个可用版本，保证运行环境不处于半升级状态。

#### Scenario: 版本升级与回滚
- **GIVEN** 运行中的 Core-Agent 旧版本
- **WHEN** 发布新版本并执行升级
- **THEN** 完成滚动升级；升级失败时自动回滚到旧版本，服务不中断或可快速恢复

### Requirement: 健康检查与生命周期
系统 SHALL 提供健康检查与生命周期管理：暴露健康探活端点，支持启动、停止、重启等生命周期操作，异常时可通过探活及时发现并触发恢复。

#### Scenario: 健康探活与恢复
- **GIVEN** 运行中的 Core-Agent 实例
- **WHEN** 探活请求发现实例异常或不可用
- **THEN** 触发告警或自动恢复，生命周期操作（启动/停止/重启）可正常执行
