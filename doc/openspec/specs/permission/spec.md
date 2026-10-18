# Permission Specification

## Purpose
权限与审批管控是智能体安全落地的核心边界层，解决裸模型无约束执行的失控风险。所有副作用在执行前必须经过分级权限判定；高危操作默认拦截并进入分级人工审批流（approve / reject / edit-plan）；可执行类操作默认在沙箱中按执行域（终端/浏览器/文件系统）隔离运行，受资源配额与网络白名单约束；并提供启动级权限模式（read-only / interactive / auto-approve / high-risk-block）开关。

## Requirements

### Requirement: 分级权限体系
系统 SHALL 将操作划分为只读查询（read）、数据编辑（data-edit）、高危操作（high-risk）三个等级，并对高危操作默认拦截。分级判定 SHALL 依据**语义分词**（工具 / 动作词的完整词元）而非对标识串的**任意子串**匹配 —— 命名空间前缀或无关子串的偶然命中 SHALL NOT 影响等级。对显式声明的**委托类 coeffect**（字面量 `agent:delegate`）SHALL 判为 read；该豁免 SHALL NOT 放宽为 `agent:` 前缀（其余 `agent:*` coeffect SHALL 仍按高危及后续规则处理）。

对**任务清单工具**（字面量工具 id `tools.tasks`）SHALL 判为 read；该豁免 SHALL NOT 放宽为
`tasks` 词元或前缀（其余含 `tasks` 的标识 SHALL 仍按词元规则与 deny-by-default 处理）。

只读动作词集合 SHALL 包含 `process`（后台任务巡检）；`process` 词元判为 `read` SHALL NOT 豁免同标识中**更高优先**的高危词元 —— 含 `kill` 的标识 SHALL 仍判 `high-risk`。

#### Scenario: 只读操作放行
- **GIVEN** 一个操作被判定为 `read` 等级
- **WHEN** 执行前经过权限引擎判定
- **THEN** 操作在 coeffect 约束满足时放行

#### Scenario: 高危操作默认拦截
- **GIVEN** 一个操作被判定为 `high-risk` 等级
- **WHEN** 未持有已批准的人工审批单
- **THEN** 操作被拦截，返回 `APPROVAL_REQUIRED`

#### Scenario: 无法归类的操作
- **GIVEN** 一个操作的等级无法归类
- **WHEN** 执行前经过权限引擎判定
- **THEN** 默认按 `high-risk` 处理（deny-by-default）

#### Scenario: 只读判定不因命名空间子串误判
- **GIVEN** 一个操作标识本身不含任何只读动作词，仅其**命名空间前缀**偶然含只读词子串（如 `tools.` 含 `"ls"`）
- **WHEN** 执行前经过权限引擎判定
- **THEN** SHALL NOT 判为 `read`（按 `high-risk` deny-by-default）

#### Scenario: 委托类 coeffect 判只读
- **GIVEN** 一个动作声明字面量 coeffect `agent:delegate`
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `read`

#### Scenario: 非委托 agent coeffect 不放宽
- **GIVEN** 一个动作声明 `agent:other`（非 `agent:delegate`）
- **WHEN** 执行前经过权限引擎判定
- **THEN** SHALL NOT 因该 coeffect 判为 `read`（豁免仅限字面量，不放宽为前缀）

#### Scenario: 任务巡检判只读
- **GIVEN** 动作标识含 `process` 词元（如 `tools.process`）且不含任何高危词元
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `read`，在 coeffect 约束满足时放行

#### Scenario: 终止进程仍判高危
- **GIVEN** 动作标识为 `tools.process_kill`（同时含 `process` 与 `kill` 词元）
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `high-risk`（高危词元优先），未获审批时返回 `APPROVAL_REQUIRED`

#### Scenario: 任务清单判只读
- **GIVEN** 动作标识为字面量 `tools.tasks`
- **WHEN** 执行前经过权限引擎判定
- **THEN** 判为 `read`，在 coeffect 约束满足时放行

#### Scenario: 任务词元豁免不放宽
- **GIVEN** 一个动作标识含 `tasks` 词元但不是 `tools.tasks`（如 `tools.tasks_purge`）
- **WHEN** 执行前经过权限引擎判定
- **THEN** SHALL NOT 因该词元判为 `read`（豁免仅限字面量工具 id）

### Requirement: 人工审批流
系统 SHALL 对高危操作（删除、杀进程、系统级写入等）强制发起人工审批，审批超时默认拒绝。

#### Scenario: 审批通过后放行
- **GIVEN** 一个高危操作触发了审批单
- **WHEN** 人工批准该审批单
- **THEN** 操作放行执行，并仍记录可逆效应

#### Scenario: 审批超时拒绝
- **GIVEN** 一个高危操作的审批单已发出
- **WHEN** 超过 TTL 未获得人工响应
- **THEN** 审批失败（fail-closed），操作阻断并写审计

#### Scenario: 审批可追溯
- **GIVEN** 一个审批单被批准或拒绝
- **WHEN** 审批结束
- **THEN** 审批结果与请求归档，可回溯"谁在何时批准了什么"

