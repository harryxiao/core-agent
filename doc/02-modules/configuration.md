# 模块设计：配置管理（Configuration）

> 对应规格：`doc/openspec/specs/configuration/spec.md` ｜ 接口：`doc/03-interfaces/configuration-interface.md`
> 定位：**横切 ｜ 配置单一收口与 ConfigSpec 单一真源**，作为 llm-provider / ui / im / git / judgment 配置语义的上层挂载能力。

---

## 1. 模块定位

配置管理是横切能力，为全系统提供**统一的配置源、功能开关与密钥分级**：以 config.yaml 为单一收口，CLI 覆盖 + env 覆盖 + 默认值兜底；配置项以 ConfigSpec 为单一真源，避免各模块另起解析、出现第二真源。

各能力层（llm-provider / ui / im / git / judgment / pet）只负责声明自己的配置语义，具体的解析、校验、密钥解析与生效统一走本模块，保证配置行为一致。

---

## 2. 内部组成

```
Configuration（横切）
├── ConfigManager    配置管理器：load / validate_schema / resolve_secret / apply_change
├── AppConfig        有效配置聚合：llm / features / im / pet / extra
├── ConfigSpec       配置项单一真源：key / cli_flag / env_var / default / map_to / exposure
├── resolve()        优先级链解析：CLI flag > env > config.yaml > 默认值
└── 三面生成器       generate_cli_flags / generate_env_vars / generate_yaml_defaults
```

---

## 3. 关键设计

### 3.1 配置源与分层

- 以 config.yaml 为单一收口，env 环境变量与 CLI 启动参数覆盖 yaml 值，未配置项取默认值兜底。
- 优先级链固定为 **CLI flag > env > config.yaml > 默认值**，同项多处定义时高优先级覆盖低优先级，且不影响其他项。
- 每项配置通过 ConfigSpec 声明 `cli_flag` / `env_var` / `default` / `map_to`，CLI flag / env / yaml 三面由 ConfigSpec 生成，一一对应、无第二真源。

### 3.2 暴露面分级与 map_to 校验

- 配置项按暴露面分三级：`core`（默认暴露）/ `advanced`（高级）/ `hidden`（密钥等），生成 CLI 帮助与参数面时按分级暴露，`hidden` 项不出现于默认帮助。
- 启动时校验 ConfigSpec 的 `map_to`：目标不存在或冲突即阻断启动并报明确错误，杜绝映射错配。

### 3.3 必选 LLM 与功能裁剪

- LLM 配置（provider/model/endpoint/api_key）为**必选项**：缺失或 api_key 未解析时阻断启动，报明确错误指明缺失项。
- 模块级 feature flag（features 段，change `0067`）：**门控名单内**（`pet` / `beast` / `evolution`，
  名单为组合根单一真源 `core.runtime.GATABLE_MODULES`）的可选模块**缺省装配** —— 未声明即开，
  仅显式 `false`（yaml / env `CORE_FEATURES_*` / CLI `--feature`）才**完全不装配**：不构造实例、
  不产生装配期副作用（`beast` 不注册神通、`pet` 不读 `pets.json`）、CLI 入口拒绝。谓词
  `is_disabled`（缺省不关）与 `is_enabled`（缺省 false）极性相反、用途不同。
  feature flag 只管**装配**，不改模块自身二级开关（`pet.enabled`）。
- **第二条极性：缺省关名单**（change `0112`）：`core.runtime.OPT_IN_MODULES`（`evolution_executor`）
  内的能力**未声明即不装配**（fail-closed，仅显式 `true` 装配），由 `is_enabled` 消费 —— 自改代码的
  执行器必须先被显式打开才存在。两条名单都是组合根单一真源，配置层只消费注入的
  `KNOWN_FEATURE_MODULES`（二者之并，供未知开关名告警）。

- feature flag **取值三面同口径**（change `0072`，账本 E20②、E23）：原生布尔与 `true/false`、`yes/no`、
  `on/off`、`1/0`（大小写不敏感、忽略首尾空白）归一为布尔；其余取值（`maybe` / 空串 / 映射）**校验期
  拒绝并阻断启动**，不经 `bool()` 静默强转（`off` 之类假值写法不得被当作开启）。CLI 面
  `--feature <模块>[=<布尔>]` 经覆盖层 `features.<模块>` 参与优先级链（裸名视为开）。
