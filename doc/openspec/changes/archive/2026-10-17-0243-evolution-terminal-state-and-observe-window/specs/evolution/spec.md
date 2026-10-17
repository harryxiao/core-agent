## MODIFIED Requirements

### Requirement: 观察期回归自动溶解（auto-dissolve）
系统 SHALL 在**结晶发布后**为该产物开启**观察期窗口**（记录发布时评测基线分），并由调用方持续
采样发布后的回归指标：观察样本数达下限**且**观察均分低于「基线 − 容差」时 SHALL **自动溶解**
（技能标 `deprecated`、停止路由，教训 SHALL 写回记忆层并携带回归证据）。溶解后该目标 SHALL 进入
**冻结冷却期**，期内 SHALL NOT 再次触发溶解。

- **开窗**：仅**结晶成功**（`crystallize` 返回 `published` 或 `accepted`）的产物开窗；未开窗目标的
  采样 SHALL 被忽略（不抛异常，也不累积）。
- **判定**：容差为**绝对分差**（与留出评测的 margin 同一形状）；样本数不足时 SHALL NOT 判定回归。
- **冻结**：冻结期内 SHALL NOT 累积样本、SHALL NOT 触发溶解；冷却期结束 SHALL 自动恢复采样。
- **可追溯**：自动溶解的回归证据（基线 / 观察均分 / 样本数）SHALL 随教训条目留痕。
- 两维度通用：技能级与架构级候选的结晶产物 SHALL 同等开窗。
- **采样来源**：生产侧的采样来源 SHALL 是**冷路径批次指标**——每轮 `run_cycle` 后，对本批 trace
  中**已开窗**的目标按 `plugin_id` 归因计算成功率并各上报一次样本；无归因 trace 的目标
  SHALL NOT 被采样（不产生样本）。
- **样本窗口**：观察样本 SHALL **有上界**（`max_samples`，缺省 `64`）；超出上界时 SHALL 淘汰
  **最旧**样本，判定均分 SHALL 只在保留的**最近**样本上计算（滑动窗口）—— SHALL NOT 对开窗以来
  的全部历史样本求累计均分（早期样本不得永久稀释/掩盖近期回归）。
- **基线口径**：基线 SHALL 是**发布时留出评测分**（基准质量分 0–1），在线样本 SHALL 是**归因
  trace 成功率**（0–1）——二者是**代理可比**的不同量纲，容差 SHALL 吸收该差异；基线 SHALL NOT
  在观察期内按在线样本自行重估（不得以被观察对象自身的历史分充当基线）。

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

#### Scenario: 样本窗口有界且淘汰最旧
- **GIVEN** 观察窗口的样本上界为 `max_samples`（如 4），且已累积满该数量的样本
- **WHEN** 继续上报新样本
- **THEN** 窗口只保留**最近** `max_samples` 条（最旧者被淘汰），落盘恢复后同样不超过该上界

#### Scenario: 近期回归不被早期好样本稀释
- **GIVEN** 基线 1.0、容差 0.2、下限 3、样本上界 4；窗口先累积 10 条好样本（1.0），随后连续
  上报低分样本
- **WHEN** 最近 4 条样本的均分低于「基线 − 容差」
- **THEN** SHALL 判定回归并溶解（对照：对开窗以来全部样本求累计均分的实现会因早期好样本
  而**永不触发**）

#### Scenario: 基线不被在线样本重估
- **GIVEN** 一个已开窗目标（基线分 0.9）
- **WHEN** 连续上报若干样本
- **THEN** 窗口基线恒为开窗时的 0.9，SHALL NOT 被在线样本均值改写

### Requirement: 人工确认队列的持久化与操作面
系统 SHALL 让进化候选的人工确认队列**可跨进程驱动**：候选 SHALL 携带**稳定身份**（不依赖进程内对象标识），过门候选 SHALL 连同其验证门报告与留出评测报告**作为一条记录**落盘为 JSON 并在启动时恢复；未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。系统 SHALL 提供操作面以**列出**待确认候选、**确认放行**（确认后即发布结晶）与**拒绝**候选；对 `risk_level="high"` 的候选，操作面 SHALL 作为审批流的**签发端**构造目标一致的权限审批单并经人工批准后再调用 `confirm`。

