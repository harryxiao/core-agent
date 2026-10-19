# Skills Specification

## Purpose
技能封装是"记忆即光谱"中 L3 技能段的管理层，负责原子技能库、版本管理与灰度/A/B、技能路由，是"结晶经济闭环"的上半场（下半场为 evolution 的溶解）。

## Requirements

### Requirement: 原子技能库

系统 SHALL 维护原子技能库，每个技能封装为可复用单元，含 schema、前置条件与执行说明。
`SkillLibrary.register()` SHALL 校验字段上界（上界常量在 `skills.models` **单一定义**）：

- `skill_id` ≤ 120 字符；`instructions` ≤ 4000 字符；`description` ≤ 400 字符；
- `task_types` ≤ 16 项，每项 ≤ 80 字符；`preconditions` ≤ 8 项，每项 ≤ 200 字符。

任一越界 SHALL 拒绝入库并返回 `INVALID_SKILL_SCHEMA`，且 SHALL NOT 新增或覆盖既有技能
（同 `skill_id` 的既有条目逐字不变）。上界内的注册语义 SHALL 逐字不变。

#### Scenario: 技能注册校验
- **GIVEN** 一个待入库的技能定义
- **WHEN** 其 schema 非法
- **THEN** 拒绝入库并返回 `INVALID_SKILL_SCHEMA`

#### Scenario: 前置条件检查
- **GIVEN** 一个技能的前置条件不满足
- **WHEN** 尝试调用该技能
- **THEN** 调用被拒绝并返回 `PRECONDITION_FAILED`

#### Scenario: 字段越界被拒绝
- **GIVEN** 一个技能定义，其 `instructions` / `description` / `task_types` / `preconditions` /
  `skill_id` 中至少一项超过上界
- **WHEN** 调用 `SkillLibrary.register()`
- **THEN** 拒绝入库并返回 `INVALID_SKILL_SCHEMA`；技能库内容**逐字不变**（不新增、不覆盖）

### Requirement: 技能启用（draft → active）
系统 SHALL 提供把 `draft` 技能迁至 `active` 的**显式启用**路径，使下载 / 注册所得的草稿技能
**可被**启用（此前的迁移路径缺失 ⇒ `draft` 技能永不被路由，是死胡同）。启用 SHALL NOT 自动
发生：技能下载 / 注册后恒为 `draft`，须由显式动作驱动迁移。

- **入口**：`SkillLibrary.activate(skill_id)`；生产触达点 SHALL 为 CLI `skill activate <name>`，
  作用于**与组合根同源**的技能库（落盘），使启用跨进程可见。
- **放行集不变**：路由候选集 SHALL 仍只放行 `active` / `gray`（本能力**只补迁移路径**，SHALL NOT
  扩大路由放行集，SHALL NOT 使未启用的 `draft` 进入路由）。
- **幂等**：技能已为 `active` 时 SHALL no-op（返回该技能、状态不变、SHALL NOT 重复登记效应）。
- **未知 id**：SHALL 抛 `KeyError`（与 `lookup` / `remove` 同口径），SHALL NOT 静默创建新技能。
- **可逆**：注入效应追踪器时，启用 SHALL 登记可逆效应（回滚恢复启用前的状态）；未注入时
  SHALL NOT 登记（零行为变化，同 `SopExtractor` 的接缝口径）。

#### Scenario: draft 技能不进入路由
- **GIVEN** 一个以 `draft` 状态注册的技能，其 `task_types` 与任务词法命中
- **WHEN** 路由器匹配该任务
- **THEN** 该技能**不**进入候选集（放行集仍只含 `active` / `gray`）

#### Scenario: 显式启用后进入路由
- **GIVEN** 一个 `draft` 技能，其 `task_types` 与任务词法命中
- **WHEN** 对该技能执行显式启用
- **THEN** 其状态变为 `active`，且路由匹配该任务时**命中**该技能

#### Scenario: 重复启用幂等
- **GIVEN** 一个已 `active` 的技能
- **WHEN** 再次显式启用
- **THEN** 状态保持 `active`，且不产生第二条启用效应（幂等）

