# mcp spec delta — mcp-default-exposure-narrowing（change 0076 / 账本 B7）

**默认暴露面从「无 write 副作用」收紧为「只读且无跨边界能力」。**

规格场景「默认最小暴露」已写「写/删除/**敏感**工具默认不暴露」，而 `_is_readonly`
（coeffects 不含 `write`）把「敏感」漏掉 ⇒ 驱动子 loop 的 `tools.delegate`（coeffects 为空）
与有网络出站的 `tools.web_fetch`（`network:outbound`）**默认即在暴露面内**（账本 B7）。
本 delta 把「敏感」的口径写实：**声明的 coeffect 集合须为纯本地只读**。

## MODIFIED Requirements

### Requirement: 工具暴露与白名单
系统 SHALL 通过白名单控制对外暴露的工具集合，默认最小暴露，命名空间隔离。**默认最小暴露** SHALL 判为：工具**声明的 coeffect 集合为纯本地只读**（如 `⊆ {"filesystem:read"}`；**未声明任何 coeffect 视为只读**）—— 凡含**写**（`filesystem:write`）、**进程派生**（`process:spawn`）、**网络出站**（`network:outbound`）、**委托驱动**（`agent:delegate`）等**跨边界** coeffect 者 SHALL NOT 默认暴露。**对外工具名 SHALL 带 `core.` 命名空间前缀**（`core.<tool_id>`），与本地工具名及 client 侧 `mcp.*` 远程工具名天然隔离；`call_tool` SHALL ONLY 接受**已暴露**的名字，未暴露者 SHALL 返回 `PERMISSION_DENIED` 且**不执行**；SHALL NOT 把 client 侧已发现的远程工具（`mcp.*`）再对外暴露（**禁止二级代理**，防止相互挂载递归）。白名单 SHALL 可经 `mcp serve --whitelist`（逗号分隔工具名）显式声明。

#### Scenario: 默认最小暴露
- **GIVEN** 未配置白名单
- **WHEN** server 启动
- **THEN** 仅暴露只读类工具（coeffect 集合为纯本地只读，含未声明 coeffect 者），写 / 删除 / 敏感工具默认不暴露

#### Scenario: 默认面排除跨边界工具
- **GIVEN** 未配置白名单，工具源含 `tools.delegate`（委托驱动，coeffect `agent:delegate`）与 `tools.web_fetch`（网络出站，coeffect `network:outbound`）
- **WHEN** 外部客户端执行 `tools/list`
- **THEN** 二者**均不出现**在暴露面内（跨边界能力默认不出），而 `tools.file_read`（`filesystem:read`）与 `tools.list`（未声明 coeffect）**仍出现**

#### Scenario: 白名单显式开放
- **GIVEN** 配置了白名单
- **WHEN** server 启动
- **THEN** 仅暴露白名单内的工具，其余不可见

#### Scenario: 工具命名空间隔离
- **GIVEN** 本地存在工具 `tools.file_read`
- **WHEN** 外部客户端执行 `tools/list`
- **THEN** 暴露名为 `core.tools.file_read`（前缀隔离），`tools/call` 以该名调用即转发到本地 `tools.file_read`

#### Scenario: 远程工具不被二级代理暴露
- **GIVEN** 本进程作为 client 已发现远程工具（`mcp.<server>.<tool>`）
- **WHEN** 外部客户端执行 `tools/list`
- **THEN** 该远程工具**不出现**在暴露面内（禁止二级代理）
