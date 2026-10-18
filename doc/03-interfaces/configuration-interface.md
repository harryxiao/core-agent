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
    embedding_model: str = ""      # 用户显式向量化模型（空=未声明，见 effective_embedding_model）
    embedding_auto: bool = True    # 未显式声明时按端点推导默认模型（change 0271；false=关闭）
    embedding_required: bool = False  # 有效模型为空时阻断启动（change 0289）
    context_window: int = 0        # 模型上下文窗口（可选；0=未配置，不派生预算 —— change 0098）

    @property
    def effective_embedding_model(self) -> str:
        """生效值：显式值优先，否则按端点表推导（未命中/开关关闭 ⇒ 空）。不回写字段。"""

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
                 cli=None, specs=None, known_modules=None) -> None:
        """cli=CLI 覆盖层（最高优先级）；specs=ConfigSpec 清单（缺省用内置全量清单）；
        known_modules=已知模块名集合（`features` 段子键校验用，组合根注入；缺省 None=不校验）。"""

    def load(self) -> AppConfig:
        """以 config.yaml 为单一收口加载：CLI 覆盖 env 覆盖 yaml 值，未定义项取默认值兜底。"""

    def validate_schema(self, config: AppConfig) -> ValidationResult:
        """schema 校验：密钥引用同口径（明文 / 空 / 不可解析）、LLM 必选项、权限模式枚举。"""

    def resolve_secret(self, ref: str) -> str:
        """从 env/keychain 解析敏感密钥引用（${VAR}），不落明文。"""

    def is_resolvable(self, ref: str) -> bool:
        """密钥引用**能否**经 env/keychain 解析（change 0162）：**只回布尔**，不返回、不打印明文
        （供只读诊断面 `core.diagnostics` 判「已设置 / 未设置」，见 `cli-ops-interface.md` §5）。"""

    def is_enabled(self, module: str) -> bool:
        """feature flag 查询：显式开启才为真（缺省 false；供缺省关的模块自查二级开关）。"""

    def is_disabled(self, module: str) -> bool:
        """装配裁剪判据（change 0067）：只有显式 `features.<模块>: false` 才为真（缺省不关）。"""

    def permission_mode(self) -> str:
        """权限模式查询（缺省 interactive；取值已在校验期限于四档），映射 config.permission.mode。"""

    def circuit_breaker(self) -> tuple[int, float]:
        """熔断阈值/冷却查询 → ``(failure_threshold, cooldown_s)``（缺省 ``(5, 30.0)``），映射 config.constraints.*。"""

    def loop_limits(self) -> tuple[int, int]:
        """循环预算查询 → ``(max_rounds, token_budget)``（change 0098）：轮数取 ``loop.max_rounds``
        （缺省 ``10``）；token 预算由 ``llm.context_window`` **派生**（窗口 - ``loop.output_reserve``，
        缺省预留 ``8192``），未配窗口时回落内置缺省 ``65536``。"""

    def config_value(self, key: str) -> Any:
        """装配前单键解析（change 0070）：CLI > env > config.yaml > 缺省；不校验、不缓存，缺文件按无 yaml 层。"""

    def apply_change(self, patch: dict) -> AppConfig:
        """变更即生效：写入失败回滚到变更前完整配置，不留半写状态。"""

    def write_patch(self, patch: dict) -> None:
        """把 patch 写回 config.yaml（只合并用户 patch，不落 env/cli 覆盖与明文密钥）；原子提交
        （tmp + ``os.replace``），并记一条**可逆效应**（见 §2.9）。"""


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

`features` 段有三条输入通道（yaml `features:` / env `CORE_FEATURES_<模块>` / CLI `--feature <模块>[=<布尔>]`），
消费它的是**两个极性相反**的谓词：

| 谓词 | 真值条件 | 缺省 | 用途 |
|---|---|---|---|
| `is_enabled(module)` | `features.<模块>` 显式为**真** | `false` | **缺省关装配**（change `0112`）：名单 `OPT_IN_MODULES`（当前 `evolution_executor`）由组合根消费；二级开关自查（如 `pet.enabled`）同用 |
| `is_disabled(module)` | `features.<模块>` 显式为**假** | `false`（即不关） | **装配裁剪**：门控名单内**缺省装配**的可选模块，由组合根消费 |

**装配裁剪契约**（规格「功能开关（feature flag）」）：组合根以**两条极性相反的名单**消费上述谓词
（同一名字**不能**承载两种缺省语义）：

