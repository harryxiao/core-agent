# Configuration Specification

## Purpose

配置管理（configuration）能力提供统一的配置源、功能开关与密钥分级：以 config.yaml 为单一收口，CLI 覆盖 + env 覆盖 + 默认值兜底（优先级链 CLI flag > env > config.yaml > 默认值），配置项以 ConfigSpec 为单一真源（每项声明 cli_flag/env_var/default/map_to，暴露面 core/advanced/hidden 分级），模块级 feature flag 开关，LLM 配置为必选项（缺失阻断启动），IM 凭证与敏感密钥经 env/keychain 分级存储，schema 校验 + 变更即生效 + 失败回滚不留半写状态，作为 llm-provider / ui / im / git / judgment 配置语义的上层挂载能力（来源：exploration_findings.md，2026-09-25）。

## Requirements

### Requirement: 配置源与分层
系统 SHALL 以 config.yaml 为单一配置收口，支持 env 环境变量与 CLI 启动参数覆盖 yaml 值，未配置项取默认值兜底；优先级链为 CLI flag > env > config.yaml > 默认值。config.yaml 发现链为 cwd config.yaml → ~/.core-agent/config.yaml（显式 --config 指定路径不回落）；~/.core-agent/.env 作为 env 兜底源（进程 env 优先于 .env）。配置项以 ConfigSpec 为单一真源：每项声明 cli_flag / env_var / default / map_to 与暴露面分级（core/advanced/hidden），CLI flag / env / yaml 三面由 ConfigSpec 生成，非法 map_to 阻断启动。

#### Scenario: env 覆盖 yaml
- **GIVEN** config.yaml 与 env 环境变量同时定义了同一配置项
- **WHEN** 系统加载配置
- **THEN** env 值覆盖 yaml 值，且不影响其他配置项

#### Scenario: 缺省取默认值
- **GIVEN** 某可选配置项在 yaml 与 env 中均未定义
- **WHEN** 系统加载配置
- **THEN** 该配置项取内置默认值，系统正常启动

#### Scenario: CLI 覆盖 env 与 yaml
- **GIVEN** 同一配置项在 CLI flag、env 环境变量与 config.yaml 中均有定义
- **WHEN** 系统加载配置
- **THEN** CLI flag 值最高优先，覆盖 env 与 yaml 值，且不影响其他配置项

#### Scenario: 三面由 ConfigSpec 单一真源生成
- **GIVEN** 一个配置项已通过 ConfigSpec 声明 cli_flag / env_var / map_to
- **WHEN** 生成 CLI 参数面 / env 变量面 / yaml schema
- **THEN** 三面一一对应、无第二真源

#### Scenario: 非法 map_to 阻断启动
- **GIVEN** ConfigSpec 中某配置项 map_to 非法（目标不存在或冲突）
- **WHEN** 启动时校验 ConfigSpec
- **THEN** 阻断启动并报明确错误

#### Scenario: 暴露面分级
- **GIVEN** 配置项标注了暴露面分级（core/advanced/hidden）
- **WHEN** 生成 CLI 帮助与参数面
- **THEN** 按分级暴露，hidden 项不出现于默认帮助

#### Scenario: cwd 缺失回落用户级目录
- **GIVEN** 工作目录不存在 config.yaml，且 ~/.core-agent/config.yaml 存在
- **WHEN** 未显式指定 --config 时加载配置
- **THEN** 读取 ~/.core-agent/config.yaml；显式 --config 指定的路径缺失时不回落，直接报配置文件不存在

#### Scenario: .env 兜底解析密钥引用
- **GIVEN** ~/.core-agent/.env 定义 KEY=VALUE，且进程 env 未定义同名变量
- **WHEN** resolve_secret 解析 ${KEY}
- **THEN** 取 .env 值解析成功；进程 env 存在同名变量时优先于 .env

### Requirement: LLM 提供商配置（必选）
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断
启动并报明确错误；并 SHALL 支持**可选**子项 `embedding_model`（复用 `endpoint` 与密钥
引用）用于记忆检索的向量化，并 SHALL 支持**可选**子项 `embedding_auto`（端点推导开关，
**缺省 `true`**）：显式 `embedding_model` 永远优先；未显式配置且 `embedding_auto` 开启时，
SHALL 按 `endpoint` 主机从**内置已知端点表**推导默认 embedding 模型（精确或子域匹配，
大小写不敏感），表中未命中 SHALL 不推导（有效模型为空）；`embedding_auto` 关闭时 SHALL NOT
推导。`embedding_required` 关闭时，有效 embedding 模型为空或不可达时记忆检索回退词法，
不影响启动；`embedding_auto`
取值口径与 feature flag **同集**（原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，大小写
不敏感、忽略首尾空白），其余取值 SHALL **在校验期拒绝并阻断启动**（错误信息指明键名与
合法取值），SHALL NOT 静默强转。并 SHALL 支持**可选**子项 `embedding_required`
（**缺省 `false`**）：开启时，若**有效 embedding 模型为空**（既未显式配置
`embedding_model`，也未能按 `embedding_auto` 从端点推导），系统 SHALL 在**配置校验期**
阻断启动并报明确错误（错误信息指明键名与可操作提示，SHALL NOT 回显 `endpoint` 或密钥）；
显式模型或端点推导命中任一存在即视为满足。该开关只保证「模型已确定」，SHALL NOT 探测
网络可达性——调用期失败仍按既有路径降级词法。`embedding_required` 取值口径与
`embedding_auto` **同集**，其余取值 SHALL 在校验期拒绝并阻断启动，SHALL NOT 静默强转；
关闭（缺省）时行为与引入前**逐字一致**。并 SHALL 支持
**可选**子项 `context_window`（模型上下文窗口，正整数，`0` = 未配置）作为 token 预算的派生来源
（派生口径见 loop「错误与预算控制」），未配置时 SHALL **按 `model` 从内置已知模型窗口表推导**
（子串匹配，大小写不敏感），表中未命中 SHALL 回落内置缺省，不影响启动；并 SHALL 支持
**可选**子项 `show_thinking`（思考回显开关，**缺省 `false`**）：取值口径与 feature flag
**同集**（原生布尔与 `true/false`·`yes/no`·`on/off`·`1/0`，大小写不敏感、忽略首尾空白），
其余取值 SHALL **在校验期拒绝并阻断启动**（错误信息指明键名与合法取值），SHALL NOT 静默强转。
开启后方经事件面外发思考原文（口径见 llm-provider「默认实现与配置归一化」与 loop「异步流式执行」）；
关闭时系统 SHALL NOT 产出思考事件、三端 SHALL NOT 呈现思考块（行为与既有缺省逐字一致）。
并 SHALL 支持**可选**子项 `timeout`（单次模型调用超时上限，单位**秒**，须 `> 0`，**缺省 `60.0`**）
与 **可选**子项 `max_retries`（调用失败的最大重试次数，须为 `≥ 0` 的**整数**，**缺省 `3`**）：
两者 SHALL 经 CLI flag / env / config.yaml 三面由 ConfigSpec 单一真源生成、参与优先级链
（CLI flag > env > config.yaml > 默认值），解析后由组合根注入 LLM 实现（生效口径见 llm-provider
「模型调用可靠性」）；未配置时 SHALL 取与实现类缺省**逐字一致**的值（`60.0` / `3`），行为零改变。
两者取值 SHALL 在校验期校验并 SHALL NOT 静默强转：`timeout` 取≤ 0 / 非数值 / 布尔，
`max_retries` 取负数 / 小数 / 布尔 / 非数值时 SHALL **阻断启动**并报明确错误（指明键名与合法取值）。

