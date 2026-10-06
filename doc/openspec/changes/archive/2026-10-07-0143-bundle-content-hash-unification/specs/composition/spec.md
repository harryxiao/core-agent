## MODIFIED Requirements

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