| 名单（`core.runtime`，单一真源） | 消费谓词 | 缺省 | 成员 |
|---|---|---|---|
| `GATABLE_MODULES` | `is_disabled` | **装配**（未声明即开） | `pet` / `beast` / `evolution` |
| `OPT_IN_MODULES` | `is_enabled` | **不装配**（未声明即关，fail-closed） | `evolution_executor` |

派生 `KNOWN_FEATURE_MODULES = GATABLE_MODULES + OPT_IN_MODULES` 供「未知功能开关」告警（见 §2.3）。
配置层不认识模块名：`GATABLE_MODULES` 内模块**缺省装配**（未声明即开，兼容既有行为），仅显式 `false`
才完全不装配；`OPT_IN_MODULES` 内模块**必须显式 `true`** 才装配（缺省关，fail-closed）；两侧名单外的
名字不触发任何裁剪。
关闭的含义是**彻底**的：不构造实例、不产生装配期副作用（`beast` 连 20 神通都不注册、`pet` 不读
`pets.json`）、`loop` 冷路径一并置 `None`、CLI 入口给出说明（**rc 0** —— 能力被关闭不是错误）。
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

> **env 前缀为复数（账本 E24，change `0080`）**：`CORE_FEATURES_<模块>` —— 与 yaml 段名 `features` 同源
> （`manager.py` 的 `_FEATURE_ENV_PREFIX`）。本文件与规格、`02-modules/configuration.md` 曾字面写**单数**
> `CORE_FEATURE_<模块>`（历史笔误），已由 change `0080` 向实现订正；单数前缀**不生效**，且**不做**兼容别名
> （静默接受两个前缀 = 同一开关两个真源）。

### 2.3 未知配置段：仅告警（change `0064`，账本 E18）

**不再静默**：顶层段名不在**已知段**之内时，`validate_schema` 返回**告警**（含段名、已知段清单与「已收纳进 `extra` 且未做校验」提示），`load()` 经 `warnings.warn` 发出，**不阻断启动**、**不丢弃**该段（仍留在 `extra`）。

- **已知段** = 五个结构化段（`llm` / `features` / `im` / `pet` / `judgment`）
  + `ConfigSpec` 声明段（由 `map_to` 前缀导出）+ 有运行时语义的 `extra` 已知段（`permission` / `loop`）。
  新增 ConfigSpec 自动进白名单（单一真源，不另维护清单）。
- **作用域**：只判**顶层段名**，不递归校验已知段内部的未知子键。
- **例外：`features` 段子键（change `0085`，账本 E20①）** —— `features` 段子键是**模块名**，
  拼错会**静默 no-op**（`features.peet: false` 关不掉 `pet`：`is_disabled("pet")` 查不到 `"pet"`）。
  故当 `ConfigManager` **注入了已知模块名集合**（`known_modules`，组合根传
  `runtime.KNOWN_FEATURE_MODULES`（两条名单之并，change `0112`））时，
  `features` 段的未知子键**仅告警**（含子键名 + 已知清单 + 「拼错将静默不生效」提示）、**不阻断**；
  未注入（缺省 `None`）时**不校验**子键。作用域**仅** `features` —— 其它已知段的未知子键（如 `llm.typo_key`）
  仍不告警（各能力 schema 义务，非本项）。模块名集合仍归组合根单一真源，配置层只**消费注入**（不 import runtime）。
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

### 2.7 上下文窗口与循环预算可配（change `0098`）

`TOKEN_BUDGET_EXCEEDED` 与「单任务最大循环次数」此前是 `DefaultLoop` 的**写死 ctor 缺省**
（`65536` / `10`），组合根四处 `DefaultLoop(...)` **都不传参** ⇒ 用户无法调。本项把它们接入配置链，
并新增**模型上下文窗口**作为预算的派生源（`llm` 是结构化段；`loop` 照 §2.4/§2.6 先例驻留 `extra`）：

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `llm.context_window` | `0`（= 未配置） | `0` 或 **≥1 的整数** | 模型上下文窗口；`> 0` 时参与派生 token 预算 |
| `loop.output_reserve` | `8192` | **≥0 的整数** | 固定保留的输出头寸（推理/回答用），从窗口中扣除 |
| `loop.max_rounds` | `20` | **≥1 的整数** | 单任务最大循环次数上限（change `0260`：10 → 20） |
| `loop.history_turns` | `20` | **≥0 的整数**（`0` = 关闭回灌） | 会话历史回灌轮数（change `0115`）：注入转录存储时 `perceive` 载入本会话最近 N 轮进 `LoopContext.history`；与 token 切片 `token_budget // 2` 取**双重上界**（ADR-0108） |