窗口来源的**优先级** SHALL 为：`llm.context_window`（显式配置，`> 0`）**优先于**内置表推导；
显式配置 SHALL NOT 被表值覆盖（用户显式声明永远胜出）。内置表 SHALL 只覆盖**有据可查**的常见模型族
（每项为「模型名子串 → 窗口」并附来源口径），SHALL NOT 猜测未收录模型；表自身 SHALL NOT 引入配置键
（不新增 CLI / env / yaml 面，SHALL NOT 成为第二真源）。

#### Scenario: 缺失 LLM 配置阻断启动
- **GIVEN** config.yaml 缺少 llm 段或 api_key 未解析
- **WHEN** 系统启动加载配置
- **THEN** 启动失败，报明确错误指明缺失的 LLM 配置项

#### Scenario: LLM 配置完整正常启动
- **GIVEN** llm 段包含 provider/model/endpoint/api_key 且 api_key 经 env 引用解析成功
- **WHEN** 系统启动加载配置
- **THEN** 系统正常启动并初始化 LLM 客户端

#### Scenario: 配置 embedding 模型启用语义检索
- **GIVEN** llm 段设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 以该模型构造 embedding 客户端并注入 `MemoryStore`（经单条→批量适配器）

#### Scenario: 未配置时按端点推导默认 embedding 模型
- **GIVEN** llm 段未设置 `embedding_model`（或为空），`embedding_auto` 为缺省开启，
  且 `endpoint` 主机命中内置端点表（如 `open.bigmodel.cn`）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型取该端点的默认模型（如 `embedding-3`），并以之构造 embedding
  客户端注入 `MemoryStore`；显式 `embedding_model` 不被推导值覆盖

#### Scenario: 未配置 embedding 模型回退词法
- **GIVEN** llm 段未设置 `embedding_model`，`embedding_required` 关闭（缺省），且 `endpoint`
  主机不在内置端点表内（如自建代理）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型为空，记忆检索不注入 embedder，回退词法相似，启动不受影响

#### Scenario: 关闭端点推导回退词法
- **GIVEN** llm 段未设置 `embedding_model`，`embedding_auto` 显式关闭（`false`），
  且 `embedding_required` 关闭（缺省）
- **WHEN** 系统启动装配记忆
- **THEN** 有效 embedding 模型为空，记忆检索回退词法（与引入端点推导前逐字一致）

#### Scenario: embedding_auto 取值归一与非法拒绝
- **GIVEN** `llm.embedding_auto` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`
  （大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为开或关；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明
  键名与合法取值，SHALL NOT 静默强转

#### Scenario: embedding_required 空模型阻断启动
- **GIVEN** `llm.embedding_required=true`，未显式配置 `embedding_model`，且 `endpoint` 主机
  不在内置端点表内（有效模型为空）
- **WHEN** 系统加载配置（含热更新 `apply_change`）
- **THEN** 校验失败并阻断启动 / 拒绝该次热更新；错误信息指明 `llm.embedding_required`
  与「有效 embedding 模型为空」，SHALL NOT 回显 `endpoint` 或密钥

#### Scenario: embedding_required 有确定模型时正常启动
- **GIVEN** `llm.embedding_required=true`，且显式配置了 `embedding_model`，或 `endpoint`
  主机命中内置端点表（`embedding_auto` 开启）
- **WHEN** 系统加载配置
- **THEN** 校验通过并正常启动；该开关 SHALL NOT 触发网络可达性探测

#### Scenario: embedding_required 取值归一与非法拒绝
- **GIVEN** `llm.embedding_required` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`
  （大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为开或关；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明
  键名与合法取值，SHALL NOT 静默强转

#### Scenario: context_window 经配置链解析
- **GIVEN** `llm.context_window` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 按优先级链（CLI flag > env > config.yaml > 默认值）解析为整数，供预算派生消费

#### Scenario: context_window 非法取值被拒
- **GIVEN** `llm.context_window` 取值为负数 / 小数 / 布尔 / 非数值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（`0` 或 ≥1 的整数）

#### Scenario: 未配置窗口时按模型推导
- **GIVEN** llm 段未配置 `context_window`（`0`），`model` 为内置表收录的模型族（如 `gpt-4o`
  或 `claude-*`）
- **WHEN** 系统派生 token 预算
- **THEN** 窗口取自内置表（该模型族的实际上下文窗口）⇒ 预算为「推导窗口 − 输出预留」，
  **不再**恒等于内置缺省 `65536`

#### Scenario: 未命中内置表回落缺省
- **GIVEN** llm 段未配置 `context_window`，`model` 不在内置表内
- **WHEN** 系统派生 token 预算
- **THEN** 窗口回落内置缺省 ⇒ 预算与变更前**逐字一致**（`65536`）

#### Scenario: 显式窗口优先于表推导
- **GIVEN** llm 段配置 `context_window: 32768`，`model` 为内置表收录且表值不同
- **WHEN** 系统派生 token 预算
- **THEN** 窗口取显式值 `32768`（**优先于**表推导），预算为 `32768 − output_reserve`

#### Scenario: show_thinking 缺省关
- **GIVEN** llm 段未声明 `show_thinking`（或整段缺省）
- **WHEN** 系统加载配置并装配循环
- **THEN** 思考回显为**关**（`show_thinking=False`）—— 事件面不产 `loop.reasoning`，三端不呈现思考块，与既有缺省**逐字一致**

