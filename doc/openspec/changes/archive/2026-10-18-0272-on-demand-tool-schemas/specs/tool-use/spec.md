# tool-use — 工具参数查询（change 0272）

## ADDED Requirements

### Requirement: 工具参数查询
系统 SHALL 提供只读原子工具 `tools.schema_read`，用于在**参数 schema 未随请求注入**时按需
查询工具参数（注入范围见 loop「工具参数按需注入」）：

- 参数：可选 `tool_ids`（字符串数组）。
- 缺省 / 空数组：SHALL 返回全部已注册工具的 `tool_id` 与 `description` 列表。
- 给定 id：SHALL 返回每个已注册 id 的 `tool_id`、`description` 与参数 schema（`parameters`）；
  未注册 id SHALL 记入 `unknown` 列表返回，SHALL NOT 抛错或中断本轮。
- 契约：`coeffects=["schema:read"]`（组合根注册该 coeffect）、`reversible=True`；权限分级
  SHALL 为只读（`read` 词元命中）⇒ 默认放行，不经确认门。
- 本工具 SHALL **只挂主工具面**：子 Agent / 神兽 / 宠物 loop SHALL NOT 注册（其工具面不超过
  按需注入阈值，无需加载）。

#### Scenario: 无参列出全部工具
- **GIVEN** 工具面已注册若干工具（含 `tools.schema_read` 自身）
- **WHEN** 模型调用 `tools.schema_read` 且不带参数
- **THEN** 返回全部已注册工具的 id 与描述，不含参数 schema

#### Scenario: 按 id 返回参数 schema
- **GIVEN** 工具面已注册 `tools.process`
- **WHEN** 模型调用 `tools.schema_read` 并请求 `["tools.process"]`
- **THEN** 返回该工具的描述与完整参数 schema；未知 id 记入 `unknown` 且不阻断

#### Scenario: 只读放行
- **GIVEN** 权限引擎对动作做风险分级
- **WHEN** 动作工具为 `tools.schema_read`
- **THEN** 判为只读、默认放行（不经人工确认）
