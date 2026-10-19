## MODIFIED Requirements

### Requirement: SOP 提炼（skill extraction）

系统 SHALL 提供 SOP 提炼能力：由注入的提炼器（DI 可调用，缺省不启用）把**同一类任务的
成功轨迹**聚合、提炼为一条 `Skill`（`instructions` 承载 SOP 步骤、`task_types` 承载归组键），
并 SHALL 经 `SkillLibrary.register()` 入库（复用既有 schema 校验），入库 SHALL 可逆。

- **准入闸（确定性、零模型调用）**：提交轨迹 SHALL 先经以下闸门，任一不满足即 SHALL 不累积：
  任务成功（`ok=True`）；行动序列**非空**；任务文本去空白后 **≥ 6 字符**；**单轮面**
  （`namespace` 为空）行动序列 SHALL 至少含一行 `tools.` 动作（闲聊 / 拒绝 / 纯文字轮无工具动作）；
  **任务级面**（`namespace="task"`）SHALL 至少含 2 步（其步序是子任务骨架，不作 `tools.` 要求）。
  组内已存在**逐字相同**的行动序列时 SHALL 忽略该次提交（不累积、不虚增样本）。
- **触发**：任务**成功**收尾时提交「任务文本 + 行动/结果序列」；失败轨迹 SHALL 不计入累积。
- **阈值**：同一组累计达阈值（缺省 3 条）才提炼一次，提炼后 SHALL 清空该组（下批重新累积）。
- **归组**：SHALL 优先词法命中已有技能的 `task_types` 并复用其作组键；未命中时以任务词元签名
  为新组键。归组口径 SHALL 确定性（离线可断言）。
- **发布**：提炼产物 SHALL 以 **`draft`** 入库（SHALL NOT 自动 active）；路由只放行
  `active` / `gray`，故 draft 在显式 `skill activate` 前 SHALL NOT 进入路由。提炼文本为空时
  SHALL 不入库。
- **已发布保护**：同 `skill_id` 已存在时——`active` / `gray` SHALL 跳过提炼（清组 + 留痕只报组键），
  SHALL NOT 覆盖或降级；`deprecated` SHALL 保持粘性（不因重抽复活）；`draft` 可被重新提炼覆盖。
- **提炼格式**：prompt SHALL 要求**结构化 Markdown**（适用场景 / 前置条件 / 步骤 / 验证 / 失败模式），
  并明确「轨迹间无共同可复用步骤（如闲聊）时输出空字符串」。系统 SHALL NOT 要求 JSON——
  `Skill` 无对应程序字段、无消费方。
- **确定性质量门（缺省开启、零模型调用）**：提炼文本（脱敏后）SHALL 先经确定性门：非空；
  `strip()` 后长度 ≥ 10 且 ≤ 4000 字符；至少 **2 个步骤行**（行首 `数字.` / `数字)` /
  `数字、` / `-` / `*` / `•` 后接非空内容）；SHALL NOT 与技能库中**任一**技能
  `instructions` 逐字相同（`strip()` 后比较）；SHALL NOT 含**拒绝/无法提炼**固定短语
  （`未提供有效的执行轨迹` / `无法提炼` / `抱歉` / `无法协助`）。门未过时：产物 SHALL NOT 入库、
  该组样本 SHALL 清空、SHALL 留痕（**只报组键，绝不回显提炼正文**）。该门无关闭开关。
- **任务级过程输入**：除**单轮**轨迹外，系统 SHALL 提供以**编排任务粒度**为输入的观察面 ——
  其观察单位是「**任务目标 + 按 `plan.order` 聚合的子任务步序**」（任务过程），随任务**成功**
  收尾（`DONE`）提交一次。该面 SHALL 与单轮面**样本隔离**（独立命名空间与样本集，互不混组：
  面、组键、`skill_id` 三者均不交叠），提炼产物 SHALL 同样经 `SkillLibrary.register()` 入库、
  可逆。两步序语义不同（任务级承载子任务骨架、单轮承载工具调用行），隔离 SHALL 保证两类
  样本不被聚合进同一提炼。
