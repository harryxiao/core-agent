# evolution spec delta — evolution-cold-path

## ADDED Requirements

### Requirement: 冷路径驱动（cold path driving）
系统 SHALL 提供驱动**进化冷路径**的两个入口——①loop 收尾的维护节拍（注入冷路径回调时给出一次机会）
与②CLI 显式入口 `evolve run`——二者 SHALL 调用 `EvolutionWorker.maybe_run`：**是否真正运行一轮
cycle 由 `EvolutionTrigger` 阈值门决定**（显式入口以 `force` 跳过阈值门）；未达阈值 SHALL 不运行
（零额外模型调用、零状态变更）。

- **阈值门不搬进驱动面**：节拍只提供「机会」，节奏语义仍归 `EvolutionTrigger`。
- **CLI 口径**：`evolve run` SHALL 为一次性动作（装配运行时 → 强制跑一轮冷路径 → 打印结局），
  SHALL NOT 启动常驻进程、SHALL NOT 改变运行态。
- **降级**：驱动失败（回调抛错 / 装配失败）SHALL 降级留痕，SHALL NOT 中断 loop 本轮。

#### Scenario: 显式入口强制跑一轮
- **GIVEN** 累积 trace 未达触发阈值
- **WHEN** 执行 `evolve run`
- **THEN** 强制跑一轮 `run_cycle` 并打印结局（诊断/提案或 `no_op`），不启动常驻进程

#### Scenario: 节拍只给机会、阈值门决定
- **GIVEN** 已注入冷路径回调且累积 trace 未达阈值
- **WHEN** loop 收尾维护节拍调用该回调
- **THEN** `maybe_run` 返回 `None`（不运行 cycle、不改状态）

### Requirement: 观察期窗口持久化（observation window persistence）
系统 SHALL 支持把观察期窗口（基线分 / 观察样本 / 冻结截止）落盘为 JSON 并在启动时恢复；
未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。

- **路径注入**：窗口注册表 SHALL 以**可选路径参数**接收落盘位置（缺省 `None` = 纯内存）。
- **恢复**：以同一路径新建注册表时 SHALL 恢复窗口（含冻结截止——冻结期跨进程仍有效）。
- **降级**：落盘缺失或损坏 SHALL 降级为**无窗口**（不抛异常、不阻断启动）。

#### Scenario: 重启后窗口与冻结期恢复
- **GIVEN** 注册表注入路径，某目标已开窗（含已累积样本与冻结截止）
- **WHEN** 以同路径新建注册表
- **THEN** 该窗口的基线 / 样本 / 冻结截止与落盘前一致

#### Scenario: 未注入路径纯内存
- **GIVEN** 注册表未注入路径
- **WHEN** 开窗 / 采样 / 冻结
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

## MODIFIED Requirements

### Requirement: 观察期回归自动溶解（auto-dissolve）
系统 SHALL 在**结晶发布后**为该产物开启**观察期窗口**（记录发布时评测基线分），并由调用方持续
采样发布后的回归指标：观察样本数达下限**且**观察均分低于「基线 − 容差」时 SHALL **自动溶解**
（技能标 `deprecated`、停止路由，教训 SHALL 写回记忆层并携带回归证据）。溶解后该目标 SHALL 进入
**冻结冷却期**，期内 SHALL NOT 再次触发溶解。

- **开窗**：仅**已发布**（`crystallize` 成功）的产物开窗；未开窗目标的采样 SHALL 被忽略
  （不抛异常，也不累积）。
- **判定**：容差为**绝对分差**（与留出评测的 margin 同一形状）；样本数不足时 SHALL NOT 判定回归。
- **冻结**：冻结期内 SHALL NOT 累积样本、SHALL NOT 触发溶解；冷却期结束 SHALL 自动恢复采样。
- **可追溯**：自动溶解的回归证据（基线 / 观察均分 / 样本数）SHALL 随教训条目留痕。
- 两维度通用：技能级与架构级候选的结晶产物 SHALL 同等开窗。
- **采样来源**：生产侧的采样来源 SHALL 是**冷路径批次指标**——每轮 `run_cycle` 后，对本批 trace
  中**已开窗**的目标按 `plugin_id` 归因计算成功率并各上报一次样本；无归因 trace 的目标
  SHALL NOT 被采样（不产生样本）。

#### Scenario: 回归超阈值自动溶解并保留教训
- **GIVEN** 一个已结晶发布的产物已开窗（基线分 1.0），观察样本达下限且均分低于「基线 − 容差」
- **WHEN** 采样触发判定
- **THEN** 自动 `dissolve`：对应技能标 `deprecated`，教训条目写回记忆层且含基线/均分/样本数

#### Scenario: 冷路径批次指标采样
- **GIVEN** 一个已开窗目标，本批 trace 含归因到该目标 `plugin_id` 的若干条（部分失败）
- **WHEN** 冷路径跑完一轮 cycle 后采样
- **THEN** 该目标被上报一次样本，分数等于本批归因 trace 的成功率

#### Scenario: 无归因 trace 不采样
- **GIVEN** 一个已开窗目标，但本批 trace 无一条归因到该目标
- **WHEN** 冷路径采样
- **THEN** 该目标不被采样（样本数不变）

#### Scenario: 样本不足不判定
- **GIVEN** 观察样本数少于下限（即使单次分数远低于基线）
- **WHEN** 采样
- **THEN** 不判回归、不溶解（仅累积样本）

#### Scenario: 未回归不溶解
- **GIVEN** 观察均分不低于「基线 − 容差」
- **WHEN** 采样达下限
- **THEN** 不溶解，技能保持 `active`

#### Scenario: 冻结期内不再触发
- **GIVEN** 一次自动溶解已发生，目标处于冻结冷却期
- **WHEN** 冷却期内继续采样（即使分数远低于基线）
- **THEN** 不累积样本、不再触发溶解；冷却期结束后恢复采样

#### Scenario: 未开窗目标的采样被忽略
- **GIVEN** 一个从未结晶发布（未开窗）的目标
- **WHEN** 调用采样
- **THEN** 忽略该样本（不抛异常、不建窗、不溶解）