- **单一真源**：四键由 `ConfigSpec` 声明（`map_to="llm.context_window"` / `"loop.output_reserve"` /
  `"loop.max_rounds"` / `"loop.history_turns"`，`exposure=ADVANCED`），自动获得 CLI flag（`--llm.context-window` /
  `--loop.output-reserve` / `--loop.max-rounds` / `--loop.history-turns`）、env（`CORE_LLM_CONTEXT_WINDOW` /
  `CORE_LOOP_OUTPUT_RESERVE` / `CORE_LOOP_MAX_ROUNDS` / `CORE_LOOP_HISTORY_TURNS`）与优先级链
  （CLI > env > config.yaml > 缺省）。
- **`loop.history_turns` 走独立访问器** `ConfigManager.history_turns()`，**不**并入 `loop_limits()` 元组
  （后者被 20+ 处 `limits[0]`/`limits[1]` 解包断言钉死，且回灌轮数与预算派生无语义关系）——
  同 `permission_mode()` 先例；经 `LimitsConfigurable.set_limits(history_turns=...)` **热推**
  （本仓把「报成功却不生效」列为缺陷类，保存配置须落盘与生效同步）。取舍详见 ADR-0108。
- **派生口径（固定保留头寸）**：`loop_limits()` 返回
  `token_budget = context_window - output_reserve`（当 `context_window > 0`），否则回落内置缺省 `65536`
  （**与变更前逐位一致**）；`max_rounds` 独立取 `loop.max_rounds`。**不**新开显式 `loop.token_budget` 键 ——
  用户选的是「由窗口派生」，派生式即机制（少一层会与窗口矛盾的开关）。取舍详见 ADR-0091。
  窗口来源的完整三态（显式 > 内置模型窗口表 > 缺省）见 §2.10（change `0184`／ADR-0175）。
- **校验期拒绝（不静默兜底）**：`llm.context_window` 非 `0`/≥1 整数（含 `bool`）、`loop.output_reserve`
  非 ≥0 整数、`loop.max_rounds` 非 ≥1 整数、`loop.history_turns` 非 ≥0 整数（含 `bool`），
  均在 `validate_schema` 判为错误、**阻断启动**；**交叉校验** `context_window > output_reserve`，
  否则报「窗口不敷输出预留」。
  为何**必须**阻断而非兜底：`token_budget <= 0` 在 loop 里的语义是「**关闭** token 维度」，
  静默兜底会把一个配置错误伪造成「预算维度失效」（更危险），详见 ADR-0091。
- **构建前阻断**：`llm.context_window` 在 `_build_config` 即化为整数（结构化段原文不可追溯），
  与 `_normalize_features` 同属「构建前阻断」通道；`loop.*` 取值原文在 `extra`，校验与消费同读原文。
- **CLI 入口**：`entry._key_to_patch` 现接受 `llm.` / `features.` / `im.` / **`loop.`** 前缀
  ⇒ `config set loop.max_rounds 3` 三面齐备；`write_patch` 对寄居 `extra` 的 `loop` 段**浅合并**
  （整份拷贝会把 patch 静默丢弃 ⇒ 报成功却不生效）。
- **消费方**：组合根 `build_runtime` 经 `config.loop_limits()` 读出后，**四处** `DefaultLoop(...)`
  （主 / 子 agent / 神兽 / 宠物 loop）注入同一对参数。
- 口径来源：`doc/openspec/specs/loop/spec.md`「错误与预算控制」（**MODIFIED**）、
  `doc/openspec/specs/configuration/spec.md`「LLM 提供商配置（必选）」（**MODIFIED**）与
  「循环预算配置」（**ADDED**）。

### 2.8 编排调度配置（change `0123` / ADR-0116；`0247` / ADR-0235；`0278` / ADR-0268）

同波次调度策略、并发上限与子任务交接超时接入配置链（`orchestration` 照 §2.4/§2.6/§2.7 先例驻留 `extra`）：

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `orchestration.difficulty_policy` | `off` | `off` / `difficulty` | 同波次调度策略：`off` 沿用依赖拓扑并发（**逐字一致**）；`difficulty` 时含 `hard` 的波次串行 |
| `orchestration.max_concurrency` | `4` | **≥1 的整数** | 同波次并发上限（`_fan_out` 的 `Semaphore` 上限） |
| `orchestration.subtask_timeout` | `600` | **≥0 的整数**（秒） | 子任务交接（`TaskHandoff.deadline`）超时；`0` = 显式不设限（change `0260`：0 → 600） |
| `orchestration.auto_resume` | `false` | 布尔 / `true`·`false` 字符串 | `task` 入口启动时自动续跑未完成编排任务（有界退避；change `0278`） |