#### Scenario: show_thinking 取值归一与非法拒绝
- **GIVEN** `llm.show_thinking` 取值为原生布尔、`true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感）
- **WHEN** 系统加载配置
- **THEN** 归一为**开**（真值）或**关**（假值）—— 不得因 `bool("<非空字符串>")` 为真而被当作开启；取值为 `maybe` / 空串 / 映射时校验失败并阻断启动，错误信息指明键名与合法取值

#### Scenario: 超时与重试经配置链解析且缺省不变
- **GIVEN** `llm.timeout` / `llm.max_retries` 经 CLI flag（`--llm.timeout` / `--llm.max-retries`）/
  env（`CORE_LLM_TIMEOUT` / `CORE_LLM_MAX_RETRIES`）/ config.yaml 任一面设置，或**均未设置**
- **WHEN** 系统加载配置并构造 LLM 实现
- **THEN** 按优先级链解析为 `float` / `int` 并注入实现；**均未设置**时取 `60.0` / `3`
  （与实现类缺省**逐字一致**，行为零改变）

#### Scenario: 超时与重试非法取值被拒
- **GIVEN** `llm.timeout` 取值为 `0` / 负数 / 非数值 / 布尔，或 `llm.max_retries` 取值为负数 /
  小数 / 布尔 / 非数值
- **WHEN** 系统加载配置
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（`timeout` 须 > 0，`max_retries`
  须为 ≥ 0 的整数），SHALL NOT 静默强转

### Requirement: 循环预算配置
系统 SHALL 将执行循环的预算参数纳入 ConfigSpec 单一真源：`loop.max_rounds`（单任务最大循环次数，
默认 `20`）与 `loop.output_reserve`（输出预留 token，默认 `8192`）与 `loop.history_turns`（回灌最近 N 轮对话历史，默认 `20`，`0` 表示关闭回灌）与 `loop.compact_steps`（**本轮工具步数**达此值触发上下文压实，默认 `6`）。四项 SHALL 经 CLI flag / env /
config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。
四项取值 SHALL 在校验期校验（`loop.max_rounds` 须为 ≥1 的整数、`loop.output_reserve` 须为 ≥0 的整数、`loop.history_turns` 须为 ≥0 的整数、
`loop.compact_steps` 须为 ≥1 的整数，布尔值非法），并 SHALL 与 `llm.context_window` **交叉校验**：两者同时配置时
`llm.context_window` SHALL 大于 `loop.output_reserve`，否则校验失败并阻断启动。

#### Scenario: 预算参数经 ConfigSpec 声明
- **GIVEN** 配置了 loop 段的 max_rounds / output_reserve
- **WHEN** 系统启动加载配置
- **THEN** 两项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** loop 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `loop.max_rounds` 取 `20`、`loop.output_reserve` 取 `8192`、`loop.history_turns` 取 `20`、`loop.compact_steps` 取 `6`，系统正常启动

#### Scenario: CLI 覆盖 env 与 yaml
- **GIVEN** `loop.output_reserve` 在 CLI flag、env 与 config.yaml 中均有定义
- **WHEN** 系统加载配置
- **THEN** CLI flag 值最高优先，覆盖 env 与 yaml 值

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `loop.max_rounds` 取 `0` / `loop.output_reserve` 取负数，或任一取布尔 / 非整数
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值（不静默强转、不退化成缺省）

#### Scenario: 回灌轮数经 ConfigSpec 声明且受校验

- **GIVEN** `loop.history_turns` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 该值经 ConfigSpec 单一真源解析；取负数 / 小数 / 布尔 / 非数值时校验失败并阻断启动

#### Scenario: 压实步数阈值经 ConfigSpec 声明且受校验

- **GIVEN** `loop.compact_steps` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 该值经 ConfigSpec 单一真源解析并注入组合根构造的压实器；取 `0` / 负数 / 小数 / 布尔 /
  非数值时校验失败并阻断启动

#### Scenario: 窗口与预留交叉校验
- **GIVEN** `llm.context_window` 已配置且不大于 `loop.output_reserve`
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明上下文窗口不敷输出预留

### Requirement: 编排调度配置
系统 SHALL 将编排调度策略纳入 ConfigSpec 单一真源：`orchestration.difficulty_policy`（同波次调度策略，默认 `off`，可选 `off` / `difficulty`）、`orchestration.max_concurrency`（波次并发上限，默认 `4`）、`orchestration.subtask_timeout`（子任务交接超时秒数，默认 `600`；显式 `0` 表示不设限）与 `orchestration.auto_resume`（未完成任务启动自动续跑，默认 `false`）。四项 SHALL 经 CLI flag / env / config.yaml 三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。取值 SHALL 在校验期校验：`orchestration.max_concurrency` 须为 ≥1 的整数（布尔非法），`orchestration.difficulty_policy` 须为 `off` / `difficulty` 之一，`orchestration.subtask_timeout` 须为 ≥0 的整数（布尔非法），`orchestration.auto_resume` 须为布尔或 `true`/`false` 字符串，否则校验失败并阻断启动（不静默强转、不退化成缺省）。`orchestration.subtask_timeout` 的非零值 SHALL 由组合根注入调度器并生效为交接 deadline；`0` 值 SHALL 同样由组合根注入，语义为不设 deadline。`orchestration.auto_resume` 的取值 SHALL 由 `task` 入口读取并决定是否执行启动自动续跑。

#### Scenario: 编排键经 ConfigSpec 声明
- **GIVEN** 配置了 orchestration 段的 difficulty_policy / max_concurrency / subtask_timeout / auto_resume
- **WHEN** 系统启动加载配置
- **THEN** 四项经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省取内置默认值
- **GIVEN** orchestration 段未配置
- **WHEN** 系统启动加载配置
- **THEN** `orchestration.difficulty_policy` 取 `off`、`orchestration.max_concurrency` 取 `4`、`orchestration.subtask_timeout` 取 `600`、`orchestration.auto_resume` 取 `false`，系统正常启动

#### Scenario: 显式 0 仍表示不设限
- **GIVEN** `orchestration.subtask_timeout` 显式配置为 `0`
- **WHEN** 系统启动加载配置并装配调度器
- **THEN** 调度器注入值为 `0`，交接不设 deadline（校验放行，不回退为缺省 `600`）

#### Scenario: 非法取值校验期拒绝
- **GIVEN** `orchestration.max_concurrency` 取 `0` / 负数 / 布尔 / 非整数，或 `orchestration.difficulty_policy` 取集合外的字符串，或 `orchestration.subtask_timeout` 取负数 / 布尔 / 非整数，或 `orchestration.auto_resume` 取非布尔值（如 `maybe`）
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值，不静默强转、不退化成缺省

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。feature flag SHALL ONLY 作用于**模块装配** —— 即组合根是否构造该模块的实例、是否注册其随装配产生的副作用（技能注册、状态文件读取）、是否接通其 CLI 与 Web UI 入口；SHALL NOT 改变模块**自身**的二级启用开关（如 `pet.enabled` 决定宠物模式是否启用，其缺省与语义不由 feature flag 改变）。**缺省口径**：白名单内的可选模块**未声明即视为开启**（缺省装配，保持既有行为）；只有显式 `false`（yaml `features.<模块>: false`、env `CORE_FEATURES_<模块>`、CLI `--feature <模块>=false`）SHALL 使该模块**完全不装配**。门控名单（**缺省装配**）与**缺省关名单**（**缺省关**，fail-closed）SHALL 均由组合根以**单一真源**维护（当前分别为 `pet` / `beast` / `evolution` 与 `evolution_executor`），二者之并即**已知模块名集合**（供未知开关名告警）；两个名单之外的模块名 SHALL NOT 触发任何装配裁剪，SHALL NOT 影响核心面。
**第二条极性（缺省关）**：**缺省关名单**内的可选能力**未声明即视为关闭** —— 其装配判据 SHALL 是「显式开启查询」（`is_enabled`，缺省 `false`），只有显式 `true`（yaml / env / CLI 三面同口径，取值归一与校验规则同上）SHALL 使其装配，关时 SHALL NOT 构造其任何实例、不产生装配期副作用。**两种极性 SHALL 各由一份**独立**名单承载**：SHALL NOT 以同一份名单表达两种缺省语义，亦 SHALL NOT 因新增一种极性而改变既有门控名单的缺省语义。
三条输入通道 SHALL **全部生效**（yaml 段 / env / CLI flag），且取值 SHALL **三面同口径**：接受原生布尔与 `true/false`、`yes/no`、`on/off`、`1/0`（大小写不敏感、忽略首尾空白），其余取值（如 `maybe`、空串、映射）SHALL **在校验期拒绝并阻断启动**，错误信息指明键名与合法取值；SHALL NOT 经 `bool()` 之类**静默强转**（`bool("off")` 为真会把「显式关闭」当作开启）。CLI 面 `--feature <模块>[=<布尔>]` SHALL 参与优先级链（CLI flag > env > config.yaml > 缺省），裸名（`--feature <模块>`）SHALL 视为开启。

#### Scenario: 关闭模块不初始化
- **GIVEN** features 段将某模块（如 voice_output）设为 false
- **WHEN** 系统启动
- **THEN** 该模块不加载、不初始化，其依赖资源不占用

#### Scenario: 开启模块正常初始化
- **GIVEN** features 段将某模块设为 true
- **WHEN** 系统启动
- **THEN** 该模块按正常流程初始化

#### Scenario: 未声明即装配（缺省开）
- **GIVEN** 配置的 features 段未声明某门控名单内模块（或无 features 段）
- **WHEN** 系统启动装配
- **THEN** 该模块按正常流程装配（与显式 `true` 等价）

#### Scenario: 关闭模块的装配面为空
- **GIVEN** features 段将门控名单内某模块设为 false（如 `pet: false`）
- **WHEN** 系统启动装配
- **THEN** 组合根不构造该模块的任何实例、不产生其装配期副作用（不注册其技能、不读其状态文件），运行系统在该面的字段为空，且该模块的 CLI 入口拒绝执行并说明原因

#### Scenario: feature flag 不改变模块自身启用开关
- **GIVEN** `features.pet` 未声明（缺省开）而 `pet.enabled` 为 false
- **WHEN** 系统启动装配并调用 `pet` CLI
- **THEN** 模块**已装配**（装配面非空），`pet` CLI 仍按 `pet.enabled` 报「未启用」—— 两级开关各管各的，互不覆盖

#### Scenario: 核心模块不受 feature flag 影响
- **GIVEN** features 段把门控名单内全部模块设为 false
- **WHEN** 系统启动装配
- **THEN** 循环 / 记忆 / 工具 / 技能路由等核心面照常装配，系统仍可正常跑一轮

#### Scenario: CLI 面覆盖 yaml 与环境
- **GIVEN** yaml 将某门控名单内模块设为 `false`（或 env 设为其等价写法）
- **WHEN** 以 `--feature <模块>=true` 启动（或反之：yaml `true` + `--feature <模块>=false`）
- **THEN** 以 CLI flag 为准 —— 该模块按其装配/裁剪，证明 CLI 面**真的**参与装配判定

#### Scenario: 常见假值写法归一为关闭
- **GIVEN** yaml 将某模块写作 `off` / `no` / `0` / 加引号的 `"false"`
- **WHEN** 系统加载配置
- **THEN** 该取值归一为**假**（模块不装配）—— 不得因 `bool("<非空字符串>")` 为真而被当作开启

#### Scenario: 非法取值校验期拒绝
- **GIVEN** 某模块的 feature flag 取值为 `maybe` / 空串 / 映射（yaml / env / CLI 任一面）
- **WHEN** 配置校验运行
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值集合（不静默强转、不退化成缺省）

#### Scenario: env 面以复数前缀生效
- **GIVEN** 环境变量 `CORE_FEATURES_<模块>=false`（或 `true`）
- **WHEN** 系统加载配置并装配
- **THEN** 该取值参与优先级链并支配装配 —— env 面前缀为**复数** `CORE_FEATURES_`，与 yaml 段名 `features` 同源

#### Scenario: 缺省关的可选能力未声明即不装配
- **GIVEN** 配置的 features 段未声明缺省关名单内的某能力（如 `evolution_executor`，或无 features 段）
- **WHEN** 系统启动装配
- **THEN** 该能力**不装配**（组合根不构造其任何实例、不产生装配期副作用），其操作面入口拒绝执行并说明原因 —— 与显式 `false` 等价，**不**因「未声明」而被当作开启

#### Scenario: 缺省关的可选能力显式 true 才装配
- **GIVEN** features 段将该缺省关能力显式设为 `true`（或经 env `CORE_FEATURES_<模块>=true` / CLI `--feature <模块>=true`）
- **WHEN** 系统启动装配
- **THEN** 该能力被装配（装配面非空），且**既有门控名单内模块的缺省语义逐字不变**（新增极性不改动原有名单的缺省开口径）

#### Scenario: 两个名单互为已知（未知开关名仍告警）
- **GIVEN** features 段声明一个**两个名单都不含**的模块名
- **WHEN** 配置校验运行
- **THEN** 仍产出「未知功能开关」告警（仅告警不阻断）—— 已知模块名集合 = 缺省装配名单 ∪ 缺省关名单

### Requirement: IM 接入配置
系统 SHALL 支持 IM 接入配置（gateway/账户/ID/密钥），其中密钥经 env/keychain 分级存储，不落 yaml 明文。

#### Scenario: IM 凭证经 keychain 存储
- **GIVEN** im 段配置了 gateway/corp_id 与 secret 引用
- **WHEN** 系统加载 IM 接入配置
- **THEN** secret 从 env/keychain 解析，yaml 中仅存 `${VAR}` 引用

#### Scenario: IM 可选不配置
- **GIVEN** 未配置 im 段
- **WHEN** 系统启动
- **THEN** IM 网关不初始化，其余功能不受影响

### Requirement: 决策模型配置
系统 SHALL 将决策模型（judgment）接入配置纳入 ConfigSpec 单一真源：judgment.provider / judgment.model / judgment.base_url / judgment.api_key / judgment.confidence_threshold；api_key 经 env/keychain 分级存储不落 yaml 明文，未配置时决策能力关闭、主 LLM 兜底。

#### Scenario: 决策模型配置经 ConfigSpec 声明
- **GIVEN** 配置了 judgment 段的 provider/model/base_url/api_key/confidence_threshold
- **WHEN** 系统启动加载配置
- **THEN** 配置经 ConfigSpec 单一真源解析（优先级链 CLI flag > env > config.yaml > 默认值），暴露面 core/hidden 分级

#### Scenario: 决策模型密钥不入 yaml 明文
- **GIVEN** judgment.api_key 为敏感密钥
- **WHEN** 系统做 schema 校验
- **THEN** api_key 必须为 `${VAR}` 引用，yaml 明文被拒绝

#### Scenario: 未配置决策模型回退主 LLM
- **GIVEN** 未配置 judgment 段或 provider 为空
- **WHEN** 系统需要决策
- **THEN** 决策能力关闭，回退主 LLM 兜底

### Requirement: 宠物模式配置
系统 SHALL 将宠物模式（pet）接入配置纳入 ConfigSpec 单一真源：pet.enabled（总开关）/ pet.persons_dir（多宠物 persona 目录）；默认关闭，开启后 PetSession 构造时经 resolve() 优先级链（CLI flag > env > config.yaml > 默认值）读取对应 pet.md 人格，禁止 pet 配置绕过 ConfigSpec 另起解析。

#### Scenario: pet 配置经 ConfigSpec 声明
- **GIVEN** 配置了 pet 段的 enabled / persons_dir
- **WHEN** 系统启动加载配置
- **THEN** pet.enabled / pet.persons_dir 经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应

#### Scenario: pet 默认关闭不激活
- **GIVEN** 未配置 pet 段或 pet.enabled 为 false
- **WHEN** 系统启动
- **THEN** 宠物模式不激活，其余功能不受影响

#### Scenario: persons_dir 多宠物加载
- **GIVEN** pet.enabled 开启且 pet.persons_dir 指向含多个 <name>.md 的目录
- **WHEN** PetSession 构造 / 激活宠物
- **THEN** 经 resolve() 优先级链读取 persons_dir，加载对应 pet.md 人格（每只宠物一个文件）

### Requirement: 密钥分级与安全
系统 SHALL 保证敏感密钥不入 yaml 明文，日志与报错输出对密钥脱敏（对齐 observability）。所有密钥引用（`llm.api_key` / `im.secret` / `judgment.api_key`）SHALL 在 schema 校验期**同口径**校验：非空且可经 env/keychain 解析，否则校验失败并阻断启动。

- **对称校验**：SHALL NOT 出现「主 LLM 强制非空且可解析、IM / 决策模型密钥放行空值或不可解析引用」的不对称。
- **可选段语义**：段未配置时 SHALL NOT 参与校验（IM 段缺失即不校验 `im.secret`）；决策模型段仅在 `provider` 非空（能力启用）时校验 `judgment.api_key`。

#### Scenario: 日志不泄露密钥
- **GIVEN** 配置含 LLM api_key / IM secret 等敏感密钥
- **WHEN** 系统记录日志或抛出配置错误
- **THEN** 密钥值被脱敏（掩码或占位符），不出现明文

#### Scenario: yaml 拒绝明文密钥
- **GIVEN** config.yaml 中直接书写了密钥明文
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并提示改用 env/keychain 引用

#### Scenario: 空或不可解析的密钥引用被拒
- **GIVEN** IM 段已配置但 secret 为空，或其引用的环境变量 / keychain 条目不存在
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并指明该密钥引用缺失或无法解析，阻断启动

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。取值受所属能力规格约束的配置项（如 `permission.mode` 限于权限规格的 read-only / interactive / auto-approve / high-risk-block 四档）SHALL 在校验期拒绝非法取值，并列出可选值。**写回 yaml 的变更 SHALL 记录可逆效应**：`write_patch` 落盘前 SHALL 向效应账注册一条撤销（恢复**写盘前的 yaml 原文**），并与内存变更（`apply_change`）记在**同一 trace** 之下——按该 trace 回滚时 SHALL 使**磁盘态与内存态一并回退**，SHALL NOT 只回退其一而留下内存/磁盘不一致。**未知配置段**（顶层段名不在已知段之内——五个结构化段 `llm` / `features` / `im` / `pet` / `judgment`、`ConfigSpec` 声明段、以及寄居 `extra` 但有运行时语义的 `permission`）SHALL **仅告警**：SHALL 产生含该段名的校验告警（指明其被收纳进 `extra` 且未做校验），SHALL NOT 因此阻断启动，SHALL NOT 静默丢弃该段。告警口径 SHALL ONLY 作用于**顶层段名**，不递归校验已知段内部的未知子键；**唯一例外是 `features` 段**——其子键是**模块名**，SHALL 以**组合根维护的已知模块名集合**（经注入提供）校验：子键不在集合内时 SHALL 产生含该子键名的告警（指明疑似拼写错误、模块名拼错将静默不生效），SHALL NOT 因此阻断启动；已知模块名集合**未注入**时 SHALL NOT 校验 `features` 段子键。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警

#### Scenario: 写回可逆：回滚恢复磁盘原文
- **GIVEN** 已加载配置，且 `apply_change` + `write_patch` 已把一个变更同时生效到内存与 config.yaml
- **WHEN** 对该变更所在的 trace 回滚
- **THEN** config.yaml 恢复为**写盘前的原文**（逐字节），内存配置同时回退 ⇒ 磁盘态与内存态**一致**，且 SHALL NOT 留下「内存已回退、磁盘仍是新值」的不一致

#### Scenario: 非法权限模式被拒
- **GIVEN** 配置将 `permission.mode` 设为四档之外的取值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并列出可选的四档取值，阻断启动

#### Scenario: 未知配置段仅告警不阻断
- **GIVEN** config.yaml 含一个已知段之外的顶层段（如拼错的 `llmm:`），且其余配置完整
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该段名**的告警（指明其被收纳进 `extra`、未做校验），该段仍保留在 `extra` 中不丢失

#### Scenario: features 段未知模块名仅告警
- **GIVEN** 已注入已知模块名集合（如 `pet` / `beast` / `evolution`），且 config.yaml 的 `features` 段含一个集合之外的子键（如拼错的 `peet:`）
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该子键名**的告警（指明疑似拼写、模块名拼错将静默不生效）

#### Scenario: 未注入已知模块名时不校验子键
- **GIVEN** 未注入已知模块名集合，且 config.yaml 的 `features` 段含任意自定义子键
- **WHEN** 系统加载并校验配置
- **THEN** 不产生 `features` 子键告警（与既有顶层段名口径一致）

### Requirement: 记忆容量配置

系统 SHALL 将 L2 活跃层容量纳入 ConfigSpec 单一真源：`memory.l2_soft_max_entries`
（L2 活跃层软上限条目数，缺省**未设置** = 不启用）。该键 SHALL 经 CLI flag
`--memory-l2-soft-max-entries` / env `CORE_MEMORY_L2_SOFT_MAX_ENTRIES` / config.yaml
`memory:` 段三面一一对应生成，参与优先级链（CLI flag > env > config.yaml > 默认值）。
取值 SHALL 为 **≥1 的整数**；`bool` / 小数 / 非数值 / `0` / 负数 SHALL 归一为**未启用**
（`None`）。`memory` 段为非结构化段 ⇒ 非法取值 SHALL NOT 阻断启动（与同段其余键同口径）。
配置值 SHALL 由组合根注入 `MemoryStore(l2_soft_max_entries=...)`；未配置或归一为未启用时
SHALL NOT 注入上限，写入路径行为与引入本键前逐字一致。

#### Scenario: 容量键经 ConfigSpec 声明
- **GIVEN** 配置了 `memory.l2_soft_max_entries`
- **WHEN** 系统启动加载配置
- **THEN** 该键经 ConfigSpec 单一真源解析，CLI flag / env / yaml 三面一一对应、无第二真源

#### Scenario: 缺省未启用
- **GIVEN** `memory` 段未配置 `l2_soft_max_entries`
- **WHEN** 系统启动装配记忆
- **THEN** 组合根以 `l2_soft_max_entries=None` 构造 `MemoryStore`，写入不受任何上限检查

#### Scenario: 配置值注入组合根
- **GIVEN** `memory.l2_soft_max_entries` 经任一面设为 `128`
- **WHEN** 系统启动装配记忆
- **THEN** 组合根以 `l2_soft_max_entries=128` 构造 `MemoryStore`，写入后按软上限收口

#### Scenario: 非法取值归一为未启用
- **GIVEN** `memory.l2_soft_max_entries` 取 `0` / 负数 / 布尔 / 小数 / 非数值
- **WHEN** 系统启动加载配置
- **THEN** 该键归一为未启用（`None`），启动不阻断，写入路径与未配置时一致

### Requirement: 工具注入范围配置
系统 SHALL 支持配置项 `loop.tool_scope` 选择推理请求中工具参数 schema 的注入范围，并经
CLI flag `--loop.tool-scope` / 环境变量 `CORE_LOOP_TOOL_SCOPE` / config.yaml `loop.tool_scope`
三面由 ConfigSpec **单一真源**生成、参与优先级链（CLI flag > env > config.yaml > 默认值）。

合法取值为 `all` 与 `auto`（大小写不敏感、忽略首尾空白），**缺省 `auto`**。其余取值
（含原生布尔、非字符串、空串）SHALL **在校验期拒绝并阻断启动**，错误信息 SHALL 指明键名与
合法取值，SHALL NOT 静默强转或回落缺省。`all` SHALL 保持引入本键前的全量注入行为
（kill-switch）；`auto` 的注入语义见 loop「工具参数按需注入」。

#### Scenario: 缺省为 auto
- **GIVEN** config.yaml / env / CLI 均未设置 `loop.tool_scope`
- **WHEN** 系统加载配置
- **THEN** 访问器返回 `auto`

#### Scenario: 三面覆盖
- **GIVEN** `loop.tool_scope` 经 CLI flag / env / config.yaml 任一面设置
- **WHEN** 系统加载配置
- **THEN** 按优先级链解析为归一后的 `all` 或 `auto`

#### Scenario: 非法取值阻断启动
- **GIVEN** `loop.tool_scope` 取值为 `maybe` / 空串 / 布尔 / 非字符串
- **WHEN** 系统加载配置
- **THEN** 校验失败并阻断启动，错误信息指明 `loop.tool_scope` 与合法取值（`all` / `auto`）

### Requirement: 无人值守配置项

系统 SHALL 将无人值守护栏纳入 ConfigSpec 单一真源，三面（CLI flag / env / config.yaml）
一一对应并参与优先级链（CLI flag > env > config.yaml > 默认值）：

- `permission.auto_approve_coeffects`（`--permission.auto-approve-coeffects` /
  `CORE_PERMISSION_AUTO_APPROVE_COEFFECTS`，默认空串）：auto-approve 档的 coeffect 允许面，
  逗号分隔；空串 SHALL 表示不限制（既有全放行行为）。
- `orchestration.task_timeout`（`--orchestration.task-timeout` /
  `CORE_ORCHESTRATION_TASK_TIMEOUT`，默认 `0`）：整任务墙钟时限秒数；`0` SHALL 表示不设限。
- `orchestration.task_token_budget`（`--orchestration.task-token-budget` /
  `CORE_ORCHESTRATION_TASK_TOKEN_BUDGET`，默认 `0`）：整任务 token 预算；`0` SHALL 表示关闭。
- `orchestration.failure_notify_file`（`--orchestration.failure-notify-file` /
  `CORE_ORCHESTRATION_FAILURE_NOTIFY_FILE`，默认空串）：失败通知 JSONL 文件路径；
  空串 SHALL 表示不落盘。

取值 SHALL 在校验期校验，非法取值 SHALL 阻断启动（不静默兜底、不退化成缺省）：
允许面条目 SHALL 形如 `namespace:action`（小写字母开头，允许数字 / `_` / `-`；空项忽略）；
`task_timeout` 与 `task_token_budget` SHALL 为 ≥0 的整数（布尔非法）；
`failure_notify_file` SHALL 为字符串（空串合法）。四项访问器 SHALL 由组合根/入口消费，
配置未加载时 SHALL 分别回落 `[]` / `0` / `0` / `""`（等价于关闭）。

#### Scenario: 缺省全关闭

- **GIVEN** 配置未声明任何无人值守项
- **WHEN** 读取四项访问器
- **THEN** 返回值 SHALL 为 `[]` / `0` / `0` / `""`
- **AND THEN** 权限判定、任务时限与失败通知行为 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 配置 `orchestration.task_timeout: 30`，env 设
  `CORE_ORCHESTRATION_TASK_TIMEOUT=60`，CLI 传 `--orchestration.task-timeout 90`
- **WHEN** 加载配置
- **THEN** `orchestration_task_timeout()` SHALL 返回 `90`

#### Scenario: 非法取值阻断启动

- **GIVEN** `orchestration.task_token_budget: -1`（或 `task_timeout: 2.5`、
  `permission.auto_approve_coeffects: filesystem` 缺少 `namespace:action` 形态、
  `failure_notify_file: true`）
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明具体键与合法形态

#### Scenario: 允许面解析

- **GIVEN** `permission.auto_approve_coeffects: filesystem:write, process:spawn,filesystem:write`
- **WHEN** 读取 `permission_auto_approve_coeffects()`
- **THEN** SHALL 返回 `["filesystem:write", "process:spawn"]`（去空白、去重、保序）

### Requirement: 失败通知 webhook 配置

系统 SHALL 将 `orchestration.failure_notify_webhook` 纳入 ConfigSpec 单一真源，三面
（CLI flag `--orchestration.failure-notify-webhook` / env
`CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK` / config.yaml）一一对应并参与优先级链
（CLI > env > config.yaml > 默认值）。默认值 SHALL 为空串，表示不推送（行为与引入前一致）。

非空取值 SHALL 为 `http` 或 `https` 的绝对 URL（scheme 与 host 均非空）；其他 scheme
（含 `file` / `ftp`）、缺 host、非字符串取值 SHALL 在校验期判为错误并**阻断启动**。
错误信息 SHALL 指明键名与合法形态，SHALL NOT 回显 URL 值（URL 可能内嵌令牌）。
访问器 `orchestration_failure_notify_webhook()` SHALL 在配置未加载时回落空串。

#### Scenario: 缺省不推送

- **GIVEN** 配置未声明 `orchestration.failure_notify_webhook`
- **WHEN** 读取 `orchestration_failure_notify_webhook()`
- **THEN** SHALL 返回空串，任务失败时 SHALL NOT 发起任何网络请求

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 配置 webhook A，env 配置 webhook B，CLI 传 webhook C
- **WHEN** 加载配置
- **THEN** `orchestration_failure_notify_webhook()` SHALL 返回 C

#### Scenario: 非法 URL 阻断启动

- **GIVEN** `orchestration.failure_notify_webhook` 为 `file:///tmp/x`（或 `ftp://h/x`、
  `https://`、布尔值）
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明键名与 `http(s)` 形态
- **AND THEN** 错误信息 SHALL NOT 包含该 URL 的值

