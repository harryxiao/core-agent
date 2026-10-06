# Evolution Specification Delta

## MODIFIED Requirements

### Requirement: 架构级候选的原生实施（可选）
系统 SHALL 支持把架构级候选的 `accepted` 结局**可选地**推进为**已实施**：**仅当**
`features.evolution_executor` 显式开启时，组合根 SHALL 装配**原生执行器**（`EvolutionExecutor`）；
未声明（**缺省**）时 SHALL NOT 装配——关时不构造实例、不产生装配期副作用，`accepted` 结局逐字
回到本 Requirement 引入前的现状，且 `crystallize` 的返回值在任何情况下 SHALL 不变（恒为 `accepted`）。

执行器 SHALL **仅由操作面显式驱动**（`core-agent evolve implement …`），SHALL NOT 挂进 loop 的
热/冷路径节拍、SHALL NOT 注册为任何 Agent 可调用的工具。实施 SHALL 分**两阶段**，**复核前
SHALL NOT 落地**：

- **筹备（prepare，`--dry-run`）**：由**补丁生产者**按候选产出补丁 → **范围守卫** → 应用 →
  跑**冻结验证门** → **回退**。制品（补丁内容、被改文件的原内容、各门禁结论）SHALL 落入**候选台账**
  （与候选同一条记录承载，跨进程可读），SHALL NOT 在本阶段留下任何工作树改动。
- **复核（review）**：制品 SHALL 以**可复核的形式**（补丁差异 + 门禁报告）呈现给人工，并 SHALL
  经人工**复核关**——要求一张与候选目标一致的**已批准**审批单，其操作标识 SHALL 与 `confirm` 阶段
  的审批单**可区分**（不得跨阶段复用同一张单）；缺失、未批准或目标不符时 SHALL NOT 落地（fail-closed）。
  **待复核**仅指**门禁全过**（`gated=True`）的制品：未过门的制品 SHALL NOT 被列为待复核项
  （呈现面 `evolve pending` 与落地面 `commit` 取同一判据）。
- **落地（commit）**：复核通过后 SHALL 应用**被复核的那一份**制品（SHALL NOT 重新产出补丁），
  记录**可逆效应**（undo 可回退），候选状态与结局 SHALL 为 **`implemented`**
  （`EvolutionOutcome.status` 的**新增**词表项）；`accepted` 的「已批准、未实施」诚实语义 SHALL NOT
  被回退为 `published`。落地 SHALL **只认门禁全过的制品**：无制品**或**制品未过门（`gated=False`，
  含筹备异常抛出 / 进程中断留下的**残留制品**）⇒ SHALL 结构化拒绝（`IMPLEMENT_REJECTED`）并提示
  重新筹备，SHALL NOT fail-open（断线式放行会让从未跑过门禁的补丁被永久应用）。

约束：

- **门禁独立性**：门禁命令 SHALL 取自**单一真源**（`GATE_COMMANDS`），执行器 SHALL NOT 自选门禁
  命令、SHALL NOT 另立第二份门禁清单；门禁 SHALL 经**独立执行面**（子进程）运行。留出评测
  （`Evaluator`）**不**参与实施验证——本 Requirement 只承诺冻结门。
- **范围守卫**：补丁路径 SHALL 限于**源码面**（`src/core/` 内的 `.py`），且 SHALL NOT 触碰验证装置
  与信任链（测试与测试配置、构建/类型/风格配置、门禁命令真源、权限审批、配置开关、进化引擎与
  台账、组合根与操作面、规格与变更目录、CI 配置）；触碰即 SHALL 拒绝且 SHALL NOT 应用。
- **路径与归因一致**：补丁路径 SHALL 由候选的**归因目标**（`target_plugin`，须为内部核心模块 id）
  经**约定**解析得出且该文件**确实存在**；不符或不存在时 SHALL 拒绝（fail-closed，不应用）。
- **可逆**：落地 SHALL 记录可逆效应（`EffectTracker.record(effect, undo)`）；筹备阶段的临时应用
  SHALL 在门禁跑完后被回退。
- **崩溃安全**：被改文件的原内容 SHALL 在**应用之前**随制品持久化，且回退 SHALL 在异常路径下
  同样完成（`finally` 语境）。
- **漂移拒绝**：落地前 SHALL 校验目标文件当前内容与筹备时记录的原内容**一致**，不一致 SHALL
  结构化拒绝（`IMPLEMENT_STALE`）且不落地。