- **自动质量门**：系统 SHALL 支持为提炼器注入**自动质量门**（DI 可调用，缺省不启用）——质量门
  SHALL 由**判定（judgment）原语**驱动的自动判定提供，SHALL NOT 引入人工确认。该判定门 SHALL 在
  确定性门**之后**执行。门**未过**时：提炼产物 SHALL NOT 入库、该组样本 SHALL 清空（避免同批样本
  反复触发提炼调用）、SHALL 留痕（**只报组键，绝不回显提炼正文**）。门判定**异常**或**缺答案**时
  SHALL **放行**（fail-open：判定故障不阻断入库，亦不中断主流程）。未注入质量门时，满足确定性门的
  入库行为 SHALL 逐字不变。
- **线程安全**：提炼器 SHALL 在内部串行化样本读写（同一实例可被主 / 子 / 兽循环的收尾线程共享）。
- 未注入提炼器时 SHALL 不累积、不提炼（零额外调用）；提炼失败 SHALL NOT 中断 Agent 主流程。

#### Scenario: 同类任务达阈值提炼入库
- **GIVEN** 已注入提炼器与技能库，同一类任务成功执行 3 次（阈值），每次行动序列不同且含 `tools.` 动作
- **WHEN** 第 3 次成功收尾触发提炼
- **THEN** 技能库新增一条 `Skill`：`instructions` 为提炼文本、`task_types` 含组键、
  `status="draft"`；`SkillRouter.match` **不**命中该技能；执行 `skill activate` 后才命中

#### Scenario: 未达阈值不提炼
- **GIVEN** 同一类任务成功执行次数少于阈值
- **WHEN** 每次成功收尾触发观察
- **THEN** 技能库不新增技能（仅累积样本）

#### Scenario: 失败轨迹不计入累积
- **GIVEN** 同一类任务连续失败（`ok=False`）
- **WHEN** 收尾触发观察
- **THEN** 不累积样本、不提炼（失败轨迹不是 SOP）

#### Scenario: 短任务不累积
- **GIVEN** 任务文本去空白后少于 6 字符（如 `继续` / `hi` / `完成了吗`）
- **WHEN** 收尾触发观察
- **THEN** 不累积样本（无论执行多少次都不达阈值、不提炼）

#### Scenario: 空行动序列不累积
- **GIVEN** 一轮成功任务但行动序列为空
- **WHEN** 收尾触发观察
- **THEN** 不累积样本

#### Scenario: 无工具动作不累积（单轮面）
- **GIVEN** 单轮面的一轮成功任务，行动序列非空但不含任何 `tools.` 动作（如纯文字/拒绝轮）
- **WHEN** 收尾触发观察
- **THEN** 不累积样本

#### Scenario: 重复轨迹不虚增支持度
- **GIVEN** 同一组已有一条行动序列 X
- **WHEN** 同一轨迹 X 再次提交（即使多次）
- **THEN** 该组样本数不增（不因一次动作刷满阈值）

#### Scenario: 归组复用已有技能的 task_types
- **GIVEN** 技能库已有一条 `task_types=["report summarize"]` 的技能
- **WHEN** 新任务 "summarize report" 收尾且词法命中该 task_type
- **THEN** 样本归入该 `task_type` 组键（而非新建任务词元签名组）

#### Scenario: 未注入提炼器时降级
- **GIVEN** 未注入提炼器（未配置模型）
- **WHEN** 任务成功收尾
- **THEN** 不累积、不提炼、无额外模型调用，主流程不受影响

#### Scenario: 空提炼不入库
- **GIVEN** 已注入提炼器，样本达阈值
- **WHEN** 提炼返回空文本
- **THEN** 不入库（不写半成品），样本保留待下轮

#### Scenario: 提炼入库可逆
- **GIVEN** 一次提炼已入库一条技能
- **WHEN** 按该次登记的 trace 回滚效应
- **THEN** 技能从库中移除（重复回滚不报错）

#### Scenario: 任务达阈值提炼为任务级 SOP
- **GIVEN** 已注入提炼器与技能库，同一类**编排任务**成功达成 `DONE` 达阈值
- **WHEN** 第 N 次成功收尾触发**任务级**观察，提交「任务目标 + 按 `plan.order` 聚合的子任务步序」
- **THEN** 技能库新增一条 `Skill`：`instructions` 为任务级提炼文本、`task_types` 含任务归组键、
  `status="draft"`

