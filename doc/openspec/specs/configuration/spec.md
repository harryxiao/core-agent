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
引用）用于记忆检索的向量化，未设置或不可达时记忆检索回退词法，不影响启动。

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

#### Scenario: 未配置 embedding 模型回退词法
- **GIVEN** llm 段未设置 `embedding_model`
- **WHEN** 系统启动装配记忆
- **THEN** 记忆检索不注入 embedder，回退词法相似，启动不受影响

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。feature flag SHALL ONLY 作用于**模块装配** —— 即组合根是否构造该模块的实例、是否注册其随装配产生的副作用（技能注册、状态文件读取）、是否接通其 CLI 与 Web UI 入口；SHALL NOT 改变模块**自身**的二级启用开关（如 `pet.enabled` 决定宠物模式是否启用，其缺省与语义不由 feature flag 改变）。**缺省口径**：白名单内的可选模块**未声明即视为开启**（缺省装配，保持既有行为）；只有显式 `false`（yaml `features.<模块>: false`、env `CORE_FEATURE_<模块>`、CLI `--feature <模块>=false`）SHALL 使该模块**完全不装配**。门控名单 SHALL 由组合根以**单一真源**维护（当前为 `pet` / `beast` / `evolution`）；名单外的模块名 SHALL NOT 触发任何装配裁剪，SHALL NOT 影响核心面。

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
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。取值受所属能力规格约束的配置项（如 `permission.mode` 限于权限规格的 read-only / interactive / auto-approve / high-risk-block 四档）SHALL 在校验期拒绝非法取值，并列出可选值。**未知配置段**（顶层段名不在已知段之内——五个结构化段 `llm` / `features` / `im` / `pet` / `judgment`、`ConfigSpec` 声明段、以及寄居 `extra` 但有运行时语义的 `permission`）SHALL **仅告警**：SHALL 产生含该段名的校验告警（指明其被收纳进 `extra` 且未做校验），SHALL NOT 因此阻断启动，SHALL NOT 静默丢弃该段。告警口径 SHALL ONLY 作用于**顶层段名**，不递归校验已知段内部的未知子键。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警

#### Scenario: 非法权限模式被拒
- **GIVEN** 配置将 `permission.mode` 设为四档之外的取值
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并列出可选的四档取值，阻断启动

#### Scenario: 未知配置段仅告警不阻断
- **GIVEN** config.yaml 含一个已知段之外的顶层段（如拼错的 `llmm:`），且其余配置完整
- **WHEN** 系统加载并校验配置
- **THEN** 校验通过、启动不被阻断；同时产生**含该段名**的告警（指明其被收纳进 `extra`、未做校验），该段仍保留在 `extra` 中不丢失