#### Scenario: 启用未知技能被拒绝
- **GIVEN** 一个未注册的 skill_id
- **WHEN** 请求启用
- **THEN** 抛 `KeyError`，且技能库**不**因此新增任何技能

#### Scenario: CLI 启用跨进程可见
- **GIVEN** 技能库中一个 `draft` 技能
- **WHEN** 执行 `skill activate <name>` 后由**另一个进程**装载同一技能库
- **THEN** 该技能状态为 `active`（启用已落盘，非进程内假象）；未注册的技能则退出码非零

#### Scenario: 启用效应可回滚
- **GIVEN** 一次启用在注入的效应追踪器上登记了效应
- **WHEN** 按该次登记的 trace 回滚
- **THEN** 该技能状态恢复为启用前状态（重复回滚不报错）

### Requirement: 版本管理与灰度/A/B
系统 SHALL 支持技能世代版本、灰度发布与 A/B 测试，依据指标决定提升或回退。

#### Scenario: 灰度发布
- **GIVEN** 一个技能发布了新版本
- **WHEN** 新版本仅对部分任务生效
- **THEN** 观察 observability 指标后再决定全量或回退

#### Scenario: A/B 中 B 退化自动回退
- **GIVEN** 技能 A/B 并行测试中 B 指标显著退化
- **WHEN** A/B 对比完成
- **THEN** 自动切回 A，B 标记 deprecated

### Requirement: 技能路由
系统 SHALL 按任务类型自动匹配最合适技能，无匹配时回退通用流程。

- **排序口径**：返回的匹配度 SHALL 为「基础分（词法命中率 / 语义分）× 历史成功率因子」的复合分；
  因子口径为——**无样本（冷启动）恒为 1.0**（不惩罚新技能），有样本时按
  `下限 + (1 - 下限) × 成功率` 缩放（下限缺省 0.5，即零成功技能仍保留一半排序分，
  避免「一次失败即永不入选」的正反馈）。未注入反馈记录器时因子恒为 1.0（行为与纯基础分一致）。
- **适用边界**：该因子 SHALL 只影响**排序**，SHALL NOT 参与命中的取舍判定（词法命中筛选与
  语义阈值判定的都是**基础分**）——否则加权会静默改变「算不算命中」的口径。
- **未命中记录的归属与唯一性**：路由 SHALL 接受可选的**调用方会话标识**（缺省空串 = 未归属）；标识
  **非空**时，未命中记录 SHALL 以该标识归属（条目 `session_id` 等于该标识，且条目 id 携带会话键），
  SHALL NOT 成为**他会话可见**的全局条目；标识为空串时归属语义与既往**逐字一致**（归全局层）。
  未命中记录的 id SHALL 由**任务内容**（连同会话键）**确定性派生** —— SHALL NOT 依赖进程内计数值：
  跨进程重启后同一会话的不同任务 SHALL NOT 互相覆盖；同一会话对**同一任务**的重复未命中 SHALL
  **幂等刷新同一条目**（未命中清单按任务去重，供后续新技能沉淀）。进程内的未命中**诊断窗口** SHALL
  **有界**（只保留最近 N 条），SHALL NOT 随任务数线性膨胀。

#### Scenario: 路由命中 Top-K
- **GIVEN** 一个任务类型
- **WHEN** 路由器匹配技能
- **THEN** 返回匹配度排序的 Top-K 技能

#### Scenario: 路由未命中沉淀
- **GIVEN** 路由器无匹配技能
- **WHEN** 回退通用 loop
- **THEN** 记录未命中，供后续新技能沉淀

#### Scenario: 未命中记录按会话归属
- **GIVEN** 一次带会话标识（非空）的路由且无匹配技能
- **WHEN** 记录未命中
- **THEN** 记录条目的 `session_id` 等于该标识且 id 含该会话键，**不以全局未归属条目形态落库**

#### Scenario: 未携带会话标识时归属不变
- **GIVEN** 一次未携带会话标识的路由且无匹配技能
- **WHEN** 记录未命中
- **THEN** 记录条目 `session_id` 为空串（归全局层），与既往语义逐字一致

