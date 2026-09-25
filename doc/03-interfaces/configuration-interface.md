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
    extra: dict                    # 其他模块扩展配置

@dataclass
class LLMConfig:
    provider: str                  # 提供商
    model: str                     # 模型
    endpoint: str                  # 端点
    api_key_ref: str               # api_key 的 ${VAR} 引用（非明文）

@dataclass
class IMConfig:
    gateway: str                   # 网关类型
    corp_id: str                   # 账户/ID
    secret_ref: str                # secret 的 ${VAR} 引用（非明文）

@dataclass
class ValidationResult:
    ok: bool                       # 校验是否通过
    errors: list[str]              # 失败原因（缺失 LLM 配置、yaml 明文密钥等）
```

---

## 2. ConfigManager 接口

```python
class ConfigManager:
    def load(self) -> AppConfig:
        """以 config.yaml 为单一收口加载：env 覆盖 yaml 值，未定义项取默认值兜底。"""

    def validate_schema(self, config: AppConfig) -> ValidationResult:
        """schema 校验：拒绝 yaml 明文密钥，校验通过才返回有效配置。"""

    def resolve_secret(self, ref: str) -> str:
        """从 env/keychain 解析敏感密钥引用（${VAR}），不落明文。"""

    def is_enabled(self, module: str) -> bool:
        """feature flag 查询：关闭的模块不加载、不初始化。"""

    def apply_change(self, patch: dict) -> AppConfig:
        """变更即生效：写入失败回滚到变更前完整配置，不留半写状态。"""
```
