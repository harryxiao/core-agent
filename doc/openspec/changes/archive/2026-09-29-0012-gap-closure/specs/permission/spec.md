权限沙箱执行颗粒度与审批动作分级协议增量规格，将沙箱从概念层细化为按执行域隔离并施加白名单/配额约束，将人工审批细化为 approve/reject/edit-plan 三级动作并按风险等级路由，对齐 Devin/Manus 云端 VM 与 Claude Code permission 规则。

## ADDED Requirements

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
