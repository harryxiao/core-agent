插件并发热插拔与注册超时：并发注册/卸载/启停原子执行不串扰，注册超时按上限终止并回滚副作用。（来源：架构查漏补缺探索结论，2026-09-22）

## MODIFIED Requirements

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

#### Scenario: 并发热插拔原子性
- **GIVEN** 多个注册/卸载/启停请求并发到达
- **WHEN** 热插拔执行
- **THEN** 每个操作原子完成，集合视图保持一致，不出现半注册/半卸载的中间态

#### Scenario: 注册超时
- **GIVEN** 插件注册过程卡死或耗时超过上限
- **WHEN** 注册超时
- **THEN** 终止注册并回滚已加载的副作用，返回 `REGISTER_TIMEOUT`，不阻塞注册表
