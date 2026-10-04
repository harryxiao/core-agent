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
- 模块级 feature flag（features 段）：关闭的模块不加载、不初始化，实现功能裁剪，其依赖资源不占用。
- 未配置 judgment 段（或 provider 为空）时决策能力关闭，回退主 LLM 兜底。

### 3.4 密钥分级与安全

- 敏感密钥（LLM api_key、IM secret、judgment.api_key）不落 yaml 明文，经 env/keychain 分级存储，yaml 中仅存 `${VAR}` 引用。
- schema 校验拒绝 yaml 明文密钥，提示改用 env/keychain 引用；日志与报错输出对密钥脱敏（掩码/占位符）。

### 3.5 校验、生效与回滚

- 配置做 schema 校验，**校验通过才生效**，否则拒绝并报错误。
- 变更即生效；写入失败时回滚到变更前完整配置，不留半写状态，并记录告警。

---

## 4. 配置加载与生效闭环

```
config.yaml ──load(优先级链)──► AppConfig（有效配置聚合）
ConfigSpec ──三面生成──► CLI flag / env 变量 / yaml schema（一一对应）
AppConfig ──validate_schema──► 校验通过才生效；yaml 明文密钥被拒绝
配置变更 ──apply_change──► 写入失败回滚到变更前完整配置
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
| 日志/报错输出密钥 | 密钥值脱敏（掩码/占位符），不出现明文 |

---

## 6. 关联

- 接口契约：`doc/03-interfaces/configuration-interface.md`
- 规格：`doc/openspec/specs/configuration/spec.md`
- 上游挂载：`doc/02-modules/llm-provider.md`（LLM 配置语义）、`doc/02-modules/judgment.md`（judgment.* ConfigSpec）、`doc/02-modules/pet.md`（pet.* ConfigSpec）
- 消费：`doc/03-interfaces/cli-ops-interface.md`（ParamMapper 消费 ConfigSpec 单一真源）