- **不进入运行**：补丁 SHALL NOT 在通过验证门与人工复核之前成为运行系统的行为（对齐 `CORE-EVO-R3`）。
- **观察期开窗口径不变**：开窗仍发生在 `crystallize` 返回 `accepted` 之时，实施 SHALL NOT 重复开窗。

#### Scenario: 开启执行器时筹备并落 implemented
- **GIVEN** `features.evolution_executor` 显式开启，一个架构级候选已 `accepted`，补丁通过范围守卫与
  归因一致性校验、且全部门禁通过，并已获一张目标一致、已批准的实施复核单
- **WHEN** 先筹备（`--dry-run`）再复核落地
- **THEN** 补丁被永久应用、记录可逆效应、候选状态与结局为 **`implemented`**（不是 `accepted`、
  不是 `published`）

#### Scenario: 缺省不装配执行器（逐字回到现状）
- **GIVEN** `features.evolution_executor` 未声明（缺省）
- **WHEN** 系统启动装配，且一个架构级候选走到 `crystallize`
- **THEN** 不装配执行器（装配面为空）、不产生装配期副作用；结局仍为 `accepted`，操作面拒绝执行
  并说明原因，且不产生任何 `implemented`

#### Scenario: 门禁不过则回退不落地
- **GIVEN** 执行器已开启，补丁已应用且**未**通过冻结验证门（任一门禁失败）
- **WHEN** 筹备结束
- **THEN** 临时应用 SHALL 被回退（工作区恢复筹备前状态），SHALL NOT 留下制品、SHALL NOT 落
  `implemented`，并抛出结构化门禁失败

#### Scenario: 补丁触碰验证装置被范围守卫拒绝
- **GIVEN** 执行器已开启，补丁生产者产出的补丁路径落在验证装置或信任链内（如测试目录、测试/
  构建配置、门禁命令真源、权限审批、配置开关、规格目录）
- **WHEN** 筹备执行范围守卫
- **THEN** 结构化拒绝该补丁，**不应用**任何改动（工作区逐字不变）、不落 `implemented`

#### Scenario: 补丁路径与候选归因不符被拒绝
- **GIVEN** 执行器已开启，补丁生产者为归因到内部核心模块 A 的候选给出了指向**另一个**模块文件
  （或指向一个**不存在**的文件）的路径
- **WHEN** 筹备校验路径与归因一致性
- **THEN** 结构化拒绝，**不应用**任何改动、不落 `implemented`

#### Scenario: 落地前须先有已筹备制品
- **GIVEN** 执行器已开启，一个已 `accepted` 的架构级候选**尚未**筹备
- **WHEN** 直接要求落地（未先 `--dry-run`）
- **THEN** 结构化拒绝并提示先筹备，**不应用**任何改动、不落 `implemented`

#### Scenario: 未过门的残留制品不被放行落地
- **GIVEN** 执行器已开启，一次筹备在门禁跑动中中断（门禁执行抛出异常 / 进程被杀），台账里留下一条
  **未过门**（`gated=False`）的残留制品，且工作树已回退到筹备前
- **WHEN** 后续进程携带一张目标一致、已批准的实施复核单要求落地
- **THEN** 结构化拒绝（`IMPLEMENT_REJECTED`）并提示重新筹备，**不应用**任何改动（工作区逐字不变）、
  不落 `implemented`；该残留制品 SHALL NOT 出现在待复核列表

#### Scenario: 复核单缺失或目标不符不放行
- **GIVEN** 一个已筹备待复核的架构级候选
- **WHEN** 不带审批单、或携带非已批准、或携带目标为其他插件、或携带 `confirm` 阶段那张
  （操作标识不可区分）的单子要求落地
- **THEN** 抛 `CONFIRM_REQUIRED`，**不落地**（工作区逐字不变）、不落 `implemented`，候选仍待复核

#### Scenario: 落地前工作区漂移则拒绝
- **GIVEN** 一份已筹备待复核的制品，且其目标文件在筹备之后被外部改动（与筹备时记录的原内容不一致）
- **WHEN** 要求落地
- **THEN** 结构化拒绝（`IMPLEMENT_STALE`），**不落地**，避免把补丁覆盖到已漂移的内容上

#### Scenario: 落地后可跨进程查得已实施状态
- **GIVEN** 一次成功的落地已发生（操作面进程已退出）
- **WHEN** 后续进程查该候选
- **THEN** 候选状态为 `implemented`、制品（补丁与门禁报告）仍可读——实施结论 SHALL NOT 只存在于
  一次性进程的标准输出
