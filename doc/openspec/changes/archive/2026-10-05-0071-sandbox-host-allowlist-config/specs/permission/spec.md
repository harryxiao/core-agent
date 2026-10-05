# permission spec delta — sandbox-host-allowlist-config

**把出站网络白名单从「构造面可注入、生产恒空」变成「可经配置声明」。**
`SandboxPolicy(host_allowlist=...)` 早已可注入（`doc/03-interfaces/permission-interface.md` §4），
但唯一生产构造点 `runtime.py:363` 此前**不传参** ⇒ 白名单**恒为空**、一切 http 出站被拒；
配置面（yaml / env / CLI）无对应键 ⇒ 规格场景「网络出站白名单」的**放行半边在生产不可达**
（账本 B5，与 E15 同型）。

## MODIFIED Requirements

### Requirement: 沙箱执行颗粒度
系统 SHALL 将沙箱按执行域（终端/浏览器/文件系统）隔离，并对网络与资源施加白名单与配额约束。
网络的**出站主机白名单** SHALL **可经配置声明**：键为 `permission.sandbox.host_allowlist`，
取值为**逗号分隔的主机名标量**（本仓 yaml 子集解析器不含列表，故三面统一为标量），
经 `ConfigSpec` **单一真源**解析（优先级 CLI flag > env > config.yaml > 缺省），
并据此装配组合根的 `SandboxPolicy`（客户端与沙箱管理器**共用同一策略实例**）。
缺省（未声明）SHALL 为空白名单 ⇒ **fail-closed 全拒出站**。
条目 SHALL 为**裸主机名**：带 scheme / 端口 / 路径 / 内部空白的条目**永不匹配**
（`check_outbound` 的实参是 `urlparse(url).hostname`），故**非法条目 SHALL 在校验期被拒绝
并阻断启动**（不得静默兜底为忽略该条目）。

#### Scenario: 三域隔离
- **GIVEN** 一个任务同时需要终端、浏览器、文件系统三类操作
- **WHEN** 沙箱管理器分配执行环境
- **THEN** 三类操作在互相隔离的域中执行，域间数据流经显式通道，不共享宿主资源

#### Scenario: 网络出站白名单
- **GIVEN** 沙箱内的代码或浏览器发起出站网络请求
- **WHEN** 目标不在白名单内
- **THEN** 请求被拦截并记录，不降级放行

#### Scenario: 出站白名单经配置声明
- **GIVEN** 配置将 `permission.sandbox.host_allowlist` 设为 `a.example.com,b.example.com`
- **WHEN** 系统启动装配并按该配置构造 `SandboxPolicy`
- **THEN** 出站到 `a.example.com` / `b.example.com` 放行，出站到其他主机被拦截
- **AND** 同一取值经 CLI flag / env / config.yaml 任一面设置均生效，优先级链一致

#### Scenario: 未配置出站白名单全拒
- **GIVEN** 配置未声明 `permission.sandbox.host_allowlist`
- **WHEN** 发生任何 http 出站
- **THEN** 目标一律被拦截（fail-closed 安全默认，不因新增配置项而松动）

#### Scenario: 非法白名单条目校验期拒绝
- **GIVEN** 白名单条目带 scheme（`https://a.example.com`）、端口（`a.example.com:443`）、
  路径（`a.example.com/v1`）或内部空白
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值形态
  （不静默忽略该条目 —— 静默的后果是「配了却连不上」）

#### Scenario: 资源配额超限
- **GIVEN** 沙箱内进程超出 CPU/内存/磁盘配额
- **WHEN** 资源监控检测到超限
- **THEN** 进程被终止，沙箱整体回收，返回 `QUOTA_EXCEEDED`

#### Scenario: 文件系统受控访问
- **GIVEN** 沙箱内进程访问宿主文件系统
- **WHEN** 目标路径不在授权清单内
- **THEN** 访问被拒绝，只读/读写权限按清单粒度授予