### Requirement: 自动放行的命令允许面配置

系统 SHALL 将 `permission.auto_approve_commands` 纳入 ConfigSpec 单一真源，三面（CLI flag
`--permission.auto-approve-commands` / env `CORE_PERMISSION_AUTO_APPROVE_COMMANDS` /
config.yaml）一一对应并参与优先级链（CLI > env > config.yaml > 默认值）。默认值 SHALL 为
空串，表示不限制（行为与引入前一致）。

取值 SHALL 为逗号（含全角 `，`）分隔的条目列表；条目形态为 `tools.code_run:<命令前缀>`：
工具部分 SHALL 为 `tools.code_run`（当前唯一执行任意命令的工具），前缀 SHALL 非空（去首尾
空白后）且 SHALL NOT 含 shell 元字符（`;` `|` `&` `$` 反引号 `<` `>` `(` `)`、换行 /
回车）。空条目 SHALL 被忽略；重复条目 SHALL 去重并保序。任一非法条目 SHALL 在校验期判为
错误并**阻断启动**，错误信息 SHALL 指明键名与合法形态，SHALL NOT 回显条目取值。

访问器 `permission_auto_approve_commands()` SHALL 返回 `{工具 id: (前缀, ...)}`；配置未加载
或未配置时 SHALL 返回空映射。

