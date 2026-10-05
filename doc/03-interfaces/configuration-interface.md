# 接口设计：配置管理（Configuration Interface）

> 横切 ｜ 对应规格 `configuration/spec.md` ｜ 挂载 llm-provider / ui / im / git

---

## 1. 实体模型

```python
@dataclass
class AppConfig:
    """配置聚合：单一收口解析后的有效配置。"""
    llm: LLMConfig                 # LLM 配置（必选）
    features: dict[str, bool]      # 模块级 feature flag
    im: IMConfig | None            # IM 接入配置（可选，None 表示未接入）
    pet: PetConfig | None          # 宠物模式配置（可选，None 表示未启用）
    extra: dict                    # 其他模块扩展配置

@dataclass
class LLMConfig:
    provider: str                  # 提供商
    model: str                     # 模型
    endpoint: str                  # 端点
    api_key_ref: str               # api_key 的 ${VAR} 引用（非明文）
    embedding_model: str = ""      # 记忆检索向量化模型（可选；空=不注入 embedder，回退词法）

@dataclass
class IMConfig:
    gateway: str                   # 网关类型
    corp_id: str                   # 账户/ID
    secret_ref: str                # secret 的 ${VAR} 引用（非明文）

@dataclass
class PetConfig:
    """宠物模式配置（pet.*，纳入 ConfigSpec 单一真源）。"""
    enabled: bool = False          # pet.enabled：总开关（--pet-enabled / CORE_PET_ENABLED）
    persons_dir: str = "persons"   # pet.persons_dir：多宠物 persona 目录（--pet-dir / CORE_PET_DIR）

@dataclass
class ValidationResult:
    ok: bool                       # 校验是否通过
    errors: list[str]              # 失败原因（缺失 LLM 配置、yaml 明文密钥等）—— 阻断生效
    warnings: list[str]            # 告警（未知配置段等）—— 仅提示，不阻断（change `0064`）

class ConfigExposure(str, Enum):
    CORE = "core"                  # 核心（默认暴露）
    ADVANCED = "advanced"          # 高级
    HIDDEN = "hidden"              # 隐藏（密钥等）

@dataclass(frozen=True)
class ConfigSpec:
    key: str                       # 配置键（点分路径，如 llm.provider）
    cli_flag: str                  # CLI flag（--llm.provider）
    env_var: str                   # env 变量（CORE_LLM_PROVIDER）
    default: Any = None            # 默认值
    map_to: str = ""               # 映射到 config.yaml 的点分路径
    exposure: ConfigExposure = ConfigExposure.CORE  # 暴露面分级
```

---

## 2. ConfigManager 接口

```python
class ConfigManager:
    def __init__(self, yaml_path=None, *, environ=None, keychain=None, effects=None,
                 cli=None, specs=None) -> None:
        """cli=CLI 覆盖层（最高优先级）；specs=ConfigSpec 清单（缺省用内置全量清单）。"""

    def load(self) -> AppConfig:
        """以 config.yaml 为单一收口加载：CLI 覆盖 env 覆盖 yaml 值，未定义项取默认值兜底。"""

    def validate_schema(self, config: AppConfig) -> ValidationResult:
        """schema 校验：密钥引用同口径（明文 / 空 / 不可解析）、LLM 必选项、权限模式枚举。"""

    def resolve_secret(self, ref: str) -> str:
        """从 env/keychain 解析敏感密钥引用（${VAR}），不落明文。"""

    def is_enabled(self, module: str) -> bool:
        """feature flag 查询：显式开启才为真（缺省 false；供缺省关的模块自查二级开关）。"""

    def is_disabled(self, module: str) -> bool:
        """装配裁剪判据（change 0067）：只有显式 `features.<模块>: false` 才为真（缺省不关）。"""

    def permission_mode(self) -> str:
        """权限模式查询（缺省 interactive；取值已在校验期限于四档），映射 config.permission.mode。"""

    def circuit_breaker(self) -> tuple[int, float]:
        """熔断阈值/冷却查询 → ``(failure_threshold, cooldown_s)``（缺省 ``(5, 30.0)``），映射 config.constraints.*。"""

    def config_value(self, key: str) -> Any:
        """装配前单键解析（change 0070）：CLI > env > config.yaml > 缺省；不校验、不缓存，缺文件按无 yaml 层。"""

    def apply_change(self, patch: dict) -> AppConfig:
        """变更即生效：写入失败回滚到变更前完整配置，不留半写状态。"""


def resolve(key, *, cli=None, env=None, yaml=None, specs=None) -> Any:
    """按优先级链 CLI flag > env > config.yaml > 默认值 解析配置项（ConfigSpec 单一真源）。"""

def validate_map_to(specs) -> list[str]:
    """校验 map_to 合法（非空点分路径、无重复），返回错误列表。"""

def generate_cli_flags(specs=None) -> list[str]: ...
def generate_env_vars(specs=None) -> list[str]: ...
def generate_yaml_defaults(specs=None) -> dict: ...
```

### 2.1 校验口径（change `0056`）

