# Plugin Registry Specification

## Purpose
插件注册表实现"插件即原子"的生命周期管理：来源获取、安装、注册、版本、依赖、卸载，并隔离恶意插件，是结晶经济闭环的原子载体。

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

#### Scenario: 并发热插拔原子性
- **GIVEN** 多个注册/卸载/启停请求并发到达
- **WHEN** 热插拔执行
- **THEN** 每个操作原子完成，集合视图保持一致，不出现半注册/半卸载的中间态

#### Scenario: 注册超时
- **GIVEN** 插件注册过程卡死或耗时超过上限
- **WHEN** 注册超时
- **THEN** 终止注册并回滚已加载的副作用，返回 `REGISTER_TIMEOUT`，不阻塞注册表

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

### Requirement: 插件安装持久化
系统的插件安装 SHALL **跨进程持久化**：经 CLI `plugin install` 或 `install` 工具安装的**非 mcp 类**资产（skill / cli），其安装记录 SHALL 落 `$CORE_STATE_DIR/plugin-installs.json`——单文件 JSON、**原子写**（先写同目录临时文件再 `os.replace`）、**状态非配置**（由安装动作写入，SHALL NOT 进 `ConfigSpec`）。**mcp 类 SHALL NOT 在本账本二次记账**：其持久化真源为 `mcp-endpoints.json`（见 mcp「MCP Server 安装与移除」），本账本 SHALL 按 `kind` 路由到该真源，二者合并构成「已安装」的**单一视图**，`SHALL NOT` 出现同一资产两处记账。

组合根 SHALL 在**装配期**读回账本并经**同一安装管线**重建物化（skill → 技能库注册；cli → 工具面注册），使「已安装」与运行时可见一致；**单条记录重建失败 SHALL 降级为告警并跳过，SHALL NOT 阻断装配**。账本文件损坏或条目残缺 SHALL 同样降级告警（不静默丢弃、不阻断启动）。

清单与卸载 SHALL 以上述单一视图为真源：`list` SHALL 返回账本与端点注册表的**合并视图**；`uninstall` SHALL 按键定位资产并**对称回退**物化（技能移除 / 工具摘除 / 端点连接释放），随后清除账本条目；键不存在 SHALL 返回 `UNINSTALL_NOT_FOUND` 且不做副作用。重复安装同一 `plugin_id` SHALL **覆盖**既有条目（重装即升级），SHALL NOT 因重名拒绝。

#### Scenario: 安装记录跨进程可见
- **GIVEN** 一个经 CLI `plugin install --kind cli` 安装成功的资产
- **WHEN** 由**另一个进程**执行 `plugin list`
- **THEN** 该资产被列出（读自落盘账本，而非进程内内存）

#### Scenario: 装配期重建物化
- **GIVEN** 账本中存在一条 cli 类安装记录
- **WHEN** 组合根装配运行时
- **THEN** 该 cli 工具经同一安装管线重新注册进生产工具面（重启后仍可达）

#### Scenario: mcp 类委派端点注册表
- **GIVEN** 一个 mcp 类插件的安装
- **WHEN** 持久化
- **THEN** 记录落 `mcp-endpoints.json`（与 `mcp add` 同一真源），`plugin-installs.json` **不含**该条目；`list` 仍合并显示该端点

#### Scenario: 卸载经账本对称回退
- **GIVEN** 账本中一个已安装插件
- **WHEN** 在**新进程**中执行 `plugin uninstall <plugin_id>`
- **THEN** 其物化副作用被对称回退（技能移除 / 工具摘除 / 端点连接释放），且账本条目被清除

#### Scenario: 未安装卸载
- **GIVEN** 一个不在账本与端点注册表中的键
- **WHEN** 发起卸载
- **THEN** 返回 `UNINSTALL_NOT_FOUND`，不做副作用

#### Scenario: 账本损坏或条目残缺降级
- **GIVEN** `plugin-installs.json` 内容非法，或其中某条目缺少 `plugin_id` / `kind`
- **WHEN** 读取账本
- **THEN** 告警并跳过该文件或该条目，其余有效条目仍可用，不阻断启动

#### Scenario: 重建失败不阻断装配
- **GIVEN** 账本中一条记录指向不可用资产（来源或 manifest 非法）
- **WHEN** 装配期重建该条
- **THEN** 告警并跳过该条，其余记录正常重建，装配继续