#### Scenario: 缺省不限制

- **GIVEN** 配置未声明 `permission.auto_approve_commands`
- **WHEN** 读取 `permission_auto_approve_commands()`
- **THEN** SHALL 返回空映射，auto-approve 档的命令执行 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml / env / CLI 同时配置不同的命令允许面
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 CLI 的取值

#### Scenario: 非法条目阻断启动

- **GIVEN** 任一条目缺少 `:`、工具 id 不是 `tools.code_run`、前缀为空、或前缀含 shell 元字符
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明键名与合法形态
- **AND THEN** 错误信息 SHALL NOT 包含该条目或前缀的取值

#### Scenario: 全角逗号与去重

- **GIVEN** 取值为 `tools.code_run:git status，tools.code_run:pytest, tools.code_run:git status`
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 `{"tools.code_run": ("git status", "pytest")}`（去重、保序）

### Requirement: 工作树隔离配置

系统 SHALL 将 `orchestration.worktree_isolation` 纳入 ConfigSpec 单一真源，三面（CLI flag
`--orchestration.worktree-isolation` / env `CORE_ORCHESTRATION_WORKTREE_ISOLATION` /
config.yaml 的 `orchestration.worktree_isolation`）一一对应并参与优先级链
（CLI > env > config.yaml > 默认值）。默认值 SHALL 为 `false`，即不启用子 Agent 工作树隔离，
行为与引入前一致。