#### Scenario: 未命中记录跨进程重启不互相覆盖
- **GIVEN** 某会话已在进程 A 记录一条未命中
- **WHEN** 另一起进程（未命中计数从零开始）记录**该会话另一任务**的未命中
- **THEN** 两条记录**同时存在** —— id 由任务内容派生，不因重启后的序号重数而互相覆盖

#### Scenario: 重复未命中同一任务幂等
- **GIVEN** 同一会话对**同一任务**先后两次路由未命中
- **WHEN** 记录未命中
- **THEN** 该任务在未命中条目中只有**一条**（按任务去重刷新，不随重复次数增长）

#### Scenario: 未命中诊断窗口有界
- **GIVEN** 一个长期运行的进程持续产生未命中任务
- **WHEN** 记录未命中
- **THEN** 诊断窗口只保留**最近** N 条（有界），不随任务数线性膨胀，且最近一条可查

#### Scenario: 历史成功率参与排序
- **GIVEN** 两个技能基础分相同，A 有全成功记录、B 有全失败记录
- **WHEN** 路由器匹配
- **THEN** A 排在 B 之前，且 B 仍在返回集中（下限保证其排序分不为零）

#### Scenario: 冷启动不惩罚新技能
- **GIVEN** 某技能无任何执行样本
- **WHEN** 路由器匹配
- **THEN** 其排序分等于基础分（因子 1.0），与未接反馈时一致

### Requirement: 语义路由（semantic routing）
系统 SHALL 在**词法匹配全无命中**时提供语义路由兜底：以注入的语义打分器（缺省不启用）对候选技能
逐条打分，达阈值者按分排序返回；语义命中 SHALL 视为命中（不记未命中）。

- **触发**：仅当词法匹配无任何命中（即原本记 miss 的那条路径）才启用语义；词法命中时 SHALL NOT
  产生模型调用。
- **打分口径**：打分器契约 `(任务文本, 候选技能列表) -> {skill_id: 分值}`；候选 SHALL 只含
  `active`/`gray` 技能（并受 `domain` 专属作用域过滤，见 beast-mode spec）。**阈值判定的是打分器
  给出的原始语义分**（缺省 0.5）；返回的 `score` 为再乘历史成功率因子后的排序分（见「技能路由」）。
- **归组/排序**：命中项按排序分降序，返回 Top-K（与词法路径同签名）。
- **降级**：未注入打分器 / 打分器不可用 / 分值低于阈值 → 行为 SHALL 与纯词法一致（返回词法结果，
  无命中则记 miss）；打分器故障 SHALL NOT 中断路由（`match` 不得向调用方抛异常）。

#### Scenario: 词法无命中时语义兜底命中
- **GIVEN** 技能库有 `task_types=["summarize report"]` 的技能（无执行样本），任务文本与任何技能词法不相交
- **WHEN** 注入的语义打分器给该技能打分 0.9（≥ 阈值）
- **THEN** `match` 返回该技能（`score=0.9`），且**不记 miss**

#### Scenario: 词法命中时不走语义
- **GIVEN** 任务文本词法命中某技能
- **WHEN** 调用 `match`
- **THEN** 返回词法结果，且语义打分器**不被调用**

#### Scenario: 未注入打分器时保持词法
- **GIVEN** 未注入语义打分器
- **WHEN** 词法无命中
- **THEN** 返回空列表并记 miss（与既有行为一致）

#### Scenario: 语义分值低于阈值不采纳
- **GIVEN** 词法无命中，语义打分器给全部候选打分均低于阈值
- **WHEN** 调用 `match`
- **THEN** 返回空列表并记 miss

#### Scenario: 加权不改变命中判定
- **GIVEN** 词法无命中，语义打分器给某技能打分达阈值，但该技能历史全失败（因子为下限）
- **WHEN** 调用 `match`
- **THEN** 该技能**仍被返回**（阈值判的是原始语义分），仅其 `score` 被因子缩放

#### Scenario: 打分器不可用时降级为词法
- **GIVEN** 词法无命中，语义打分器整体抛出异常
- **WHEN** 调用 `match`
- **THEN** 不抛出、返回空列表并记 miss（路由不得因打分器故障而中断）

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

