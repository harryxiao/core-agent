# Composition Specification

## Purpose

Composition（组合与分发层）是 CORE-Harness 唯一的静态层：只有组合代数、没有业务逻辑、永不进化。它通过 profile（命名组合）/ bundle（分发格式）/ patch.yml（用户覆盖）三要素，把已结晶的技能与插件按需组合、跨部署分发、按用户差异覆盖，实现「一切皆插件 + 可逆组合」的基底（来源：core_harness_architecture.md L5）。

## Requirements

### Requirement: profile 命名组合
系统 SHALL 提供 profile 命名组合机制（如 web / headless / sdk-minimal），一个 profile 命名一个可复用的插件组合集合，层叠多个 bundle 并叠加用户 patch.yml。

#### Scenario: 按名选用组合
- **GIVEN** 系统已定义若干命名 profile
- **WHEN** 用户或部署按名选用某个 profile
- **THEN** 系统按该 profile 声明的组合解析出完整插件集

### Requirement: bundle 分发格式
系统 SHALL 定义 bundle 作为插件的分发格式，使已结晶的技能可打包、跨部署复用。
bundle SHALL 携带**内容哈希**：哈希 SHALL 由该 bundle 的**制品内容**派生，即其插件引用集合的规范形（`plugin_id@generation` 有序逐项以 `|` 连接，取 SHA-256）；**内容相同 ⇒ 哈希相同，内容不同 ⇒ 哈希不同**。系统 SHALL NOT 以版本名 / 制品清单文件名等**元信息**充当内容哈希 —— 元信息不同而内容相同者，哈希 SHALL 相同。
系统 SHALL 提供**发布入口**（CLI `release publish <bundle 制品清单>`）：读制品清单（声明 `plugin_refs` 的文件）并经上述内容哈希口径发布。清单缺失、不可读或非法（含 `plugin_refs` 非列表、引用项缺 `plugin_id` / `generation`）SHALL 以结构化错误拒绝（`BUNDLE_INVALID`）并**保持既有发布记录不变**，SHALL NOT 退化为以元信息哈希照常发布。

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

#### Scenario: 同内容同哈希、异内容异哈希
- **GIVEN** 两份 bundle 制品清单的 `plugin_refs` 逐项一致，而清单文件名（与其声明的 bundle 名）不同
- **WHEN** 分别发布两份清单
- **THEN** 两次发布记录的内容哈希**相同**（哈希由制品内容派生，与元信息无关）；改动任一份的 `plugin_refs`（任一 `generation`）⇒ 该份哈希随之改变

#### Scenario: 制品清单缺失不产假账
- **GIVEN** 指定路径不可读、非法 JSON，或 `plugin_refs` 非法
- **WHEN** 部署执行发布
- **THEN** 结构化拒绝（`BUNDLE_INVALID`），命令以非零退出码报错定位原因，既有发布记录**不变** —— SHALL NOT 退化为「以版本名哈希」照常发布


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


### Requirement: 层叠解析
系统 SHALL 按「bundle 层叠 + patch.yml 覆盖」的确定顺序解析最终组合，解析结果可逆、可回退。
解析结果 SHALL **保留覆盖前（bundle 层叠后）的分层结果**与生效覆盖项；系统 SHALL 提供**回退**：
移除 patch 覆盖、恢复至**覆盖前**的分层结果，回退 SHALL 幂等（对回退结果再回退，结果不变）。
patch 覆盖值 SHALL 为整数 generation；**布尔值**（YAML `true` / `false`）SHALL NOT 被当作 generation
（`bool` 虽为 `int` 子类，SHALL 视为类型非法并按 `PATCH_CONFLICT` 拒绝），SHALL NOT 静默落为 1 / 0。

#### Scenario: 确定顺序解析
- **GIVEN** 一个 profile 层叠多个 bundle 并叠加 patch.yml
- **WHEN** 解析最终组合
- **THEN** 按确定顺序合并，同名项由 patch.yml 覆盖，卸载时可回退到覆盖前状态

#### Scenario: 回退到覆盖前状态
- **GIVEN** 一次解析已应用 patch.yml 覆盖（某插件的 generation 被覆盖）
- **WHEN** 执行回退（移除 patch 覆盖）
- **THEN** 结果回到覆盖前分层结果（被覆盖项恢复为层叠值）、覆盖项清空；**再次回退结果不变**（幂等）

#### Scenario: 布尔覆盖值拒绝
- **GIVEN** patch.yml 的覆盖值为布尔（YAML `true`）
- **WHEN** 解析该 patch
- **THEN** 按 `PATCH_CONFLICT` 拒绝（布尔非 generation），SHALL NOT 静默落为 `1`