#### Scenario: 任务级与单轮样本不混组
- **GIVEN** 任务级与单轮两条观察面共用同一技能库，且单轮技能已含词法相近的 `task_types`
- **WHEN** 任务级观察提交样本
- **THEN** 任务级样本归入**独立命名空间**的组键（不复用单轮技能的 `task_types`、不与之混组），
  其提炼产物的 `skill_id` 与单轮产物**不同**

#### Scenario: 质量门未过不入库
- **GIVEN** 已注入提炼器与**拒绝该产物的**自动质量门，同组样本已达阈值
- **WHEN** 提炼产出非空文本、门判定未过
- **THEN** 技能库**不新增**技能；该组样本被**清空**；留痕**只报组键**，**不**含提炼正文

#### Scenario: 未注入质量门时发布行为不变
- **GIVEN** 已注入提炼器但**未**注入质量门
- **WHEN** 同组样本达阈值且提炼产出**满足确定性门**的文本
- **THEN** 技能照常以 `draft` 入库

#### Scenario: 确定性门拦截退化提炼
- **GIVEN** 已注入提炼器，样本达阈值
- **WHEN** 提炼产出单步、超短（`strip()` 后 < 10 字符）或超长（> 4000 字符）的文本
- **THEN** 不入库；该组样本被**清空**；留痕**只报组键**，**不**含提炼正文

#### Scenario: 拒绝文本被确定性门拦截
- **GIVEN** 已注入提炼器，样本达阈值
- **WHEN** 提炼产出「未提供有效的执行轨迹，无法提炼…」等拒绝/道歉文本
- **THEN** 不入库；该组样本被清空（绝不把拒绝文本发布为 SOP）

#### Scenario: 逐字重复的提炼不入库
- **GIVEN** 技能库已有一条 `instructions` 为 X 的技能，同组样本达阈值
- **WHEN** 提炼产出与 X 逐字相同（`strip()` 后）的文本
- **THEN** 不入库（技能库条目数不变、既有技能逐字不变）；该组样本被**清空**

#### Scenario: 已 active 的技能不被重抽覆盖
- **GIVEN** 技能库已有一条同 `skill_id` 的 `active` 技能
- **WHEN** 同组样本达阈值并产出提炼文本
- **THEN** 技能库不新增、不覆盖该技能（`status` 仍为 `active`，`instructions` 逐字不变）；
  该组样本被清空

## ADDED Requirements

### Requirement: 技能状态运维（CLI）

系统 SHALL 提供 `skill list [--status STATUS]`：列出技能库中的技能（`skill_id` / `status` /
`description`），`--status` SHALL 按状态过滤（`draft|active|gray|deprecated`）。该入口 SHALL 供
操作者 review SOP 提炼产物并决定是否启用。

系统 SHALL 提供 `skill deprecate <name>`：把技能迁至 `deprecated`（复用 `SkillLibrary.deprecate`），
SHALL 幂等；未知技能 SHALL 退出非零。退役 SHALL NOT 物理删除，可经 `skill activate` 复活。
两个入口 SHALL 与运行时共用同一技能库路径（`$CORE_STATE_DIR/skills.json`）。

#### Scenario: 列出 draft 技能
- **GIVEN** 技能库含一条 `status="draft"` 的 SOP 技能与若干 active 技能
- **WHEN** 执行 `skill list --status draft`
- **THEN** 输出只含该 draft 技能的 id / 状态 / 描述

#### Scenario: 退役跨进程可见
- **GIVEN** 技能库含一条 active 技能
- **WHEN** 执行 `skill deprecate <id>` 后重新加载技能库
- **THEN** 该技能 `status="deprecated"`，且不再被路由命中

#### Scenario: 退役幂等与未知技能
- **GIVEN** 技能已 `deprecated`
- **WHEN** 再次执行 `skill deprecate <id>`
- **THEN** 成功且状态不变（幂等）；对未知 id SHALL 退出非零
