# configuration spec delta — env 前缀口径订正

**把规格里写错的 env 前缀订正为实现口径，并补齐 `0072` 归档时丢失的一段正文。**

规格「功能开关（feature flag）」正文列三条输入通道，env 面写作 `CORE_FEATURE_<模块>`（**单数**）；
实现（`src/core/configuration/manager.py:169` `_FEATURE_ENV_PREFIX = "CORE_FEATURES_"`）与
`doc/00-product/user-guide.md`、`coding-plan/cli-contract-baseline.md` 一致用**复数** `CORE_FEATURES_<模块>`
（与段名 `features` 同源）。实测：`CORE_FEATURES_BEAST=false` 生效；照规格字面写 `CORE_FEATURE_BEAST=false`
则**静默无效**（不裁剪、不报错）。

**裁决（账本 E24）**：**改规格与文档向实现靠拢** —— 零代码变更、零对外破坏。改实现为单数是**对外可观测**的
破坏性重命名（既有部署 / CI 的 env 失效），而现实现与段名自洽；规格的单数是历史笔误
（与 E7/E8 同型：**单一真源 + 零破坏**优先于「字面正义」）。

**同批修复**：`0072` delta 曾给本条 Requirement 追加**第二段**正文（三条通道 SHALL 全部生效 / 取值 SHALL 三面同口径 /
SHALL NOT 经 `bool()` 静默强转），**归档合并时丢失**（现行 spec 只剩它带来的场景）。本 delta 将正文恢复为**两段**，
第二段**逐字**取自 `0072` delta 原文（不重写、不扩写）。

## MODIFIED Requirements

### Requirement: 功能开关（feature flag）
系统 SHALL 支持模块级 feature flag：关闭的模块不加载、不初始化，实现功能裁剪。feature flag SHALL ONLY 作用于**模块装配** —— 即组合根是否构造该模块的实例、是否注册其随装配产生的副作用（技能注册、状态文件读取）、是否接通其 CLI 与 Web UI 入口；SHALL NOT 改变模块**自身**的二级启用开关（如 `pet.enabled` 决定宠物模式是否启用，其缺省与语义不由 feature flag 改变）。**缺省口径**：白名单内的可选模块**未声明即视为开启**（缺省装配，保持既有行为）；只有显式 `false`（yaml `features.<模块>: false`、env `CORE_FEATURES_<模块>`、CLI `--feature <模块>=false`）SHALL 使该模块**完全不装配**。门控名单 SHALL 由组合根以**单一真源**维护（当前为 `pet` / `beast` / `evolution`）；名单外的模块名 SHALL NOT 触发任何装配裁剪，SHALL NOT 影响核心面。
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