- **稳定身份**：`GenerationCandidate` SHALL 携带构造即固化、进程内唯一的标识；验证门/留出评测报告的检索 SHALL NOT 依赖 `id(obj)`。
- **随候选留痕**：落盘记录 SHALL 含候选及其门禁与评测结论，使重启后 `confirm` → `crystallize` 仍可判定（不得因重启而误判未过门/退化）。
- **队列语义**：待确认快照 SHALL 只包含 `status="pending"` 的候选；`confirm` 与 `reject` SHALL 落盘并在快照中移除该候选。
- **拒绝语义**：拒绝 SHALL 置候选 `status="rejected"`（可附理由）并落盘；被拒候选 SHALL NOT 可发布。
- **终态化**：`run_cycle` 的三类失败结局 SHALL 在落盘前把候选置**终态**——门禁拒绝与留出评测退化
  ⇒ `status="rejected"`；无法评测（`freeze`）⇒ `status="frozen"`。终态候选 SHALL NOT 出现在
  待确认快照中（SHALL NOT 要求人工 `confirm` 后才暴露其失败）。
- **恢复 fail-closed**：恢复落盘记录时，未知/缺失 `kind` SHALL 按 `plugin`（架构级）恢复、
  未知/缺失 `risk_level` SHALL 按 `high` 恢复（不得把损坏/旧格式记录当作低风险候选而绕过
  架构级审批）；缺失/未知 `status` SHALL NOT 按 `pending` 恢复（按 `rejected` 处置）；
  `caliber` 缺失 SHALL 保持 `0`（不可结晶）。
- **降级**：落盘缺失或损坏 SHALL 降级为**空队列**（不抛异常、不阻断启动）。

#### Scenario: 待确认队列跨进程恢复
- **GIVEN** 一轮冷路径产出过门候选并已落盘
- **WHEN** 以同一路径在新进程中装配引擎
- **THEN** 待确认队列含该候选，且其验证门/留出评测结论一并恢复，可继续确认并发布

#### Scenario: 未注入路径纯内存
- **GIVEN** 引擎未注入落盘路径
- **WHEN** 跑一轮后确认并发布
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

#### Scenario: 操作面列出与确认放行
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面列出并确认该候选
- **THEN** 候选被放行并发布结晶（结局 `published`），且随即从待确认队列移除

#### Scenario: 操作面拒绝候选
- **GIVEN** 待确认队列中有一个候选项
- **WHEN** 操作面拒绝该候选
- **THEN** 候选置 `rejected` 并从待确认队列移除，后续发布被拒

#### Scenario: 架构级候选的审批单由操作面签发
- **GIVEN** 待确认队列中有一个 `risk_level="high"` 的候选
- **WHEN** 操作面以人工身份确认
- **THEN** 操作面构造目标一致的审批单并经审批流批准后调用 `confirm`，候选被放行

#### Scenario: 候选不存在时的操作面反馈
- **GIVEN** 待确认队列中不含某标识
- **WHEN** 操作面以该标识确认或拒绝
- **THEN** 操作面给出明确反馈并非零退出，队列状态不变

#### Scenario: 门禁拒绝候选终态且不入队
- **GIVEN** 候选未过验证门
- **WHEN** `run_cycle` 收口
- **THEN** 候选 `status="rejected"` 并落盘，待确认快照 SHALL NOT 含该候选

#### Scenario: 退化与无法评测候选终态且不入队
- **GIVEN** 候选过门但留出评测分别判 `rollback` / `freeze`
- **WHEN** `run_cycle` 收口
- **THEN** 前者 `status="rejected"`、后者 `status="frozen"` 并落盘，二者均 SHALL NOT 出现在待确认快照

#### Scenario: 损坏记录恢复为高风险且不可确认
- **GIVEN** 一条落盘记录缺失 `kind` / `risk_level` / `status`
- **WHEN** 新进程恢复该队列
- **THEN** 候选按 `kind="plugin"`、`risk_level="high"`、非 `pending` 恢复，SHALL NOT 以低风险候选
  进入待确认快照或绕过架构级审批