- **单一真源**：四键由 `ConfigSpec` 声明（`map_to="orchestration.*"`，`exposure=ADVANCED`），
  自动获得 CLI flag（`--orchestration.difficulty-policy` / `--orchestration.max-concurrency` /
  `--orchestration.subtask-timeout` / `--orchestration.auto-resume`）、env
  （`CORE_ORCHESTRATION_DIFFICULTY_POLICY` / `CORE_ORCHESTRATION_MAX_CONCURRENCY` /
  `CORE_ORCHESTRATION_SUBTASK_TIMEOUT` / `CORE_ORCHESTRATION_AUTO_RESUME`）与优先级链
  （CLI > env > config.yaml > 缺省）；声明段自动进「已声明段」白名单 ⇒ 不触发「未知配置段」告警。
- **访问器**：`ConfigManager.orchestration_difficulty_policy()` /
  `orchestration_max_concurrency()` / `orchestration_subtask_timeout()` /
  `orchestration_auto_resume()` 四个独立标量访问器
  （**不**并入 `loop_limits()`，同 §2.7 口径）。
- **校验期拒绝（不静默兜底）**：`max_concurrency` 非 ≥1 整数（`0` / 负数 / 小数 / 非数值 / `bool`）⇒
  「非法波次并发上限」；`difficulty_policy` 不在词表（含拼写错误、`OFF` 等大小写变体）⇒
  「非法编排调度策略」；`subtask_timeout` 非 ≥0 整数（负数 / 小数 / 非数值 / `bool`）⇒
  「非法子任务超时」；`auto_resume` 非布尔/非 `true`·`false` 字符串 ⇒「非法自动续跑开关」；
  四者均在 `validate()` 判为错误、**阻断启动**。
  **与 `Subtask.difficulty` 的口径不同**（后者是模型自报弱信号 ⇒ **归一**为 `medium`）：配置是人写的，
  写错必须暴露（ADR-0116 决策④）。
- **组合根注入（不得依赖构造缺省）**：`build_runtime` 装配 `TaskScheduler` 时**显式**传三值 ——
  `TaskScheduler` 的构造缺省 `max_concurrency=4` 与既有行为**同值**，不接线**不会暴露**
  （上限判据空转，与账本 E15 同型）；`subtask_timeout` 配置缺省 `600` 同样由组合根显式注入。
  **两处缺省口径不同**（change `0260`）：`TaskScheduler` 构造缺省仍为 `0`（不设限；不注入即保持既有
  行为），配置面缺省为 `600`；生产路径必须经组合根注入，直连构造不获得 600s 保护。显式配置 `0`
  原样注入为「不设限」，不被缺省值覆盖。
  已有用例断言接入的是**配置值**而非构造缺省。
- **`config set` 可达**：`_key_to_patch` 白名单含 `orchestration`；`_merge_patch` 对 `extra` 寄居段
  （`loop` / `orchestration`）**浅合并** ⇒ patch 不会「报成功却不生效」。

### 2.9 写回的可逆效应（change `0130` / ADR-0123，账本 E68）

`write_patch` 落盘**是**可逆效应：配置变更作用于**两处状态**（内存 `AppConfig` + `config.yaml` 文件），
`apply_change` 原先只记了内存那一处 ⇒ 按 trace 回滚会留下「内存已退、磁盘未退」的不一致，下次 `load()`
把已回滚的变更**复活**。

- **记账点**：`os.replace` **之前**记 `Effect(op="config_write_patch", target=<yaml 路径>, trace_id="config")`，
  与 `apply_change` 的 `config_apply` **同 trace** ⇒ **一次** `rollback("config")` 同时回退内存与磁盘。
- **undo 恢复写盘前的**原文字节****（不重新 `_dump_yaml`）：重 dump 会改写文件格式，并可能把 env/cli
  覆盖层写进 yaml（`write_patch` 只合并用户 patch）。
- **幂等**：`os.replace` 原子 —— 若它抛出则 yaml 仍是旧值，undo 写回旧值即 no-op。
- **本 change 不新增配置回滚的生产入口**（`rollback("config")` 今日无调用方；`entry._config_set` 与
  `ui/api.py` 的「回滚」都是**重读 yaml**）⇒ 行为零变化，账目**先于消费者**就位。
