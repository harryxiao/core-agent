## ADDED Requirements

### Requirement: 技能候选内容生成

系统 SHALL 为**技能级**候选提供可选的内容生成接缝：经组合根注入的 writer 工厂
（`skill_content_writer_with(llm) -> writer`，照 SOP writer 先例）把诊断 `issue` 与有界
`failure_notes` 蒸馏为可执行内容（`task_types` / `instructions` / `param_schema`，及可选
`preconditions` / `description`）。内容 SHALL 以纯 dict 写入候选 `delta["content"]`，可
序列化往返。

- **DI 方向**：evolution SHALL NOT import 任何 LLM 抽象；模型调用由组合根提供。
- **失败即无 content**：writer 返回非法 JSON、结构不符、或调用异常时 SHALL 返回空结果；
  Proposer SHALL **不**写入 `content` 键（delta 仍仅含 `issue`），SHALL NOT 抛裸异常。
- **未注入逐字不变**：未注入 writer 时，技能级 delta SHALL 仍仅 `{"issue": ...}`，与既有
  实现逐字一致。
- **plugin 不受影响**：架构级候选 SHALL NOT 经本接缝生成 content。
- **有界 prompt**：注入 `failure_notes` 时 SHALL 有界（条数与单条字符上限由实现常量钉死，
  与诊断失败摘要同口径量级）。

#### Scenario: 注入 writer 后技能候选携带 content

- **GIVEN** Proposer 已注入合法 writer，且诊断归因产出 `kind="skill"`
- **WHEN** `propose` 运行且 writer 返回有效内容
- **THEN** 候选 `delta` 含 `issue` 与 `content`（dict，可 asdict 往返），`content` 经校验为有效

#### Scenario: writer 失败不写 content 键

- **GIVEN** Proposer 已注入 writer，但 writer 对本次 prompt 返回空（非法 JSON / 结构不符 / 异常）
- **WHEN** `propose` 运行
- **THEN** 候选 `delta` **仅**含 `issue`，SHALL NOT 含 `content` 键，SHALL NOT 向调用方抛裸异常

#### Scenario: 未注入 writer 逐字不变

- **GIVEN** Proposer 未注入 writer
- **WHEN** 对技能级诊断 `propose`
- **THEN** 候选 `delta` 仍仅 `{"issue": ...}`，与既有实现逐字一致

## MODIFIED Requirements

### Requirement: 验证门

系统 SHALL 对候选执行 review + 运行时测试，通过才允许发布。

- **口径版本**：结晶面门 SHALL 带**口径版本**（判定所依据的 review / 运行时测试 / 留出评测口径的
  版本号）；候选 SHALL 在其**提案时**被盖上当时的口径版本并**随候选台账落盘**。投放（`crystallize`）
  时口径与现口径**不符**的候选 SHALL **拒绝**（结构化错误、候选留待确认态，须按现口径**重新提案**），
  SHALL NOT 放行。本 change 将现口径递增为 **3**（新增「技能内容有效」判据）。
- **不重判历史**：口径变更 SHALL NOT 使历史候选**重跑**判定、SHALL NOT 一次性重算历史结论；历史
  候选 SHALL 冻结在**其被记录时**的口径（只有「按现口径重新提案」一条前进路径）。
- **不谎报**：拒绝的理由 SHALL 是「口径不符」，SHALL NOT 表述为「未过 review / 测试」或「留出集
  退化」（那些判定在旧口径下并未发生）。
- **review 的生产者**：review SHALL 由**结构化审查者**产出——审的是候选自身的**自洽性**
  （`kind` / `target_plugin` / `delta` 是否互相说得通），产出「通过 / 不通过」判定；审查者 SHALL
  由**组合根注入**，evolution SHALL NOT import 任何 LLM 抽象（照 `author.py` 先例、ADR-0045 同一
  依赖方向：prompt 文本属本域、模型调用由组合根提供）。判定 SHALL **fail-closed**：输出不可解析
  （空输出 / 非判定词表 / 调用失败）SHALL 判**未通过**，SHALL NOT 判通过。review 未通过时
  SHALL NOT 再跑运行时测试（fail-fast：门已未过，不做无谓的子进程开销）。
- **运行时测试的生产者**：运行时测试 SHALL 取自门禁命令**单一真源**（`GATE_COMMANDS`）
  **按标记派生的子集**，SHALL NOT 另立第二份门禁清单（SHALL NOT 复制门禁**命令字符串**）。结晶面
  SHALL 跑两道：`lint`（`ruff check` —— 轻量静态门，语法/风格面回归，亚秒级）与 `test`
  （`pytest -q` —— 行为回归门）；`typecheck`（`pyright`）与 `build`（`uv build`）SHALL NOT 进
  结晶面（类型卫生与打包属**交付面**判据，与「该候选能否发布」无因果关系，且成本高）。**标记**
  命中未注册的门名 SHALL **派生失败**（fail-closed：标记与真源漂移必须炸出来，不得静默少跑一门）。
  任一门未通过 ⇒ 验证门**未通过**。
