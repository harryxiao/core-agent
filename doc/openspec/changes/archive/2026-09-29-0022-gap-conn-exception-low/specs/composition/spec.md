Composition 环检测与冲突兜底：bundle 依赖图检测循环引用并拒绝加载，patch.yml 覆盖冲突按确定优先级裁决、歧义回退，避免死循环与静默吞掉冲突。（来源：架构查漏补缺探索结论，2026-09-22）

## MODIFIED Requirements

### Requirement: bundle 分发格式
系统 SHALL 定义 bundle 作为插件的分发格式，使已结晶的技能可打包、跨部署复用。

#### Scenario: 跨部署复用
- **GIVEN** 某部署结晶出一批技能
- **WHEN** 将技能打包为 bundle
- **THEN** 其他部署可引入该 bundle 复用同一批技能，无需重新结晶

#### Scenario: bundle 校验失败
- **GIVEN** 引入的 bundle 校验和或签名不符、或格式损坏
- **WHEN** 部署引入该 bundle
- **THEN** 拒绝加载并报错定位损坏 bundle，不影响已有组合，可回退到引入前状态

#### Scenario: 循环依赖检测
- **GIVEN** 多个 bundle 间声明引用形成循环依赖
- **WHEN** 解析 bundle 依赖图
- **THEN** 检测到环则拒绝加载并报错指出环路径，不进入死循环，已有组合不受影响

### Requirement: patch.yml 用户覆盖
系统 SHALL 支持用户 patch.yml 对 profile 组合做局部覆盖，在不改 profile 与 bundle 的前提下按用户差异调整。

#### Scenario: 用户差异覆盖
- **GIVEN** 用户对某 profile 有局部差异需求
- **WHEN** 提供 patch.yml 声明覆盖项
- **THEN** 系统在 profile 组合结果上应用覆盖，原 profile 与 bundle 保持不变

#### Scenario: 覆盖冲突兜底
- **GIVEN** patch.yml 覆盖项与 profile/bundle 既有项冲突或产生歧义
- **WHEN** 解析覆盖无法唯一判定生效项
- **THEN** 按确定优先级裁决（显式 patch 覆盖优先于默认层叠），仍歧义则报错并回退到覆盖前状态，不静默吞掉冲突