- **CLI 入口**：两键经 ConfigSpec **自动**获得主命令 flag（`--orchestration.difficulty-policy` /
  `--orchestration.max-concurrency`，`_add_config_flag` 单一真源派生）。`config set` 的键前缀白名单
  （`entry._key_to_patch`：`llm.` / `features.` / `im.` / `loop.`）**不含** `orchestration.` ⇒
  该命令会**明确报「暂不支持键」**（不静默成功、不假装生效；如需三面齐备可后续按 §2.7 先例补白名单）。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「编排调度配置」（**ADDED**）与
  `doc/openspec/specs/orchestration/spec.md`「难易度感知的调度策略」（**ADDED**）。

### 2.10 已知模型窗口表（change `0184` / ADR-0175，账本 E121）

`llm.context_window` 缺省 `0` 时窗口**恒**回落常量 `65536` ⇒ 模型换了窗口却不随动（§2.7 派生口径的
上游来源只有一个）。本项新增**内置已知模型窗口表**作为中间来源：

```
llm.context_window > 0  ──►  显式值（优先，逐字兼容）
        │ 否
        ▼
known_window(llm.model)  ──►  表命中 ⇒ 该族真实窗口（本 change 唯一的有意行为变更）
        │ 未命中（返回 0 = 不知道）
        ▼
内置缺省 65536（不做窗口派生，回落常量预算 —— 逐字兼容）
```

- **模块**：`src/core/configuration/model_windows.py` —— `_KNOWN_CONTEXT_WINDOWS: tuple[tuple[str, int], ...]`
  + `known_window(model: str) -> int`。**有序**表（**顺序即特异性**：更具体的前缀须排在更笼统的前缀之前，
  首个命中胜出）+ **子串匹配**（大小写不敏感、忽略首尾空白）⇒ 命名空间/版本后缀（`openai/gpt-4.1-mini`、
  `gpt-4o-2024-08-06`）都能命中。未命中返回 `0`（「不知道」的诚实表达），由 `loop_limits()` 统一回落。
- **无新配置面**：表是**纯常量 + 纯函数**，**不**引入 ConfigSpec / CLI flag / env / yaml 键 ⇒
  **不是**第二真源，只是 `llm.context_window` 的**推导来源**。
- **消费方**：`ConfigManager.loop_limits()`（`window <= 0` 时调 `known_window`），其余口径（`max_rounds`、
  减法位置、arity）**逐字不变** ⇒ 既有 `(max_rounds, token_budget)` 解包断言不受影响。
- **不变量**：① 显式窗口 ⇒ 预算与变更前**逐字相同**；② 表未命中 ⇒ 回落 `65536`，与变更前**逐字相同**；
  ③ 减法只有一处（归一窗口后统一 `window − output_reserve`）。
- 已知局限（不过 `_window_reserve_errors` 闸门 / 子串无边界语义 / 静态表不自更新）见 ADR-0175。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「LLM 提供商配置（必选）」（**MODIFIED**）。

### 2.11 LLM 调用超时与重试可配（change `0232` / ADR-0221，账本 E168）

`StdlibLLMProvider` 的 `timeout` / `max_retries` 构造参**早已存在**，但 `_CONFIG_SPECS` 无键、
组合根 `build_runtime` 构造主 provider 时未传 ⇒ 恒取实现类缺省，操作者无法收窄「单次调用等待上限」
（2026-10-12 实跑：轮末 maintenance 调用超时 ⇒ 4×60s ≈ 232s）。本项把两者接入配置链：

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `llm.timeout` | `60.0` | **> 0 的数值**（单位秒） | 单次模型调用超时上限 |
| `llm.max_retries` | `3` | **≥0 的整数** | 调用失败最大重试次数 |

- **单一真源**：两键由 `ConfigSpec` 声明（`map_to="llm.timeout"` / `"llm.max_retries"`，
  `exposure=ADVANCED`），自动获得 CLI flag（`--llm.timeout` / `--llm.max-retries`）、
  env（`CORE_LLM_TIMEOUT` / `CORE_LLM_MAX_RETRIES`）与优先级链（CLI > env > config.yaml > 缺省）。
- **缺省 = 实现类缺省 ⇒ 行为零改变**：三处（dataclass / ConfigSpec / 解析器回落）同为 `60.0` / `3`，
  与 `StdlibLLMProvider.__init__` 类缺省**逐字一致**。这是**新增可调控点**（非 kill-switch）。
- **构建前阻断（不静默强转）**：`_llm_timeout` / `_llm_max_retries` 镜像 `_llm_context_window` 口径，
  在 `_build_config` 当场 `raise ConfigurationError`：`timeout` 须 `> 0` 的数值、`max_retries` 须
  `≥ 0` 的整数（`bool` / 小数 / 负数 / 非数值一律拒）。`timeout <= 0` 在 provider 侧语义是
  「立即失败」⇒ 放行等于把配置笔误静默变成「所有调用必失败」。