- **未注入生产者 ⇒ 不得放行**：review 或运行时测试的**生产者未注入**时，系统 SHALL 判验证门
  **未通过**（fail-closed）—— 「无判据」SHALL NOT 被当作「通过」（缺省 `Validator()` 恒通过正是
  本 Requirement 要消除的形态）。
- **技能内容判据（可选装配）**：Validator SHALL 接受可选开关 `require_skill_content`（缺省
  **关**，行为与既有实现逐字一致）。装配为开时，对 `kind="skill"` 的候选：若 `delta` 无有效
  `content`（缺键、非映射、或未通过内容校验）⇒ 验证门**未通过**，review 理由 SHALL 表明「空壳」
  类语义，`test_results` SHALL 为空，且 SHALL NOT 再跑运行时测试（fail-fast）。`kind="plugin"`
  候选 SHALL NOT 受本判据影响。组合根装配内容 writer 时 SHALL **同开**本开关。
- **门的面（诚实）**：结晶面运行时测试跑的是**仓库级**回归门（`GATE_COMMANDS` 子集）—— 与候选
  **内容无关**的基线健康检查（技能级候选本无代码产物）；候选**专属**产物的验证属**实施面**
  （`EvolutionExecutor` 的冻结门），两门**不同源、不互替**。
- **执行面**：结晶面门禁 SHALL 经**独立执行面**（子进程）运行、执行器由组合根注入；单门
  「跑不起来」（工具缺失 / 超时）与「跑失败」（非零退出）SHALL 同样归一为**该门未通过**。

#### Scenario: 过门发布

- **GIVEN** 一个候选提交验证
- **WHEN** review 与运行时测试均通过
- **THEN** GateReport.passed=True，候选进入留出评测

#### Scenario: 未过门丢弃

- **GIVEN** 候选未通过验证门
- **WHEN** Validator 判定失败
- **THEN** 丢弃候选，教训写回 L2/L3

#### Scenario: 旧口径候选不得投放

- **GIVEN** 一条候选台账记录，其口径版本与现口径不符（含落盘早于口径字段引入的旧记录）
- **WHEN** 该候选已获人工确认并要求结晶投放
- **THEN** 结构化拒绝（口径不符），候选**不发布**、其留待确认态不变；理由 SHALL NOT 记为「退化」

#### Scenario: 现口径候选正常投放

- **GIVEN** 一条候选台账记录，其口径版本等于现口径，且门禁与留出评测结论均通过
- **WHEN** 要求结晶投放
- **THEN** 正常结晶（口径校验不阻断）

#### Scenario: 未注入生产者不得放行

- **GIVEN** 一个缺省构造的 Validator（未注入 review 与运行时测试的生产者）
- **WHEN** 校验任意候选
- **THEN** `GateReport.passed=False`，理由 SHALL 表明「生产者未注入 / 无法判定」，
  SHALL NOT 以「空测试集」之类的空判据判通过

#### Scenario: review 判定不可解析不得放行

- **GIVEN** 审查者的输出为空、或不属于判定词表、或调用抛异常
- **WHEN** Validator 取其判定
- **THEN** 判 review **未通过**（fail-closed），SHALL NOT 放行，且 SHALL NOT 为此再跑运行时测试
  （fail-fast）

#### Scenario: 结晶面门禁子集按标记派生

- **GIVEN** 门禁命令单一真源 `GATE_COMMANDS`（`lint` / `typecheck` / `test` / `build`）
- **WHEN** 派生结晶面门禁子集
- **THEN** 得到 `lint` 与 `test` 两道（顺序随单一真源），命令字符串仍只有一份；标记若命中
  `GATE_COMMANDS` 中**不存在**的门名 ⇒ 派生**失败**（抛结构化错误），SHALL NOT 静默忽略

#### Scenario: 运行时测试未过则门未过

- **GIVEN** 候选的 review 通过，但结晶面某道门禁（`lint` 或 `test`）未通过
- **WHEN** Validator 汇总结论
- **THEN** `GateReport.passed=False`、`test_results` 据实标出未通过的门（值恒为布尔），
  `run_cycle` 记候选为 `rejected`、**不发布**

#### Scenario: 结晶面门禁经独立执行面运行

- **GIVEN** 一道结晶面门禁命令
- **WHEN** 执行该门禁
- **THEN** 经子进程运行（非进程内 import 调用）；「跑不起来」（可执行文件缺失 / 超时）与
  「跑失败」（非零退出）同样归一为**该门未通过**，SHALL NOT 使整个验证抛裸异常

#### Scenario: 技能级空壳在装配内容门时不得过门

- **GIVEN** Validator 已装配 `require_skill_content=True`，候选 `kind="skill"` 且 `delta` 无有效
  `content`
- **WHEN** 校验该候选
- **THEN** `GateReport.passed=False`，review 表明空壳类理由，`test_results` 为空，且 SHALL NOT
  再跑运行时测试；同开关下带有效 `content` 的技能候选仍走既有 review + 运行时测试路径
