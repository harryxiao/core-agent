# Tasks

> 注：本 Phase 按项目「不锁选型」立场，deployment 仅落**可注入抽象**（无真实 supervisor / 容器 / 云 / keychain 代码）。
> 下方标注「真实后端未接」的项 = 抽象（状态机 + 注入 seam）已落地，真实托管/流水线/凭据留待 Phase 7。

## 1. 自托管运行环境（P0）

- [x] 1.1 定义运行环境抽象接口（start/stop/restart/status/health）—— 已落地 configure/assemble/bootstrap 状态机（本身即抽象定义）
- [ ] 1.2 实现进程级运行环境（supervisor 托管）—— 真实后端未接：仅 DeployTarget.runtime 抽象，无 supervisor
- [x] 1.3 定义容器运行环境适配接口（不锁定具体容器实现）—— 按「不锁定」落地抽象

## 2. 可选云托管 BYOC（P1）

- [x] 2.1 定义 BYOC 云托管接口契约（bring your own cloud）—— 已落地 CloudAdapter.adapt/parity_check
- [ ] 2.2 环境配置接口（运行参数/凭据注入，经 keychain 不落盘明文）—— 真实后端未接：env 为普通 dict，未接 keychain

## 3. 发布与升级（P0）

- [ ] 3.1 发布流水线接口（构建产物接入 composition bundle）—— 真实后端未接：publish 为内存注册表，未接真实制品流水线
- [ ] 3.2 滚动升级流程—— 真实后端未接：strategy="rolling" 仅声明，无真实滚动编排
- [x] 3.3 升级失败自动回滚，保证不半升级—— 已落地并测试（upgrade 失败 → 自动 rollback → UPGRADE_FAILED）

## 4. 健康检查与生命周期（P0）

- [ ] 4.1 暴露健康探活端点—— 真实后端未接：probe 经注入 probe_fn，无真实 HTTP 探活端点
- [x] 4.2 生命周期操作（启动/停止/重启）—— 已落地 start/stop/restart 状态机
- [ ] 4.3 异常检测 → 告警或自动恢复—— 真实后端未接：仅 restart 探活失败抛 HEALTH_UNHEALTHY，未接告警/自动恢复链路

## 5. 收敛与协作（P1）

- [ ] 5.1 与 permission 沙箱对齐运行环境选型（进程 vs 容器 vs VM）—— 本 Phase 未实施
- [x] 5.2 明确与 composition（产物来源）/distributed（跨设备拓扑）的边界—— 已在接口文档明确
