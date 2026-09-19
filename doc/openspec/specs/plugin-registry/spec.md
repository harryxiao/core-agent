# Plugin Registry Specification

## Purpose
插件注册表实现"插件即原子"的生命周期管理：注册、版本、依赖、卸载，并隔离恶意插件，是结晶经济闭环的原子载体。

## Requirements

### Requirement: 插件注册与生命周期
系统 SHALL 管理插件的注册、启用、禁用、卸载全生命周期。

#### Scenario: 注册并校验
- **GIVEN** 一个插件包
- **WHEN** 注册
- **THEN** 校验 manifest（版本/依赖/入口），非法则返回 `INVALID_MANIFEST`

#### Scenario: 卸载干净
- **GIVEN** 一个已注册插件
- **WHEN** 卸载
- **THEN** 其工具/技能从集合移除，无悬空引用

### Requirement: 依赖解析
系统 SHALL 解析插件依赖并检测循环依赖。

#### Scenario: 依赖满足
- **GIVEN** 插件 A 依赖 B
- **WHEN** 加载 A
- **THEN** 先加载 B 并校验版本约束

#### Scenario: 循环依赖检测
- **GIVEN** A 依赖 B 且 B 依赖 A
- **WHEN** 注册解析
- **THEN** 返回 `CIRCULAR_DEPENDENCY`，拒绝加载

### Requirement: 隔离与安全
系统 SHALL 隔离插件运行边界，限制其可访问能力，异常不污染核心。

#### Scenario: 能力边界限制
- **GIVEN** 一个插件请求超出其声明权限的能力
- **WHEN** 运行时检查
- **THEN** 请求被拒绝并记录

#### Scenario: 插件崩溃隔离
- **GIVEN** 插件运行时 panic
- **WHEN** 异常抛出
- **THEN** 异常被捕获隔离，主循环继续，插件标记故障