- **两处构造点同步**：`_build_config`（冷启动）与 `apply_change`（热更新补丁）**都**接线 ——
  只改一处会让 `config set llm.timeout` 看似生效、实际被静默丢弃。
- **消费方**：组合根 `build_runtime` 把两值注入主 `StdlibLLMProvider`
  （`timeout=app.llm.timeout, max_retries=app.llm.max_retries`）；`embed_provider` 与 `JEVProvider`
  **不**接同名键（各自独立语义，留默认）。
- 已知局限（dataclass 缺省在配置路径不可观测 / 不改 provider 重试语义 / 不做「重试进度可见」）见 ADR-0221。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「LLM 提供商配置（必选）」、
  `doc/openspec/specs/llm-provider/spec.md`「模型调用可靠性」（均 **MODIFIED**）。

### 2.12 记忆容量配置（change `0251` / ADR-0241，账本 E187）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `memory.l2_soft_max_entries` | **未设置**（`None`） | **≥1 的整数** | L2 活跃层软上限条目数；未设置 = 不设上限 |

- **单一真源**：`ConfigSpec` 声明（`map_to="memory.l2_soft_max_entries"`，`exposure=ADVANCED`）
  ⇒ CLI flag `--memory-l2-soft-max-entries`、env `CORE_MEMORY_L2_SOFT_MAX_ENTRIES`、
  yaml `memory:` 段三面一一对应；优先级链 CLI > env > config.yaml > 缺省。
- **访问器** `ConfigManager.l2_soft_max_entries() -> int | None`：`memory` 为非结构化段 ⇒
  `bool` / 小数 / 非数值 / `0` / 负数一律归一为 `None`（不阻断启动）。`0` 特意不收：
  直通会清空 L2，属危险笔误方向。
- **消费方**：组合根 `build_runtime` 以 `l2_soft_max_entries=` 注入 `MemoryStore`
  （此前形参存在但无生产调用方 ⇒ 能力不可达）。未配置 ⇒ 写入路径逐字不变。
- **只在写入后收口**：存量超限库下一次写入才收敛（不在启动时迁移）。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「记忆容量配置」（ADDED）、
  `doc/openspec/specs/memory/spec.md`「L2 活跃层软上限」（MODIFIED）。

### 2.13 钩子配置（change `0269` / ADR-0259，台账 E205）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `hooks.enabled` | **`false`** | 布尔 | 未显式开启 ⇒ 不加载、不执行任何钩子 |
| `hooks.timeout_s` | `5` | `(0, 60]` | 超上限截断为 60 并告警；非数值 / `<=0` 回落 5 |
| `hooks.on_error` | `block` | `block` / `allow` / `warn` | 非法值回落 `block`（fail-closed） |
| `hooks.entries` | 空 | 映射列表 | **只**从 `config.yaml` 结构化段读；无 CLI flag / env 形态 |

- **单一真源**：前三个标量走 `ConfigSpec`（`map_to="hooks.<key>"`；`enabled` 常规曝光，
  另两项 `ADVANCED`）⇒ CLI flag `--hooks-enabled` / `--hooks-timeout-s` / `--hooks-on-error`、
  env `CORE_HOOKS_*`、yaml `hooks:` 段三面一一对应；优先级链 CLI > env > config.yaml > 缺省。
- **访问器**：`hooks_enabled() -> bool` / `hooks_timeout_s() -> float` /
  `hooks_on_error() -> str` / `hooks_entries() -> list[Any]`（`hooks` 为非结构化段，
  非法形态告警后按缺省处置，不阻断启动）。
- **YAML 面**：解析器/转储器支持**块序列**与**行内 flow** 列表/映射 —— `hooks.entries`
  经 `write_patch` 重写后 round-trip 保真（此前只支持映射，序列会被丢弃）。
- **消费方**：组合根仅在 `hooks_enabled()` 为真时构造 `HookManager` 并接入四个 loop 与
  `MemoryStore(write_observer=...)`；关闭时注入面为 `None` / 空列表 ⇒ 既有路径逐字不变。
- 口径来源：`doc/openspec/specs/hooks/spec.md`「钩子声明面」（change `0269` 实现）。

### 2.14 embedding 模型端点推导与强制（change `0271` / ADR-0261、change `0289` / ADR-0279，台账 E207/E225）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `llm.embedding_auto` | **`true`** | 布尔（`true/false`·`yes/no`·`on/off`·`1/0`） | 未显式声明 `embedding_model` 时按端点表推导默认模型；非法值阻断启动 |
| `llm.embedding_required` | **`false`** | 同上（与 `embedding_auto` 同集） | 开启时有效 embedding 模型为空 ⇒ **校验期阻断启动**；非法值阻断启动 |