### Requirement: 技能命中注入（skill hint injection）
系统 SHALL 把**路由命中的技能**以「技能 id + 版本 + `instructions` 节选」注入推理 prompt；
节选 SHALL 有字符上界（token 有界），`instructions` 为空时 SHALL 只注入 id 与版本。

- **载荷**：命中钩子 SHALL 以**纯 dict**（`skill_id` / `version` / `instructions`）交付，供 loop
  渲染——loop SHALL NOT 依赖 skills 类型。
- **口径**：每轮推理前按当轮任务重新路由；未命中或未注入技能库时，prompt SHALL NOT 含技能块。

#### Scenario: 命中技能时注入 id 与步骤
- **GIVEN** 一条 `active` 技能命中当前任务，且其 `instructions` 非空
- **WHEN** 组装推理 system prompt
- **THEN** 技能块含该 `skill_id` 与 `instructions` 节选（超长按上界截断）

#### Scenario: instructions 为空只注入 id
- **GIVEN** 命中技能的 `instructions` 为空
- **WHEN** 组装推理 system prompt
- **THEN** 技能块只含 `skill_id`（不产生空占位行）

### Requirement: 技能执行反馈（skill execution feedback）
系统 SHALL 记录技能的「命中」与「执行结果」，按 `(skill_id, version)` 累计，作为技能迭代的
判据；未注入记录器时 SHALL NOT 记录（零行为变化）。

- **命中**：技能进入 prompt 的那一轮 SHALL 记一次命中。
- **结果**：一轮收尾 SHALL 按该轮实际注入的技能记一次成功/失败（失败含超限终止轮）。
- **累积面**：反馈 SHALL 缺省**仅进程内**累积（不落盘、不写记忆）；注入路径时 SHALL 落盘并在
  启动时恢复（见「技能态持久化」）。反馈 SHALL NOT 影响本轮推理结果与终止语义。

#### Scenario: 命中与结果按版本累计
- **GIVEN** 一轮任务命中技能 X 且收尾成功
- **WHEN** 记录命中与结果
- **THEN** `(X, 该轮版本)` 命中数 +1、成功数 +1

#### Scenario: 失败轮计入失败
- **GIVEN** 一轮任务命中技能 X 但收尾失败（超限终止）
- **WHEN** 记录结果
- **THEN** `(X, 该轮版本)` 失败数 +1

### Requirement: 技能迭代闭环（skill iteration）
系统 SHALL 在**执行反馈不达标**（样本达下限且失败率达阈值）时触发迭代：由注入的改写器
（DI 可调用，缺省不启用）重写 `instructions` 为新版本并经**灰度发布**生效；两版本样本齐备后
SHALL 以 A/B 对比定夺——提升 SHALL 落地新版本，退化 SHALL 丢弃新版本并保留原版本。

- **触发**：样本数低于下限或失败率低于阈值时 SHALL NOT 迭代；未注入改写器时 SHALL NOT 触发
  （零额外模型调用）。
- **灰度**：新版本 SHALL 仅对按比例抽取的部分任务生效，其余任务仍用原版本。
- **定夺**：A/B 指标 SHALL 取各版本的成功率；胜者 SHALL 成为当前版本（版本号与
  `instructions` 一并落地）；败者 SHALL NOT 改变当前技能，且**单次**退化 SHALL NOT 置
  `status="deprecated"`（退化的是待定版本）——**连续**退化的处置见「SOP 技能退役（skill
  retirement）」。
- **可逆**：落地新版本 SHALL 登记可逆效应（回滚恢复原版本与原 `instructions`）。

#### Scenario: 反馈不达标触发迭代并灰度
- **GIVEN** 技能 X 失败率达阈值且样本达下限，已注入改写器
- **WHEN** 触发迭代
- **THEN** X 产生新版本草稿（`instructions` 为改写文本）并进入灰度（仅部分任务生效）

#### Scenario: 样本不足不迭代
- **GIVEN** 技能 X 的执行样本少于下限
- **WHEN** 触发迭代
- **THEN** 不产生新版本，且 SHALL NOT 调用改写器

#### Scenario: A/B 提升落地新版本
- **GIVEN** 技能 X 的新版本与当前版本样本齐备，新版本成功率更高
- **WHEN** A/B 定夺
- **THEN** 当前版本号与 `instructions` 更新为新版本