- 未配置 judgment 段（或 provider 为空）时决策能力关闭，回退主 LLM 兜底。
- **LLM 调用超时 / 重试可配**（change `0232` / ADR-0221，账本 E168）：`llm.timeout`（缺省 `60.0` 秒，
  须 > 0 的数值）与 `llm.max_retries`（缺省 `3`，须 ≥0 的整数）经 ConfigSpec 单一真源声明（CLI / env / yaml
  三面齐备），校验期阻断非法值（不静默强转），组合根注入主 `StdlibLLMProvider`。**缺省 = 实现类缺省 ⇒
  未配置时行为零改变**（新增可调控点，非 kill-switch）；`embed_provider` / `JEVProvider` 不接同名键。

### 3.4 密钥分级与安全

- 敏感密钥（LLM api_key、IM secret、judgment.api_key）不落 yaml 明文，经 env/keychain 分级存储，yaml 中仅存 `${VAR}` 引用。
- schema 校验拒绝 yaml 明文密钥，提示改用 env/keychain 引用；日志与报错输出对密钥脱敏（掩码/占位符）。

### 3.5 校验、生效与回滚

- 配置做 schema 校验，**校验通过才生效**，否则拒绝并报错误。
- **loop 段四键校验**（change `0182`／ADR-0173）：`loop.max_rounds` 与 `loop.compact_steps` 须为
  **≥1 的整数**、`loop.output_reserve` 与 `loop.history_turns` 须为 **≥0 的整数**（`bool` 一律非法），
  非法即阻断启动；`loop.compact_steps` **不做**「≤ max_rounds」跨键校验 —— 阈值达上限是**合法退化配置**
  （语义仍是「至少压实一次」，只不再提前触发）。
- **长任务缺省放宽**（change `0260`／ADR-0250）：`loop.max_rounds` 缺省 `20`（`DefaultLoop`
  构造缺省同步，避免有/无配置源两条路径分叉）；`orchestration.subtask_timeout` 配置缺省 `600s`，
  显式 `0` 仍表示不设限；`TaskScheduler` 构造缺省保持 `0`（不注入即保持既有行为），生产值由组合根
  注入。
- **loop 段独立访问器**（change `0182`／ADR-0173、change `0183`／ADR-0174）：`compact_steps()` 与
  `output_reserve()` 各读一个既有/新增键，**不**并入 `loop_limits()` 二元组（其 arity 被多处解包断言
  钉死）；`output_reserve()` 与预算派生**同源**（预算 = 窗口 − 预留），组合根据此注入 planner 的
  请求侧输出上限 ⇒ 预留从**记账假设**变为**端点上界**（无新配置键、无规格变更）。
- **durability 保留策略两键**（change `0208`／ADR-0198）：`durability.retention.max_count` 须为
  **≥1 的整数**（`bool` / `0` / 负数一律非法）、`durability.retention.time_window_s` 须为 **≥0 的
  数值**（`bool` 非法）；**两键皆缺省合法**（= 不清理），非法即阻断启动。访问器 `retention_limits()
  -> tuple[int | None, float | None]` 返回**原始值对**（**不**返回能力层 `RetentionPolicy` ——
  `configuration` 是底座模块不得 import `durability`；`timedelta` 装配留组合根）。
- **已知模型窗口表**（change `0184`／ADR-0175）：`llm.context_window` 未配置（`0`）时，窗口来源由
  「恒回落常量 `65536`」改为**按 `llm.model` 从内置表推导** —— `model_windows.known_window(model)`
  做**子串匹配**（大小写不敏感）命中收录族返回其真实窗口，未命中返回 `0`（=「不知道」，调用方据此
  回落缺省）。**优先级：显式 `context_window > 0` > 表推导 > 内置缺省**（用户显式声明永远胜出）。
  表是**有序** `(子串, 窗口)` 元组（顺序即特异性，首个命中胜出）且**纯常量** —— 不引入任何配置键、
  无 CLI/env/yaml 面，故**不是**第二真源；它只**补充** `llm.context_window` 的推导来源。
  归一后统一 `window − output_reserve` ⇒ 减法只有一处；`_window_reserve_errors` 闸门只管**显式配置**
  的窗口（表推导路径不经该闸门 —— 见 ADR-0175 局限③）。