- **有效值属性**：`LLMConfig.effective_embedding_model` —— 显式 `embedding_model` 非空时恒用它；
  否则 `embedding_auto` 开启时按 `configuration/embedding_models.py::default_embedding_model(endpoint)`
  推导；开关关闭或端点未命中 ⇒ 空串。推导**不回写字段**，热更新基线仍取显式值（换端点自动跟随）。
- **强制开关**（change `0289` / ADR-0279）：`llm.embedding_required` 开启时，
  `ConfigManager.validate_schema` 在有效值为空时追加错误并阻断 `load()` / `apply_change()`；
  错误只含键名与可操作提示，**不回显 endpoint / 密钥**。该开关只断言「模型已确定」，
  **不探测网络可达性**：调用期失败仍按既有路径降级词法（见 memory 接口）。
- **端点表**：静态、小而有据（`api.openai.com` → `text-embedding-3-small`、`open.bigmodel.cn` →
  `embedding-3`、`dashscope.aliyuncs.com` → `text-embedding-v3`、`api.siliconflow.cn` →
  `BAAI/bge-m3`），按主机名精确或子域匹配；未命中不猜。表不引入配置键，不是第二真源。
- **消费方**：组合根用有效值构造单一 `embed_provider`（记忆 `batch_embed(LLMEmbedder)` 与
  RAG `LLMEmbedder` 共用）；有效值为空 ⇒ 记忆词法 / RAG `HashEmbedder`（与引入前逐字一致）。
  CLI 启动提示按有效值判断：为空 ⇒ 词法提示；仅推导 ⇒「按端点自动选用 …」一次。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「LLM 提供商配置（必选）」（**MODIFIED**）。

### 2.15 工具注入范围（change `0272` / ADR-0262，台账 E208）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `loop.tool_scope` | **`auto`** | `all` / `auto`（大小写不敏感、忽略首尾空白） | 请求侧工具参数 schema 注入范围；非法值**校验期阻断启动** |

- **三面**：CLI `--loop.tool-scope` / env `CORE_LOOP_TOOL_SCOPE` / yaml `loop.tool_scope`
  （priority CLI > env > yaml，同既有配置链）。
- **访问器**：`ConfigManager.tool_scope() -> str` —— 无配置源时返回 `auto`；返回值归一为小写、
  去首尾空白。
- **消费方**：只有组合根的**主 planner** 注入该值（`LLMPlanner(..., tool_scope=config.tool_scope())`）。
  `LLMPlanner` 构造缺省仍是 `all`（库级保守缺省，既有直接构造逐字不变）；子 Agent / 神兽 / 宠物
  不注入该值。
- **语义**：`auto` 仅在工具数 > 8 且 `tools.schema_read` 已注册时收窄**请求侧** schema；
  `all` 恒注入全部（kill-switch，与引入前逐字一致）。只影响 `LLMRequest.tools`，不改变工具注册、
  权限、coeffect、撤销或去重（详见 `loop-interface.md` §3.3）。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「工具注入范围配置」（**ADDED**）。

### 2.16 无人值守配置（change `0280` / ADR-0270，台账 E216）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `permission.auto_approve_coeffects` | `""` | 逗号分隔的 `namespace:action` 条目（全角逗号亦可；去空白/去重） | auto-approve 的允许面；空 = 不限制；仅在该模式生效 |
| `permission.auto_approve_commands` | `""` | 逗号分隔的 `tools.code_run:<命令前缀>` 条目（全角逗号亦可；前缀非空、不含 shell 元字符） | auto-approve 的命令允许面（change 0282）；空 = 不限制；仅在该模式生效 |
| `orchestration.task_timeout` | `0` | **≥0 的整数**（秒；`bool` 非法） | 整任务墙钟（CLI `task` 入口）；`0` = 不设限 |
| `orchestration.task_token_budget` | `0` | **≥0 的整数**（`bool` 非法） | 整任务 token 预算（调度器累计记账）；`0` = 不设限 |
| `orchestration.failure_notify_file` | `""` | 字符串（路径） | 任务失败 JSONL 通知文件；空 = 关闭 |

