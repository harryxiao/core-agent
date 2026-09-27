# Permission Specification

## Purpose
权限与审批管控是智能体安全落地的核心边界层，解决裸模型无约束执行的失控风险。所有副作用在执行前必须经过分级权限判定；高危操作默认拦截并进入分级人工审批流（approve / reject / edit-plan）；可执行类操作默认在沙箱中按执行域（终端/浏览器/文件系统）隔离运行，受资源配额与网络白名单约束；并提供启动级权限模式（read-only / interactive / auto-approve / high-risk-block）开关。

## ADDED Requirements

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
