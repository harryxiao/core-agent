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
    errors: list[str]              # 失败原因（缺失 LLM 配置、yaml 明文密钥等）

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
        """schema 校验：拒绝 yaml 明文密钥，校验通过才返回有效配置。"""

    def resolve_secret(self, ref: str) -> str:
        """从 env/keychain 解析敏感密钥引用（${VAR}），不落明文。"""

    def is_enabled(self, module: str) -> bool:
        """feature flag 查询：关闭的模块不加载、不初始化。"""

    def permission_mode(self) -> str:
        """权限模式查询（缺省 interactive），映射 config.permission.mode。"""

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
