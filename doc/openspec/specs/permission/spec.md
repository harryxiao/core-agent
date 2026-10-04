# Permission Specification

## Purpose
权限与审批管控是智能体安全落地的核心边界层，解决裸模型无约束执行的失控风险。所有副作用在执行前必须经过分级权限判定；高危操作默认拦截并进入分级人工审批流（approve / reject / edit-plan）；可执行类操作默认在沙箱中按执行域（终端/浏览器/文件系统）隔离运行，受资源配额与网络白名单约束；并提供启动级权限模式（read-only / interactive / auto-approve / high-risk-block）开关。

## Requirements

### Requirement: 分级权限体系
系统 SHALL 将操作划分为只读查询（read）、数据编辑（data-edit）、高危操作（high-risk）三个等级，并对高危操作默认拦截。

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

#### Scenario: 三域隔离
- **GIVEN** 一个任务同时需要终端、浏览器、文件系统三类操作
- **WHEN** 沙箱管理器分配执行环境
- **THEN** 三类操作在互相隔离的域中执行，域间数据流经显式通道，不共享宿主资源

#### Scenario: 网络出站白名单
- **GIVEN** 沙箱内的代码或浏览器发起出站网络请求
- **WHEN** 目标不在白名单内
- **THEN** 请求被拦截并记录，不降级放行

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

#### Scenario: read-only 拒绝写操作
- **GIVEN** 权限模式为 read-only
- **WHEN** 执行写 / 编辑 / 删除类操作
- **THEN** 操作被拒绝并返回 `PERMISSION_DENIED`

#### Scenario: interactive 高危走审批
- **GIVEN** 权限模式为 interactive
- **WHEN** 执行高危操作
- **THEN** 进入人工审批流，批准才放行

#### Scenario: auto-approve 放行低危
- **GIVEN** 权限模式为 auto-approve
- **WHEN** 执行非高危操作
- **THEN** 自动放行（仍记录可逆效应），高危操作仍按高危策略拦截或走审批

#### Scenario: high-risk-block 阻断高危
- **GIVEN** 权限模式为 high-risk-block
- **WHEN** 执行高危操作
- **THEN** 无条件阻断，不进入审批流，返回拒绝
