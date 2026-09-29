
权限与审批管控是智能体安全落地的核心边界层，解决裸模型无约束执行的失控风险。所有副作用在执行前必须经过分级权限判定；高危操作默认拦截并进入人工审批流；可执行类操作默认在沙箱中隔离运行。

## ADDED Requirements

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