- **工具注入范围 `loop.tool_scope`**（change `0272`／ADR-0262）：取值仅 `all` / `auto`（缺省
  `auto`），**非法值校验期阻断启动**（`bool` / 非字符串 / 空串一律非法）；访问器 `tool_scope()`
  返回归一后取值（去首尾空白、小写，无配置源时返回 `auto`）。三面：`--loop.tool-scope` /
  `CORE_LOOP_TOOL_SCOPE` / yaml `loop.tool_scope`。语义见 `loop` 模块 §3.10 —— 配置值只决定
  **请求侧** schema 注入面，不改变工具注册、权限或执行面。`all` 为 kill-switch（逐字保持引入前
  行为）；`LLMPlanner` 构造缺省仍为 `all`（库级保守缺省，生产由组合根显式注入配置值）。
- **embedding 模型端点推导**（change `0271`／ADR-0261）：`llm.embedding_model` 未显式声明时，
  `LLMConfig.effective_embedding_model` 按 `embedding_models.default_embedding_model(endpoint)`
  从**有据可查的端点表**推导默认模型（`llm.embedding_auto` 缺省 `true`，非法值阻断启动）。
  显式值永远优先；推导**不回写字段**（热更新换端点自动跟随）；未知端点 / 开关关闭 ⇒ 空，
  与引入前逐字一致。表纯常量、无配置键，不是第二真源。
- 变更即生效；写入失败时回滚到变更前完整配置，不留半写状态，并记录告警。
- **写回是可逆效应（change `0130` / ADR-0123）**：变更作用于**内存 + yaml 文件**两处，`apply_change`
  与 `write_patch` 记在**同一 trace**（`"config"`）⇒ 按该 trace 回滚时磁盘态与内存态**一并回退**；
  `write_patch` 的 undo 恢复**写盘前的 yaml 原文**（不重 dump）。

---

## 4. 配置加载与生效闭环

```
config.yaml ──load(优先级链)──► AppConfig（有效配置聚合）
ConfigSpec ──三面生成──► CLI flag / env 变量 / yaml schema（一一对应）
AppConfig ──validate_schema──► 校验通过才生效；yaml 明文密钥被拒绝
配置变更 ──apply_change──► 写入失败回滚到变更前完整配置
配置变更 ──write_patch──► 落盘 + 记同 trace 可逆效应（undo 恢复 yaml 原文）
```

- 各能力层配置语义统一挂载到本模块，解析、校验、密钥解析、生效共用一条链路，不另起炉灶。
- feature flag 与 judgment 未配置回退保证「裁剪/兜底」都在配置层收敛，下游模块无感。

---

## 5. 错误处理

| 场景 | 行为 |
|---|---|
| 缺失或不完整 LLM 配置 | 阻断启动，报明确错误指明缺失的 LLM 配置项 |
| yaml 明文密钥 | schema 校验失败，提示改用 env/keychain 引用 |
| ConfigSpec 非法 map_to | 阻断启动，报明确错误（目标不存在或冲突） |
| 配置写入失败 | 回滚到变更前完整配置，不留半写状态，记录告警 |
| 未知配置段（顶层段名不在已知段内） | **仅告警**（WARN 不阻断，含段名 + 已知段清单）；该段保留在 `extra` 不丢弃（change `0064`，口径只到顶层段名） |
| `features` 段未知模块名 | **仅告警**（WARN 不阻断，含子键名 + 已知模块名清单）：`features` 子键是模块名、拼错会静默 no-op；**仅在注入已知模块名集合**时校验，作用域**仅此段**（change `0085`，账本 E20① / ADR-0080） |
| 日志/报错输出密钥 | 密钥值脱敏（掩码/占位符），不出现明文 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/configuration-interface.md`
- 规格：`doc/openspec/specs/configuration/spec.md`
- 上游挂载：`doc/02-modules/llm-provider.md`（LLM 配置语义）、`doc/02-modules/judgment.md`（judgment.* ConfigSpec）、`doc/02-modules/pet.md`（pet.* ConfigSpec）
- 消费：`doc/03-interfaces/cli-ops-interface.md`（ParamMapper 消费 ConfigSpec 单一真源）、
  `doc/02-modules/pet.md` / `doc/02-modules/beast-mode.md`（组合根按门控名单裁剪可选模块装配，change `0067`）