#### Scenario: 交互审批通道
- **GIVEN** 确认门对高风险工具调用返回 confirm
- **WHEN** 经交互审批通道（如终端 y/n）发起审批
- **THEN** 批准放行、拒绝阻断；通道未接交互端时 fail-closed 拒绝

### Requirement: 沙箱隔离
系统 SHALL 在独立沙箱环境中执行代码/Shell，执行完成后自动销毁，不污染宿主系统。

#### Scenario: 沙箱内执行与销毁
- **GIVEN** 一个代码执行请求被放行
- **WHEN** 沙箱管理器执行该请求
- **THEN** 代码在受限沙箱中运行，结束后沙箱自动销毁且无残留

#### Scenario: 沙箱不可用
- **GIVEN** 沙箱环境启动失败
- **WHEN** 需要执行代码操作
- **THEN** 操作阻断并返回 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑

#### Scenario: 沙箱销毁与资源回收
- **GIVEN** 沙箱内执行结束或异常终止
- **WHEN** 沙箱管理器销毁该沙箱实例
- **THEN** 进程被终止、CPU/内存/磁盘配额释放、临时挂载与网络规则清理，无残留进程或资源泄漏

#### Scenario: 常驻子进程受配额约束
- **GIVEN** 一个长连接型消费者需在沙箱内**常驻**运行（如本地 stdio MCP 服务端）
- **WHEN** 沙箱管理器以资源配额拉起该常驻子进程
- **THEN** 进程按 rlimit（内存/CPU）约束运行，句柄归调用方持有并在其销毁时终止；拉起失败降级 `SANDBOX_UNAVAILABLE`，不降级到宿主直跑

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

### Requirement: 审批动作分级协议
系统 SHALL 将人工审批流细化为 approve / reject / edit-plan 三类动作，并按风险等级路由审批。

#### Scenario: 批准放行
- **GIVEN** 一个审批单展示完整操作上下文（影响面、可逆性、风险等级）
- **WHEN** 审批人执行 approve
- **THEN** 操作放行，审批决策归档可追溯

#### Scenario: 拒绝阻断
- **GIVEN** 一个审批单待决
- **WHEN** 审批人执行 reject
- **THEN** 操作阻断，可附拒绝理由写回，供后续提案改进

#### Scenario: 编辑计划后重提
- **GIVEN** 审批人认为原计划需调整但方向可行
- **WHEN** 审批人执行 edit-plan 并提交修订
- **THEN** 修订后的计划重新进入审批流，形成新审批单，原单标记 superseded

#### Scenario: 分级审批路由
- **GIVEN** 不同风险等级的操作触发审批
- **WHEN** 审批单生成
- **THEN** 按等级路由到对应审批策略或责任人，高危需二次确认

### Requirement: 权限模式
系统 SHALL 提供启动级权限模式开关，支持 read-only / interactive / auto-approve / high-risk-block 四档，映射 config.permission.mode，CLI 以 `--permission-mode` 指定。

**auto-approve 为无人值守全放行档**：权限判定 SHALL 对一切可由权限层决定的操作放行 —— 含高危操作、不可逆写、出站网络与无法归类的动作 —— SHALL NOT 触发人工审批、SHALL NOT 因「不可逆」或「高风险」而阻断。auto-approve 与 interactive SHALL 在判定结果上有可见差异（interactive 高危走审批；auto-approve 直接放行）。

auto-approve 的全放行 SHALL 仅覆盖**权限层**的判定，SHALL NOT 越过与权限档正交的安全机制（如注入的 guardrail 拦截）；read-only 与 high-risk-block 两档的拒绝语义 SHALL 保持不变。

#### Scenario: read-only 拒绝写操作
- **GIVEN** 权限模式为 read-only
- **WHEN** 执行写 / 编辑 / 删除类操作
- **THEN** 操作被拒绝并返回 `PERMISSION_DENIED`

#### Scenario: interactive 高危走审批
- **GIVEN** 权限模式为 interactive
- **WHEN** 执行高危操作
- **THEN** 进入人工审批流，批准才放行

#### Scenario: auto-approve 全放行
- **GIVEN** 权限模式为 auto-approve，且无可用审批通道
- **WHEN** 执行高危 / 不可逆写 / 出站网络 / 无法归类动作
- **THEN** 操作被放行（仍记录可逆效应），SHALL NOT 返回 `APPROVAL_REQUIRED`，SHALL NOT 返回 `PERMISSION_DENIED`

#### Scenario: auto-approve 与安全红线正交
- **GIVEN** 权限模式为 auto-approve 且注入了独立安全机制（guardrail）
- **WHEN** 该机制判定拦截
- **THEN** 操作仍被拒绝（权限档全放行 SHALL NOT 越过正交红线）

#### Scenario: high-risk-block 阻断高危
- **GIVEN** 权限模式为 high-risk-block
- **WHEN** 执行高危操作
- **THEN** 无条件阻断，不进入审批流，返回拒绝