`validate_schema` 对**密钥引用**与**枚举型配置项**的判定一律在加载期完成（不通过即阻断启动）：

| 配置项 | 参与条件 | 判定 |
|---|---|---|
| `llm.api_key` | 总是 | 明文 → 拒；空 → 拒；不可解析 → 拒 |
| `im.secret` | 仅当 `im` 段存在 | 同上 |
| `judgment.api_key` | 仅当 `judgment.provider` 非空（能力启用） | 同上 |
| `permission.mode` | 总是（缺省 `interactive`） | 仅接受权限规格四档 `read-only` / `interactive` / `auto-approve` / `high-risk-block` |

口径来源：`doc/openspec/specs/configuration/spec.md`「密钥分级与安全」「配置校验与生效」；`permission.mode` 四档定义方为 `doc/openspec/specs/permission/spec.md`「权限模式」。
### 2.2 两个开关谓词（change `0067`，账本 E10）

`features` 段有三条输入通道（yaml `features:` / env `CORE_FEATURE_<模块>` / CLI `--feature <模块>[=<布尔>]`），
消费它的是**两个极性相反**的谓词：

| 谓词 | 真值条件 | 缺省 | 用途 |
|---|---|---|---|
| `is_enabled(module)` | `features.<模块>` 显式为**真** | `false` | 「显式开启查询」：供**缺省关**的模块自查二级开关（如 `pet.enabled`） |
| `is_disabled(module)` | `features.<模块>` 显式为**假** | `false`（即不关） | **装配裁剪**：门控名单内**缺省装配**的可选模块，由组合根消费 |

**装配裁剪契约**（规格「功能开关（feature flag）」）：门控名单 `core.runtime.GATABLE_MODULES`
（当前 `pet` / `beast` / `evolution`）是**组合根单一真源** —— 配置层不认识模块名。名单内模块
**缺省装配**（未声明即开，兼容既有行为），仅显式 `false` 才完全不装配；名单外的名字不触发任何裁剪。
关闭的含义是**彻底**的：不构造实例、不产生装配期副作用（`beast` 连 20 神通都不注册、`pet` 不读
`pets.json`）、`loop` 冷路径一并置 `None`、CLI 入口拒绝（stderr 说明 + 退出码 0）。
feature flag 只管**装配**，不改模块自身的二级启用开关（`features.pet` 缺省开 ≠ `pet.enabled` 开）。

**三面取值同口径 + CLI 面接线**（change `0072`，账本 E20②、E23）：三条通道**全部生效**，取值收敛在
**单一归一/校验点** `_normalize_features()` —— 接受原生布尔与 `true/false`、`yes/no`、`on/off`、`1/0`
（大小写不敏感、忽略首尾空白），其余取值（`maybe` / 空串 / 映射）**校验期拒绝并阻断启动**（错误信息含
键名与合法取值），**SHALL NOT** 经 `bool()` **静默强转**（`bool("off")` 为真，会把「显式关闭」当作开启）。
归一发生在**构建配置前**（`features` 是结构化段，化为布尔后原文不可追溯 —— 与 `load()` 顶部 `map_to`
校验同属「构建前阻断」通道），故运行时变更（`config set features.<模块>=...`）走同一函数、同一口径。
CLI 面 `--feature <模块>[=<布尔>]` 由 `entry._cli_overrides` 收进覆盖层 `features.<模块>`（模块名是
**开放集合**、归组合根，故不入 `ConfigSpec`），与其他两面共用同一优先级链与同一套取值校验；裸名视为开；
语法非法（`=false` / `pet=`）在**解析点**即拒（`非法 --feature 取值`）。

> ⚠️ **env 前缀差异（账本 E24，待裁决）**：实现读 `CORE_FEATURES_<模块>`（**复数**，与段名 `features`
> 一致），而规格、本文件上文与 `02-modules/configuration.md` 字面写 `CORE_FEATURE_<模块>`（单数），
> `doc/00-product/user-guide.md` 亦写复数。改名属**对外可观测**的破坏性变更，本次不动，单独立项裁决。

### 2.3 未知配置段：仅告警（change `0064`，账本 E18）

**不再静默**：顶层段名不在**已知段**之内时，`validate_schema` 返回**告警**（含段名、已知段清单与「已收纳进 `extra` 且未做校验」提示），`load()` 经 `warnings.warn` 发出，**不阻断启动**、**不丢弃**该段（仍留在 `extra`）。

- **已知段** = 五个结构化段（`llm` / `features` / `im` / `pet` / `judgment`）
  + `ConfigSpec` 声明段（由 `map_to` 前缀导出）+ 有运行时语义的 `extra` 已知段（`permission`）。
  新增 ConfigSpec 自动进白名单（单一真源，不另维护清单）。
- **作用域**：只判**顶层段名**，不递归校验已知段内部的未知子键。
- **为何不硬拒**：`extra` 是承诺给扩展的宽松兜底，收紧为白名单会**拒绝既有自定义段**
  （改变既有接受行为）；而完全静默会让拼错的段名（`llmm:`）无处暴露（用户只看到「LLM 配置缺失」）。