取值 SHALL 接受布尔值或 `true` / `false` 字符串；其他取值 SHALL 在校验期判为错误并**阻断
启动**，错误信息 SHALL 指明键名与合法取值，SHALL NOT 静默降级。访问器
`orchestration_worktree_isolation()` SHALL 在配置未加载或未配置时返回默认值 `false`。

仅当该配置为 true 时，组合根 SHALL 构造工作树管理器并在主工具面注册
`tools.worktree.list` / `tools.worktree.discard`；为 false 时 SHALL NOT 构造管理器，
SHALL NOT 注册上述工具，SHALL NOT 创建状态目录下的工作树根。

#### Scenario: 缺省关闭

- **GIVEN** 配置未声明 `orchestration.worktree_isolation`
- **WHEN** 读取访问器并构造运行时
- **THEN** 访问器 SHALL 返回 false，运行时 SHALL 不含工作树管理器与工作树工具
- **AND THEN** 委托行为与持久化字段 SHALL 与引入前逐字一致

#### Scenario: 三面取值与优先级

- **GIVEN** yaml 为 false、env 为 false、CLI 为 true
- **WHEN** 加载配置
- **THEN** 访问器 SHALL 返回 true（CLI 优先）
- **AND THEN** 运行时 SHALL 组装工作树管理器并注册两个工作树工具