#### Scenario: A/B 退化丢弃新版本
- **GIVEN** 技能 X 的新版本成功率更低（**单次**退化）
- **WHEN** A/B 定夺
- **THEN** 技能保持原版本与 `instructions`（草稿丢弃），且技能 SHALL NOT 被标记 `deprecated`

### Requirement: 技能态持久化（skill state persistence）
系统 SHALL 支持把**技能态**——技能库注册表、执行反馈统计、SOP 样本累积、灰度/A-B 状态——
落盘为 JSON 并在启动时恢复；未注入路径时 SHALL 纯内存运行（零行为变化、不写盘）。

- **路径注入**：各组件 SHALL 以**可选路径参数**接收落盘位置（缺省 `None` = 纯内存）；
  落盘 SHALL NOT 引入第三方依赖（标准库 JSON）。
- **恢复**：以同一路径新建组件时 SHALL 恢复到落盘时的状态（技能含 `version` / `status` /
  `instructions` 等全字段；反馈统计含各 `(skill_id, version)` 计数；样本含各归组键的轨迹；
  灰度/A-B 含待定版本、稳定版本与最近 A/B 结果）。
- **降级**：落盘缺失或损坏（非法 JSON / 结构不符）SHALL 降级为空态并继续运行，
  SHALL NOT 阻断启动、SHALL NOT 抛异常。
- **口径**：持久化 SHALL NOT 改变路由 / 版本选择 / 迭代判定的语义（只跨进程保态）。

#### Scenario: 重启后技能库恢复
- **GIVEN** 技能库注入路径且已注册一条 `active` 技能
- **WHEN** 以同路径新建技能库（模拟进程重启）
- **THEN** 该技能仍在库中，且 `version` / `status` / `instructions` 与落盘前一致

#### Scenario: 重启后反馈统计与灰度/A-B 状态恢复
- **GIVEN** 反馈统计与灰度/A-B 状态注入路径，且已累积计数与发布状态
- **WHEN** 以同路径新建实例
- **THEN** 统计计数与灰度/A-B 状态与落盘前一致

#### Scenario: 重启后 SOP 样本恢复
- **GIVEN** SOP 提炼器注入路径，且某归组键已累积不足阈值的轨迹
- **WHEN** 以同路径新建提炼器并再提交一条同组轨迹
- **THEN** 样本在既有累积上继续计数（达阈值即提炼），不从零重来

#### Scenario: 未注入路径纯内存
- **GIVEN** 组件未注入路径
- **WHEN** 注册技能 / 记录反馈 / 累积样本 / 发布灰度
- **THEN** 不产生任何落盘文件，行为与未持久化时一致

#### Scenario: 落盘损坏降级为空态
- **GIVEN** 路径指向一个非法 JSON 文件
- **WHEN** 以该路径新建组件
- **THEN** 组件以空态启动（不抛异常），后续写入覆盖该文件

### Requirement: SOP 技能退役（skill retirement）
系统 SHALL 提供 SOP 技能的**自动退役**路径：在开关 `skills.retirement` 显式开启时，
`SkillIterator` SHALL 逐技能统计**连续** A/B 退化次数——一次退化定义为 A/B 定夺判新版本败且草稿
未采纳，一次提升（新版本落地）SHALL 使该计数归零；计数达阈值 `RETIRE_AFTER_DEGRADATIONS`
（缺省 3）时 SHALL 置该技能 `status="deprecated"`（退役）并登记可逆效应。退役 SHALL 由系统
**自动**判定，SHALL NOT 依赖人工确认。开关缺省**关闭**，关闭时连续退化 SHALL NOT 改变任何技能
的 `status`（逐字回归锚点）。

- **触发**：仅当退化**连续**达阈时 SHALL 退役；中间任一提升 SHALL 归零重计。
- **自动**：退役 SHALL 自动发生，SHALL NOT 需外部确认或人工审批。
- **可逆**：退役 SHALL 登记可逆效应（trace `skills.deprecate`，回滚即恢复退役前 `status`）。
- **退出路由**：退役技能 SHALL 退出路由候选（路由放行集仍只含 `active` / `gray`）。
- **粘性防复活**：已退役技能 SHALL NOT 因**重抽**（同组键再提炼产出同 `skill_id`）被无声复活为
  `active`；复活 SHALL 仅经**显式** `SkillLibrary.activate`。