### 2.4 熔断阈值/冷却可配（change `0068`，账本 E15）

`constraints` 段承载熔断参数，**不新增结构化段**、镜像 `permission.mode` 的 `extra` 驻留先例
（避免改配置规格里「五个结构化段」的字面枚举；`map_to` 前缀已自动进 §2.3 白名单）：

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `constraints.failure_threshold` | `5` | **≥1 的整数** | 连续执行失败达此值 → 该工具熔断（`OPEN`） |
| `constraints.cooldown_s` | `30.0` | **≥0 的数值** | 冷却期（秒），过后半开试探 |

- **单一真源**：两键由 `ConfigSpec` 声明（`ConfigSpec(..., map_to="constraints.<键>")`），
  自动获得 CLI flag（`--constraints.failure-threshold` / `--constraints.cooldown-s`）、env
  （`CORE_CONSTRAINTS_FAILURE_THRESHOLD` / `CORE_CONSTRAINTS_COOLDOWN_S`）与优先级链，无需另维护。
- **校验期拒绝**：非法取值（阈值非 ≥1 整数如 `0`/`-1`/`2.5`/`abc`；冷却非 ≥0 数值）
  在 `validate_schema` 判为错误、**阻断启动**，**不**静默兜底为缺省值。
- **消费方**：组合根 `build_runtime` 经 `config.circuit_breaker()` 读出后注入 `build_constraints_chain`，
  主 loop 与子 agent loop **共享同一链实例**（熔断态 per-runtime）。
- 口径来源：`doc/openspec/specs/constraints/spec.md`「容错中间件」（**MODIFIED**）。

### 2.6 出站白名单可配（change `0071`，账本 B5）

`permission.sandbox` 段承载沙箱出站主机白名单，与 §2.4 同路：**不新增结构化段**，
镜像 `permission.mode` 的 `extra` 驻留先例（`map_to` 前缀已自动进 §2.3 白名单）。

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `permission.sandbox.host_allowlist` | `""`（空 = 全拒） | 逗号分隔的**裸主机名** | 出站网络白名单（`SandboxPolicy.check_outbound`） |

- **单一真源**：由 `ConfigSpec` 声明（`map_to="permission.sandbox.host_allowlist"`，
  `exposure=ADVANCED`），自动获得 CLI flag `--permission.sandbox.host-allowlist`、env
  `CORE_SANDBOX_HOST_ALLOWLIST` 与优先级链（CLI > env > config.yaml > 缺省）。
- **取值形态为标量**：本仓 yaml 子集解析器**不含列表**（§2.3 同款约束），故三面统一为逗号分隔
  字符串，归一到裸主机名列表（去空白 / 去空项 / 保序去重，兼容全角逗号）。
- **校验期拒绝**：条目带 scheme（`https://a.example.com`）、端口（`a.example.com:443`）、
  路径（`a.example.com/v1`）或内部空白 —— 因 `check_outbound` 的实参是 `urlparse().hostname`，
  这类条目**永不匹配**，故在 `validate_schema` 判为错误、**阻断启动**，**不**静默忽略；
  非字符串取值（如 yaml 里写 `123` 被解析成整数）同样阻断。
- **缺省空白名单 = fail-closed 全拒**，安全默认不因新增配置项而松动。
- **消费方**：组合根 `build_runtime` 经 `config.sandbox_host_allowlist()` 读出后注入
  `SandboxPolicy(host_allowlist=...)`，`MCPClient` 与 `SandboxManager` **共用同一策略实例**。
- 口径来源：`doc/openspec/specs/permission/spec.md`「沙箱执行颗粒度」（**MODIFIED**）。

### 2.5 装配前单键解析（change `0070`，账本 E21）

`config_value(key)` 是 `load()` 之外的第二条**只读单键**通路，专供 CLI 层在装配前做前置判定
（当前消费方：`entry._pet` 的 `pet.enabled` 门控与 `pet.persons_dir` 取值；`entry._config` 的 `config get` 单键读取 —— change `0078`／ADR-0075，账本 E22）。

- **同源**：内部即 `resolve(key, cli=self._cli, env=self._environ, yaml=<yaml 层>, specs=self._specs)` ——
  与 `load()` 共用 ConfigSpec 单一真源，**禁止**另起一套解析（规格「宠物模式配置」明文要求）。
- **yaml 层**：按 `ConfigSpec.map_to` 从嵌套 yaml 逐键取出、以 `ConfigSpec.key` 为键回填
  （两者对 `im.corp-id` 等键不同名，故不能简单按点分拼键）。
- **不校验/不阻断/不缓存**：`config.yaml` 缺失按「无 yaml 层」处理（不抛 `ConfigurationError`），
  供「配置文件可能不存在」的前置判定使用；整份配置的校验仍归 `load()`。
- **返回原文**：env/CLI 层为字符串，归一化（如 `entry._as_bool`）由调用方负责，与 `resolve` 口径一致。
- 性能无关紧要：前置判定只读单键，不解析整份配置为 `AppConfig`。