#### Scenario: 非法取值阻断启动

- **GIVEN** 取值为 `maybe` 或无法解释为布尔的其他字符串
- **WHEN** 加载配置
- **THEN** 校验 SHALL 失败并阻断启动，错误信息 SHALL 指明
  `orchestration.worktree_isolation` 与合法取值
- **AND THEN** SHALL NOT 回退为默认值继续启动

### Requirement: 已知模型能力告警

配置校验 SHALL 在内置能力表命中时产生**仅告警、不阻断**的提示：

- `loop.output_reserve` **大于**该模型已知最大输出 ⇒ SHALL 告警，说明请求将按模型上限钳制
  （钳制口径见 llm-provider「请求侧输出上限按预留注入」）；
- `llm.reasoning_effort` 非空且该模型**已知不支持**该字段 ⇒ SHALL 告警，说明仍会照常下发、
  端点若不接受会报错（本 change SHALL NOT 静默丢弃用户显式配置）。

表未收录、或对应能力未知（最大输出 `0` / 支持性 `None`）⇒ SHALL NOT 产生该类告警，既有校验结果
逐字不变。告警 SHALL NOT 回显端点或密钥；SHALL NOT 改变校验通过与否。

#### Scenario: 输出预留高于已知上限仅告警

- **GIVEN** `llm.model = gpt-4-turbo`（已知最大输出 `4096`），`loop.output_reserve` 取缺省 `8192`
- **WHEN** 配置校验
- **THEN** 校验通过（不阻断启动），并产生含 `output_reserve` 与已知模型上限的告警

