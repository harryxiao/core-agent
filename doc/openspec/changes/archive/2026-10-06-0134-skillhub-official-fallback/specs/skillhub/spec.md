# skillhub — spec delta（change 0134）

## MODIFIED Requirements

### Requirement: 多源路由与健康回退
系统 SHALL 按 source 路由到对应市场源；源不健康时 SHALL **回退官方源并以其结果响应**
（SHALL NOT 因单个非官方源不可达而使查询失败）—— 回退发生 SHALL 把不可达源**标记为不健康**
（`health` 可查）。官方源**亦**不可用（即无可用源）时 SHALL 返回 `SOURCE_UNHEALTHY`。
源不存在时 SHALL 拒绝路由并返回 `SOURCE_NOT_FOUND`，SHALL NOT 回退到未知源。

#### Scenario: 源不可达回退
- **GIVEN** 某个非官方 source 不可达，而官方源健康且有其目录
- **WHEN** MarketIndex 经该 source 列目录 / 路由
- **THEN** 该源被标记为不健康，且**返回官方源的结果**（不抛错）

#### Scenario: 回退目标亦不可用
- **GIVEN** 某个 source 与官方源**均**不可达
- **WHEN** 经该 source 列目录 / 路由
- **THEN** 返回 `SOURCE_UNHEALTHY`（无可用源）

#### Scenario: 官方源自身不可达
- **GIVEN** 官方源不可达（无回退目标）
- **WHEN** 经官方源列目录 / 路由
- **THEN** 返回 `SOURCE_UNHEALTHY`

#### Scenario: 源不存在
- **GIVEN** source 未注册
- **WHEN** 路由到该源
- **THEN** 返回 `SOURCE_NOT_FOUND`，不 fallback 到未知源