- **缺省关**：开关未开启时，连续退化 SHALL NOT 改变 `status`，迭代行为逐字不变。

#### Scenario: 连续退化达阈自动退役
- **GIVEN** 开关 `skills.retirement` 已开启，技能 X 连续 3 次 A/B 定夺均判新版本退化
- **WHEN** 第 3 次退化定夺完成
- **THEN** X 的 `status` 置为 `deprecated`

#### Scenario: 一次提升使计数归零
- **GIVEN** 开关 `skills.retirement` 已开启，技能 X 已连续退化 2 次
- **WHEN** 下一次 A/B 定夺判新版本提升（落地）
- **THEN** X 的连续退化计数归零，且 X 的 `status` 保持 `active`（不退役）

#### Scenario: 退役可撤销
- **GIVEN** 技能 X 因连续退化达阈被退役（登记效应 trace `skills.deprecate`）
- **WHEN** 按该 trace 回滚效应
- **THEN** X 的 `status` 恢复为退役前状态

#### Scenario: 缺省关时连续退化不退役
- **GIVEN** 开关 `skills.retirement` **缺省关闭**（未开启），技能 X 连续多次 A/B 定夺均判退化
- **WHEN** 多次退化定夺完成
- **THEN** X 的 `status` 始终保持 `active`（与引入该开关前**逐字一致**）

#### Scenario: 退役技能退出路由候选
- **GIVEN** 技能 X 已退役（`status="deprecated"`）
- **WHEN** 路由匹配任务
- **THEN** X SHALL NOT 出现在路由候选中

#### Scenario: 粘性防复活
- **GIVEN** 一条 SOP 技能已退役（`status="deprecated"`），其归组键对应同一 `skill_id`
- **WHEN** 同一归组键累积成功轨迹再次触发提炼
- **THEN** 该技能 SHALL NOT 被复活为 `active`（仍为 `deprecated`），且本次重抽 SHALL NOT 入库

### Requirement: 路由未命中记录的脱敏与有界

技能路由未命中记录（`skills.miss.*`）的正文 SHALL 在落库前脱敏并**有界**：命中密钥形态的子串
SHALL 替换为 `<redacted>`，正文长度 SHALL 不超过单条字符上界。未命中记录的 **id 派生** SHALL 仍
基于**原始任务文本**（与会话键一起派生）——同一会话重复未命中同一任务仍幂等刷新同一条，跨进程
重启不互相覆盖，诊断窗口有界等既有语义 SHALL 逐字不变。脱敏 SHALL NOT 改变路由判据与
`misses` 诊断窗口内容。

#### Scenario: 未命中正文不含密钥明文且有界
- **GIVEN** 一次无匹配技能的路由，任务文本含密钥形态或超长
- **WHEN** 记录未命中
- **THEN** 落库条目正文**不含**该明文、长度不超过单条上界；工具/任务的可读前缀仍在
- **AND** 同一会话重复未命中同一任务仍只有一条（id 派生口径不变）

### Requirement: SOP 提炼正文脱敏

SOP 提炼器返回的非空文本 SHALL 在空文本判定、自动质量门与 `SkillLibrary.register()` **之前**
统一脱敏：命中密钥形态的子串 SHALL 替换为 `<redacted>`。脱敏 SHALL NOT 改变空文本判定、质量门
判据（门看到的已是脱敏文本）与提炼入库的可逆性。未含密钥形态的提炼文本 SHALL 逐字不变。

#### Scenario: SOP 入库正文不含密钥明文
- **GIVEN** 提炼器返回的 SOP 文本含密钥形态
- **WHEN** 样本达阈值触发提炼入库
- **THEN** 技能 `instructions` **不含**该明文，命中段为 `<redacted>`；技能仍按既有发布语义入库
- **AND** 未含密钥的提炼文本入库内容**逐字不变**

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
