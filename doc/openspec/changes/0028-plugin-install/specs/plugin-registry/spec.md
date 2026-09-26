# Plugin Registry Specification

## Purpose
插件注册表实现"插件即原子"的生命周期管理：来源获取、安装、注册、版本、依赖、卸载，并隔离恶意插件，是结晶经济闭环的原子载体。

## ADDED Requirements

### Requirement: 插件来源与安装
系统 SHALL 支持从四类来源（local-path / git-repo / market-registry / mcp-endpoint）安装插件，并统一其生命周期：discover → verify（签名校验）→ install → register → activate → deactivate → uninstall；skillhub 的签名校验 / 多源路由语义上提到此统一层复用。

#### Scenario: 四类来源安装
- **GIVEN** 一个插件来自 local-path / git-repo / market-registry / mcp-endpoint 任一来源
- **WHEN** 发起安装
- **THEN** 系统按该来源发现并安装插件，进入注册表统一生命周期

#### Scenario: 签名校验失败拒绝
- **GIVEN** 一个插件包签名无效或缺失
- **WHEN** 安装前校验签名
- **THEN** 返回 `SIGNATURE_INVALID`，拒绝安装

#### Scenario: 来源不可达
- **GIVEN** 插件来源（路径/仓库/市场/MCP 端点）不可访问
- **WHEN** 发起安装
- **THEN** 返回 `SOURCE_NOT_FOUND`，拒绝安装

#### Scenario: 安装失败回滚
- **GIVEN** 插件安装过程中出错
- **WHEN** 安装失败
- **THEN** 返回 `INSTALL_FAILED`，回滚已产生的副作用，不残留半安装状态

#### Scenario: 卸载释放
- **GIVEN** 一个已安装插件
- **WHEN** 卸载
- **THEN** 其工具/技能移除，连接与资源释放，无悬空引用
