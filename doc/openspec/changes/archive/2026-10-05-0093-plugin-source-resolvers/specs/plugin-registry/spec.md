# Plugin Registry Specification Delta

## MODIFIED Requirements

### Requirement: 插件来源与安装
系统 SHALL 支持从四类来源（local-path / git-repo / market-registry / mcp-endpoint）安装插件，并统一其生命周期：discover → verify（签名校验）→ install → register → activate → deactivate → uninstall；skillhub 的签名校验 / 多源路由语义上提到此统一层复用。

四类来源的**发现（discover）** SHALL 由执行层的来源解析器承担，SHALL NOT 引入第三方运行时依赖：local-path 读 `location` 所指本地 manifest 文件；git-repo 克隆 `location` 所指仓库到**临时工作区**、读其**根目录** `core-plugin.json`，且 SHALL 在读取完成后清理该临时工作区（不残留）；market-registry 取 `location` 所指 manifest 文档，鉴权凭据 SHALL 由注入的 fetcher 携带、SHALL NOT 写进 URL；mcp-endpoint 由端点串合成 manifest（**解析期零网络**，端点可达性在 install 期判定）。来源不可达 / manifest 非法 SHALL 归一为 `SOURCE_NOT_FOUND`，错误信息 SHALL NOT 回显 URL 的 userinfo 与 query（可能含凭据）。

#### Scenario: 四类来源安装
- **GIVEN** 一个插件来自 local-path / git-repo / market-registry / mcp-endpoint 任一来源
- **WHEN** 发起安装
- **THEN** 系统按该来源发现并安装插件，进入注册表统一生命周期

#### Scenario: git-repo 来源克隆解析与临时工作区清理
- **GIVEN** 一个 git 仓库，根目录含 `core-plugin.json`
- **WHEN** 以 git-repo 来源发现插件
- **THEN** 系统克隆该仓库、读取根目录 manifest 作为资产 manifest，且临时工作区在解析后被清理（不留残留）

#### Scenario: market-registry 来源经注入 fetcher 取 manifest
- **GIVEN** 一个市场注册表地址，配以注入的 fetcher（真实拉取依赖网络与市场凭据）
- **WHEN** 以 market-registry 来源发现插件
- **THEN** 系统经该 fetcher 取得 manifest 文档作为资产 manifest；fetcher 失败 SHALL 归一为 `SOURCE_NOT_FOUND`

#### Scenario: mcp-endpoint 来源解析期零网络
- **GIVEN** 一个 MCP 端点串
- **WHEN** 以 mcp-endpoint 来源发现插件
- **THEN** 系统由该端点串**合成** manifest（含端点名与端点地址），解析期不发起任何网络连接；端点不可达由 install 期判定

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

#### Scenario: 卸载未安装插件
- **GIVEN** 一个未安装（或已卸载）的插件
- **WHEN** 发起卸载
- **THEN** 返回 `UNINSTALL_NOT_FOUND`，不做副作用
