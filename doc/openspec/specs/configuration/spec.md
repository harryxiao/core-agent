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
系统 SHALL 要求 LLM 配置（provider/model/endpoint/api_key）为必选项，缺失或不完整时阻断启动并报明确错误。

#### Scenario: 缺失 LLM 配置阻断启动
- **GIVEN** config.yaml 缺少 llm 段或 api_key 未解析
- **WHEN** 系统启动加载配置
- **THEN** 启动失败，报明确错误指明缺失的 LLM 配置项

#### Scenario: LLM 配置完整正常启动
- **GIVEN** llm 段包含 provider/model/endpoint/api_key 且 api_key 经 env 引用解析成功
- **WHEN** 系统启动加载配置
- **THEN** 系统正常启动并初始化 LLM 客户端

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。

#### Scenario: 关闭模块不初始化
- **GIVEN** features 段将某模块（如 voice_output）设为 false
- **WHEN** 系统启动
- **THEN** 该模块不加载、不初始化，其依赖资源不占用

#### Scenario: 开启模块正常初始化
- **GIVEN** features 段将某模块设为 true
- **WHEN** 系统启动
- **THEN** 该模块按正常流程初始化

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
系统 SHALL 保证敏感密钥不入 yaml 明文，日志与报错输出对密钥脱敏（对齐 observability）。

#### Scenario: 日志不泄露密钥
- **GIVEN** 配置含 LLM api_key / IM secret 等敏感密钥
- **WHEN** 系统记录日志或抛出配置错误
- **THEN** 密钥值被脱敏（掩码或占位符），不出现明文

#### Scenario: yaml 拒绝明文密钥
- **GIVEN** config.yaml 中直接书写了密钥明文
- **WHEN** 系统做 schema 校验
- **THEN** 校验失败并提示改用 env/keychain 引用

### Requirement: 配置校验与生效
系统 SHALL 对配置做 schema 校验，校验通过才生效；变更即生效；写入失败回滚不留半写状态（对齐 ui spec）。

#### Scenario: schema 校验通过才生效
- **GIVEN** 一份配置待加载
- **WHEN** 系统校验配置
- **THEN** 仅当 schema 校验通过时配置生效，否则拒绝并报错误

#### Scenario: 半写状态回滚
- **GIVEN** 配置变更写入过程失败
- **WHEN** 系统检测到写入不完整
- **THEN** 回滚到变更前完整配置，不留半写状态，并记录告警
