# Plugin Registry Specification Delta

## ADDED Requirements

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
