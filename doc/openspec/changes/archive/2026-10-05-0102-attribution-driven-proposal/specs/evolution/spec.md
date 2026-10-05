# Evolution Specification Delta

## MODIFIED Requirements

### Requirement: 模块级提案
系统 SHALL 针对诊断结果生成世代化产物（技能/插件补丁 + delta）。候选的 `kind` SHALL 由**诊断归因**
驱动：`target_plugin` 属于**内部核心模块**（归因白名单）时 SHALL 产出 `kind="plugin"`，否则 SHALL
产出 `kind="skill"`；`risk_level` SHALL 随 `kind` 固化（`plugin` → `high`，`skill` → `low`）。
提案器 MAY 接受**显式覆盖** `kind`，显式值 SHALL 优先于归因判定。

#### Scenario: 生成候选
- **GIVEN** 一个 DiagnosisReport 已归因到插件
- **WHEN** Proposer 运行
- **THEN** 生成 GenerationCandidate，含 delta 与 kind（skill/plugin）

#### Scenario: 归因到内部核心模块产出架构级候选
- **GIVEN** 一个归因到内部核心模块的 DiagnosisReport（`target_plugin` 属归因白名单，如 `loop.default`）
- **WHEN** Proposer 未收显式 `kind` 覆盖并运行
- **THEN** 候选 `kind` 为 `plugin`、`risk_level` 为 `high`、`status` 保持 `pending`

#### Scenario: 归因到工具产出技能级候选
- **GIVEN** 一个归因到**非**内部核心模块的 DiagnosisReport（如工具 id `tools.file_read`）
- **WHEN** Proposer 未收显式 `kind` 覆盖并运行
- **THEN** 候选 `kind` 为 `skill`、`risk_level` 为 `low`

#### Scenario: 显式覆盖优先于归因
- **GIVEN** Proposer 收显式 `kind="skill"`，而诊断归因到内部核心模块
- **WHEN** 提案
- **THEN** 候选 `kind` 为 `skill`（显式值优先，归因判定被覆盖）

#### Scenario: 候选进入验证门
- **GIVEN** 候选已生成
- **WHEN** 发布前
- **THEN** 交 Validator 验证，未过门不发布

### Requirement: 架构级候选强制人工审批（HITL confirm gate）
系统 SHALL 按风险域区分候选的确认路径：世代化候选 SHALL 携带 `risk_level`（`high` 为架构级——
`kind="plugin"`，`low` 为技能库级——`kind="skill"`）。`risk_level="high"` 的候选 SHALL 强制走
**人工审批**：`confirm` SHALL 要求一张与候选目标一致的**已批准**权限审批单，缺失、未批准或目标
不符时 SHALL NOT 放行（fail-closed，候选保持 `pending`）；`risk_level="low"` 的候选 SHALL 仍须
**显式**人工 `confirm()`——系统 SHALL NOT 提供低风险自动结晶。

- **判定**：`risk_level` SHALL 由提案阶段按 `kind` 判定并随候选固化（不依赖调用方传入）。
- **门禁**：审批判定 SHALL 由 permission 域解释其审批单状态（域外 SHALL NOT 依赖状态字面量）。
- **可追溯**：审批单 SHALL 携带候选目标与 trace，经审批流归档可回溯。
- **拒绝不放行**：被拒/过期/超时的审批单 SHALL NOT 放行候选；`crystallize` 对未确认候选仍 SHALL
  拒绝（既有 `CANDIDATE_PENDING` 语义不变）。
- **结局诚实**：架构级候选获批并过门后 SHALL 以 `accepted` 结局登记（语义为「已批准、**待人工
  实施**」）——系统 SHALL NOT 在该分支报告 `published`（无架构产物被发布、无世代被晋升）；
  技能级候选 SHALL 以 `published` 结局登记（确实写入技能库）。两个分支 SHALL 同样开启观察期
  （观察期判的是「批准之后是否回归」，与是否有产物无关）。

#### Scenario: 架构级候选无审批单不放行
- **GIVEN** 一个 `risk_level="high"` 的候选已过验证门与留出评测
- **WHEN** 不带审批单调用 `confirm`
- **THEN** 抛结构化错误 `CONFIRM_REQUIRED`，候选 `status` 保持 `pending`，`crystallize` 拒绝

#### Scenario: 架构级候选带已批准审批单放行
- **GIVEN** 一个 `risk_level="high"` 的候选，且已有一张目标一致、经人工批准的审批单
- **WHEN** 携带该审批单调用 `confirm`，随后 `crystallize`
- **THEN** 候选 `status` 置 `confirmed`，结晶结局为 **`accepted`**（「已批准、待人工实施」，
  **不**报 `published`），并开启观察期

#### Scenario: 审批被拒不放过
- **GIVEN** 一个 `risk_level="high"` 的候选，审批单已被人工拒绝
- **WHEN** 携带该审批单调用 `confirm`
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`

#### Scenario: 审批单目标不符不放行
- **GIVEN** 一张已批准但目标为**其他**插件的审批单
- **WHEN** 携带它确认本候选
- **THEN** 抛 `CONFIRM_REQUIRED`，候选保持 `pending`（不得跨候选复用审批）

#### Scenario: 技能级候选仍须显式人工确认
- **GIVEN** 一个 `risk_level="low"` 的候选（`kind="skill"`）
- **WHEN** 调用 `confirm`（不带审批单）
- **THEN** 候选置 `confirmed`（人工确认仍是必要条件，只是不要求权限工单），未被确认时
  `crystallize` 仍拒绝

#### Scenario: 技能级候选结晶报 published
- **GIVEN** 一个已确认、过验证门、留出集不退化的 `risk_level="low"` 候选
- **WHEN** `crystallize`
- **THEN** 技能写入技能库且结局为 `published`

#### Scenario: 未确认候选不产出任何发布类结局
- **GIVEN** 一个 `status="pending"` 的候选（无论 `risk_level`）
- **WHEN** 直接调用 `crystallize`
- **THEN** 抛 `CANDIDATE_PENDING`，不产生 `accepted` 亦不产生 `published` 结局

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