- **三面**：CLI `--permission.auto-approve-coeffects` / `--permission.auto-approve-commands` /
  `--orchestration.task-timeout` / `--orchestration.task-token-budget` /
  `--orchestration.failure-notify-file`；env `CORE_PERMISSION_AUTO_APPROVE_COEFFECTS` /
  `CORE_PERMISSION_AUTO_APPROVE_COMMANDS` / `CORE_ORCHESTRATION_TASK_TIMEOUT` /
  `CORE_ORCHESTRATION_TASK_TOKEN_BUDGET` / `CORE_ORCHESTRATION_FAILURE_NOTIFY_FILE`；yaml
  同名点路径。优先链 CLI > env > config.yaml > 缺省。
- **访问器**：`ConfigManager.permission_auto_approve_coeffects() -> list[str]`（已解析去重）/
  `permission_auto_approve_commands() -> dict[str, tuple[str, ...]]` /
  `orchestration_task_timeout() -> int` / `orchestration_task_token_budget() -> int` /
  `orchestration_failure_notify_file() -> str`。
- **校验期拒绝（不静默兜底）**：条目非 `namespace:action` 形态（小写字母起头，
  `[a-z0-9_-]`）⇒「非法 auto-approve 允许面条目」；命令条目非
  `tools.code_run:<非空前缀>` 或前缀含 shell 元字符 ⇒「非法 auto-approve 命令允许面条目」
  （**不回显取值**，前缀可能内嵌令牌）；`task_timeout` / `task_token_budget` 非 ≥0 整数 ⇒
  「非法整任务超时」/「非法整任务 token 预算」；`failure_notify_file` 非字符串 ⇒
  「非法失败通知文件」。均阻断启动。
- **消费方**：组合根把允许面注入 `PermissionGuard(allowed_coeffects=...)`（空列表 ⇒ `None`
  不限制）与 `allowed_commands=...`（空映射 ⇒ `{}` 不限制），把 `task_token_budget` 注入
  `TaskScheduler`；`task_timeout` 与 `failure_notify_file` 只由 CLI `task` 入口读取
  （`serve` / TUI 不受约束）。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「无人值守配置项」（**ADDED**）。

### 2.17 失败通知 webhook 配置（change `0281` / ADR-0271，台账 E217）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `orchestration.failure_notify_webhook` | `""` | 空串，或 `http`/`https` 绝对 URL（scheme 与 host 均非空） | 任务失败远程 JSON 推送端点；空 = 关闭 |

- **三面**：CLI `--orchestration.failure-notify-webhook`；env
  `CORE_ORCHESTRATION_FAILURE_NOTIFY_WEBHOOK`；yaml 同名点路径。优先链 CLI > env >
  config.yaml > 缺省（空串）。
- **访问器**：`ConfigManager.orchestration_failure_notify_webhook() -> str`（配置未加载时回落
  空串）。
- **校验期拒绝（不静默兜底）**：非字符串，或非空取值不是 `http(s)` + 非空 host 的绝对 URL
  ⇒「非法失败通知 webhook」（阻断启动）。错误信息只报键名与合法形态，**不回显 URL 取值**
  （URL 可能内嵌令牌）。
- **消费方**：只由 CLI `task` 入口（含自动续跑）读取并传给 `entry._notify_failure`；与
  `failure_notify_file` 相互独立。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「失败通知 webhook 配置」（**ADDED**）。

### 2.18 工作树隔离配置（change `0284` / ADR-0274，台账 E220）

| 键 | 缺省 | 约束 | 说明 |
|---|---|---|---|
| `orchestration.worktree_isolation` | `false` | `bool` 或 `true` / `false`（大小写不敏感、去空白） | 每次 `tools.delegate` 在独立 git worktree 中运行；false = 关闭 |

- **三面**：CLI `--orchestration.worktree-isolation`；env
  `CORE_ORCHESTRATION_WORKTREE_ISOLATION`；yaml 同名点路径。优先链 CLI > env > config.yaml > 缺省。
- **访问器**：`ConfigManager.orchestration_worktree_isolation() -> bool`，归一规则与
  `orchestration_auto_resume()` 相同。
- **校验期拒绝（不静默兜底）**：非 `bool` 且非 `true|false` 字符串 ⇒
  「非法工作树隔离开关: orchestration.worktree_isolation=…」（阻断启动）。
- **消费方**：`build_runtime` 仅在 true 时构造 `WorktreeManager`
  （`$CORE_STATE_DIR/worktrees`）并注册 `worktree:read` / `worktree:write` coeffect 与两个
  `tools.worktree.*` 工具；false ⇒ 工具面 / 结果形状 / 持久化字段逐字不变。
- 口径来源：`doc/openspec/specs/configuration/spec.md`「工作树隔离配置」（**ADDED**）。
