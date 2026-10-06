## MODIFIED Requirements

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
