# configuration — 后台派生调用与压实上限配置（change 0296）

## ADDED Requirements

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