#### Scenario: 已知不支持的推理档位仅告警

- **GIVEN** `llm.model = gpt-4o`（已知不支持 `reasoning_effort`），`llm.reasoning_effort = low`
- **WHEN** 配置校验
- **THEN** 校验通过，并产生含 `reasoning_effort` 与模型名的告警；配置值不被丢弃

#### Scenario: 未收录模型不产生能力告警

- **GIVEN** `llm.model` 未收录于能力表
- **WHEN** 配置校验
- **THEN** 不产生本要求的告警，既有校验告警集合与通过与否逐字不变

### Requirement: 沉淀配置项

系统 SHALL 经 `ConfigSpec` **单一真源**声明以下两项（CLI flag / env / YAML 三面同源）：

| 键 | CLI | env | 缺省 |
|---|---|---|---|
| `notes.candidate_distill` | `--notes-candidate-distill` | `CORE_NOTES_CANDIDATE_DISTILL` | `true` |
| `notes.candidate_auto_promote` | `--notes-candidate-auto-promote` | `CORE_NOTES_CANDIDATE_AUTO_PROMOTE` | `false` |

两项 SHALL 以宽容 bool 归一（与 feature flag 同集：`true/1/yes/on` 为真，其余为假）。
`notes.candidate_distill=false` 时运行时 SHALL **不产候选、零模型调用**（沉淀链路整体关闭）；
`notes.candidate_auto_promote=true` 时候选 `support ≥ 2` 才尝试自动晋升（冲突保留候选）。

`config set notes.<key> <value>` SHALL 可写（`_key_to_patch` 允许 `notes.` 前缀）。

#### Scenario: 缺省值
- **GIVEN** 未配置 `notes` 段
- **WHEN** 运行时读取两项
- **THEN** `candidate_distill == true`、`candidate_auto_promote == false`

#### Scenario: 关闭提炼不产候选
- **GIVEN** `notes.candidate_distill=false`
- **WHEN** 一轮成功写效应任务收尾
- **THEN** 不调用提炼器、候选区无变化

#### Scenario: CLI 写配置
- **GIVEN** 用户执行 `config set notes.candidate_auto_promote true`
- **WHEN** 重新读取配置
- **THEN** 该键为 `true`（env / YAML 同名键按既有优先级覆盖）

#### Scenario: 非法值归一为关
- **GIVEN** `notes.candidate_auto_promote` 被写成任意非真值字符串
- **WHEN** 运行时读取
- **THEN** 视为 `false`（不自动晋升）

### Requirement: 后台派生调用的超时与重试配置

系统 SHALL 将**后台派生模型调用**（组合根 `_llm_text` 接缝：会话摘要、关键事实 / 关系 /
情景归纳、SOP 提炼、沉淀候选蒸馏、进化 review / patch author）的超时与重试纳入 ConfigSpec
单一真源：

- `llm.background_timeout`（单次后台调用超时上限，单位**秒**，须 `> 0`，**缺省 `60.0`**）；
- `llm.background_max_retries`（后台调用失败的最大重试次数，须为 `≥ 0` 的**整数**，
  **缺省 `0`**）。

两键 SHALL 经 CLI flag / env / config.yaml 三面一一对应生成，参与优先级链
（CLI flag > env > config.yaml > 默认值），解析后由组合根注入**独立于主 provider 的**
后台 provider。主 provider 的 `llm.timeout` / `llm.max_retries` 语义与缺省 SHALL 保持不变；
用户交互调用（规划、校验、流式回复）SHALL 继续使用主 provider。

非法取值 SHALL 在校验期**阻断启动**并报明确错误（指明键名与合法取值），SHALL NOT 静默强转。

#### Scenario: 三键三面声明

- **GIVEN** 配置系统加载
- **WHEN** 读取 ConfigSpec
- **THEN** 存在 `llm.background_timeout` / `llm.background_max_retries`，且
  CLI flag、env、`map_to` 三面齐备

#### Scenario: 缺省值

- **GIVEN** 未配置两键
- **WHEN** 加载配置
- **THEN** `llm.background_timeout == 60.0`、`llm.background_max_retries == 0`

#### Scenario: 非法取值阻断

- **GIVEN** `llm.background_timeout` 取 `0` / 负数 / 非数值 / 布尔，或
  `llm.background_max_retries` 取负数 / 小数 / 非数值 / 布尔
- **WHEN** 配置校验
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值

#### Scenario: 组合根注入独立后台 provider

- **GIVEN** 配置 `background_timeout = 30`、`background_max_retries = 1`
- **WHEN** 装配运行时
- **THEN** 后台 provider 以 `(30.0, 1)` 构造；主 provider 的 `(timeout, max_retries)` 不因此改变

### Requirement: 压实耗时上限配置

系统 SHALL 将轮内压实的耗时上限于 ConfigSpec 单一真源中声明：

- `loop.compact_timeout`（单次轮内压实总时长上限，单位**秒**，须 `> 0`，**缺省 `60.0`**）；
- 该键 SHALL 经 CLI flag / env / config.yaml 三面一一对应生成，参与既有优先级链；
- 组合根 SHALL 把该值注入**全部** `DefaultLoop` 实例（主 / 子 Agent / 神兽 / 宠物）；
- 非法取值（`0` / 负数 / 非数值 / 布尔）SHALL 在校验期阻断启动。

该键只影响轮内压实的等待与协作式截止；SHALL NOT 改变压实产物、触发阈值
（`loop.compact_steps`）或记忆维护节拍。

#### Scenario: 缺省值

- **GIVEN** 未配置 `loop.compact_timeout`
- **WHEN** 加载配置
- **THEN** 取 `60.0`，轮内压实上限为 60 秒

#### Scenario: 注入全部 loop

- **GIVEN** 配置 `loop.compact_timeout = 15`
- **WHEN** 装配运行时并检查四个 `DefaultLoop`
- **THEN** 每个 loop 的压实上限均为 15 秒

#### Scenario: 非法取值阻断

- **GIVEN** `loop.compact_timeout` 取 `0` / 负数 / 非数值 / 布尔
- **WHEN** 配置校验
- **THEN** 校验失败并阻断启动，错误信息指明键名与合法取值
