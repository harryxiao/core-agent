"""配置管理器（ConfigManager）。

以 config.yaml 为单一收口：env 覆盖 yaml、缺省取默认值；LLM 配置必选
（缺失阻断启动）；模块级 feature flag 缺省关闭；密钥走 env/keychain 分级
存储（yaml 拒绝明文）；schema 校验通过才生效，变更经 EffectTracker 可逆。

对应规格：doc/openspec/specs/configuration/spec.md
接口：doc/03-interfaces/configuration-interface.md §2
"""

from __future__ import annotations

import os
import time
import warnings
from collections.abc import Mapping
from pathlib import Path
from typing import Any, cast

from core.plugin_registry import CoeffectResolver, Effect, EffectTracker

from .errors import ConfigurationError
from .models import (
    AppConfig,
    ConfigExposure,
    ConfigSpec,
    IMConfig,
    JudgmentConfig,
    LLMConfig,
    PetConfig,
    ValidationResult,
)

# 熔断阈值/冷却缺省口径来源：doc/openspec/specs/constraints/spec.md「容错中间件」
# （配置层不 import 能力层，故缺省值在此复述；变更规格缺省时两处同改）
_DEFAULT_FAILURE_THRESHOLD = 5
_DEFAULT_COOLDOWN_S = 30.0

# 配置项单一真源（全量声明）：CLI flag / env / yaml 三面由 ConfigSpec 生成，禁止硬编码第二真源。
_CONFIG_SPECS: list[ConfigSpec] = [
    ConfigSpec(
        "llm.provider", "--llm.provider", "CORE_LLM_PROVIDER", default="", map_to="llm.provider"
    ),
    ConfigSpec("llm.model", "--llm.model", "CORE_LLM_MODEL", default="", map_to="llm.model"),
    ConfigSpec(
        "llm.endpoint", "--llm.endpoint", "CORE_LLM_ENDPOINT", default="", map_to="llm.endpoint"
    ),
    ConfigSpec(
        "llm.api_key",
        "--llm.api-key",
        "CORE_LLM_API_KEY",
        default="",
        map_to="llm.api_key",
        exposure=ConfigExposure.HIDDEN,
    ),
    ConfigSpec(
        "llm.embedding_model",
        "--llm.embedding-model",
        "CORE_LLM_EMBEDDING_MODEL",
        default="",
        map_to="llm.embedding_model",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "im.gateway",
        "--im.gateway",
        "CORE_IM_GATEWAY",
        default="",
        map_to="im.gateway",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "im.corp-id",
        "--im.corp-id",
        "CORE_IM_CORP_ID",
        default="",
        map_to="im.corp_id",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "im.secret",
        "--im.secret",
        "CORE_IM_SECRET",
        default="",
        map_to="im.secret",
        exposure=ConfigExposure.HIDDEN,
    ),
    ConfigSpec(
        "permission.mode",
        "--permission-mode",
        "CORE_PERMISSION_MODE",
        default="interactive",
        map_to="permission.mode",
    ),
    ConfigSpec(
        "pet.enabled",
        "--pet-enabled",
        "CORE_PET_ENABLED",
        default=False,
        map_to="pet.enabled",
    ),
    ConfigSpec(
        "pet.persons_dir",
        "--pet-dir",
        "CORE_PET_DIR",
        default="persons",
        map_to="pet.persons_dir",
    ),
    ConfigSpec(
        "judgment.provider",
        "--judgment.provider",
        "CORE_JUDGMENT_PROVIDER",
        default="",
        map_to="judgment.provider",
    ),
    ConfigSpec(
        "judgment.model",
        "--judgment.model",
        "CORE_JUDGMENT_MODEL",
        default="",
        map_to="judgment.model",
    ),
    ConfigSpec(
        "judgment.base_url",
        "--judgment.base-url",
        "CORE_JUDGMENT_BASE_URL",
        default="",
        map_to="judgment.base_url",
    ),
    ConfigSpec(
        "judgment.api_key",
        "--judgment.api-key",
        "CORE_JUDGMENT_API_KEY",
        default="",
        map_to="judgment.api_key",
        exposure=ConfigExposure.HIDDEN,
    ),
    ConfigSpec(
        "judgment.confidence_threshold",
        "--judgment.confidence-threshold",
        "CORE_JUDGMENT_CONFIDENCE_THRESHOLD",
        default=0.7,
        map_to="judgment.confidence_threshold",
    ),
    ConfigSpec(
        "constraints.failure_threshold",
        "--constraints.failure-threshold",
        "CORE_CONSTRAINTS_FAILURE_THRESHOLD",
        default=_DEFAULT_FAILURE_THRESHOLD,
        map_to="constraints.failure_threshold",
    ),
    ConfigSpec(
        "constraints.cooldown_s",
        "--constraints.cooldown-s",
        "CORE_CONSTRAINTS_COOLDOWN_S",
        default=_DEFAULT_COOLDOWN_S,
        map_to="constraints.cooldown_s",
    ),
]

_FEATURE_ENV_PREFIX = "CORE_FEATURES_"

_BOOL_NULL: dict[str, Any] = {"true": True, "false": False, "null": None, "~": None}


def _opt_str(value: Any) -> str | None:
    """yaml 可选字符串：缺省/空串归一为 None（不下发该字段）。"""
    return str(value) if value else None


def _default_user_dir() -> Path:
    """用户级配置目录（config.yaml 回落位 + .env 兜底位）。"""
    return Path.home() / ".core-agent"


def _default_yaml_path() -> Path:
    """默认发现链：cwd config.yaml 优先，缺失回落 ~/.core-agent/config.yaml。"""
    cwd = Path("config.yaml")
    if cwd.exists():
        return cwd
    fallback = _default_user_dir() / "config.yaml"
    if fallback.exists():
        return fallback
    return cwd  # 均缺失：保持「配置文件不存在: config.yaml」报错语义


def _load_env_file(path: Path) -> dict[str, str]:
    """读取 KEY=VALUE 行（跳过注释与空行）；仅作进程 env 的兜底源。"""
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


class ConfigManager:
    """配置加载 / 校验 / 密钥解析 / 功能开关 / 变更即生效。"""

    def __init__(  # noqa: PLR0913 — 注入面为 6 项，均为可选依赖注入
        self,
        yaml_path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        keychain: CoeffectResolver | None = None,
        effects: EffectTracker | None = None,
        cli: Mapping[str, Any] | None = None,
        specs: list[ConfigSpec] | None = None,
    ) -> None:
        self._yaml_path = Path(yaml_path) if yaml_path else _default_yaml_path()
        if environ is not None:
            self._environ = dict(environ)
        else:
            self._environ = dict(os.environ)
            for key, value in _load_env_file(_default_user_dir() / ".env").items():
                self._environ.setdefault(key, value)  # 进程 env 优先于 .env
        self._keychain = keychain if keychain is not None else CoeffectResolver()
        self._effects = effects if effects is not None else EffectTracker()
        self._cli = dict(cli) if cli is not None else {}
        self._specs = list(specs) if specs is not None else list(_CONFIG_SPECS)
        self._config: AppConfig | None = None

    # ---- 加载与校验 ----

    def load(self) -> AppConfig:
        """加载 config.yaml：CLI 覆盖 env 覆盖 yaml，校验通过才生效；LLM 缺失则阻断。"""
        map_to_errors = validate_map_to(self._specs)
        if map_to_errors:
            raise ConfigurationError("; ".join(map_to_errors))
        raw = self._read_yaml()
        merged = self._apply_env(raw)
        merged = self._apply_cli(merged)
        config = self._build_config(merged)
        result = self.validate_schema(config)
        if not result.ok:
            raise ConfigurationError("; ".join(result.errors))
        for warning in result.warnings:
            warnings.warn(warning, stacklevel=2)  # 仅告警不阻断（账本 E18）
        self._config = config
        return config

    def validate_schema(self, config: AppConfig) -> ValidationResult:
        """schema 校验：密钥引用同口径（明文/空/不可解析）、LLM 必选项与权限模式枚举。"""
        errors: list[str] = []
        for label, ref in _secret_refs(config):
            error = _secret_ref_error(label, ref, resolvable=self._resolvable(ref))
            if error is not None:
                errors.append(error)
        for key, value in (
            ("provider", config.llm.provider),
            ("model", config.llm.model),
            ("endpoint", config.llm.endpoint),
        ):
            if not value:
                errors.append(f"缺失 LLM 配置项: llm.{key}")
        perm = cast("dict[str, Any]", config.extra.get("permission") or {})
        mode = str(perm.get("mode", _DEFAULT_PERMISSION_MODE))
        if mode not in _PERMISSION_MODES:
            errors.append(
                f"非法权限模式: permission.mode={mode}（可选：{'/'.join(_PERMISSION_MODES)}）"
            )
        cons = cast("dict[str, Any]", config.extra.get("constraints") or {})
        errors.extend(_circuit_breaker_errors(cons))
        return ValidationResult(
            ok=not errors, errors=errors, warnings=self._unknown_section_warnings(config)
        )

    def _known_sections(self) -> set[str]:
        """已知顶层段：结构化段 + ConfigSpec 声明段 + 有运行时语义的 extra 已知段。"""
        declared = {spec.map_to.split(".", 1)[0] for spec in self._specs if "." in spec.map_to}
        return set(_STRUCTURED_SECTIONS) | set(_KNOWN_EXTRA_SECTIONS) | declared

    def _unknown_section_warnings(self, config: AppConfig) -> list[str]:
        """未知顶层段告警（仅告警不阻断）：段名不在已知段内 → 提示拼写并说明收纳位置。"""
        known = self._known_sections()
        return [
            f"未知配置段: {key}（不在已知段 {', '.join(sorted(known))} 之内；"
            f"已收纳进 extra 且未做校验 —— 若为拼写错误请订正）"
            for key in sorted(set(config.extra) - known)
        ]

    def _resolvable(self, ref: str) -> bool:
        """密钥引用能否经 env/keychain 解析（不返回明文）。"""
        try:
            self.resolve_secret(ref)
        except ConfigurationError:
            return False
        return True

    # ---- 密钥与开关 ----

    def resolve_secret(self, ref: str) -> str:
        """从 env/keychain 解析 ${VAR} 引用，返回明文（仅调用方使用，不落日志）。"""
        name = _parse_ref(ref)
        if name is None:
            raise ConfigurationError(f"非法密钥引用: {ref}")  # noqa: TRY003
        if name in self._environ:
            return self._environ[name]
        try:
            return self._keychain.resolve_secret(f"secret:{name}")
        except KeyError:
            raise ConfigurationError(f"密钥引用未解析: {ref}") from None  # noqa: TRY003

    def is_enabled(self, module: str) -> bool:
        """feature flag 查询：缺省关闭，未显式开启的模块不加载、不初始化。"""
        if self._config is None:
            return False
        return self._config.features.get(module, False)

    def is_disabled(self, module: str) -> bool:
        """模块级 feature flag 的**装配裁剪**判据：只有显式 false 才为真（缺省不关）。

        与 ``is_enabled`` 极性相反、用途不同 —— ``is_enabled`` 是「显式开启查询」（缺省 false，
        供缺省关的模块自查二级开关）；本谓词服务于**缺省装配**的可选模块，由组合根消费
        （门控名单归组合根：``core.runtime.GATABLE_MODULES``，配置层不认识模块名）。
        """
        if self._config is None:
            return False
        return self._config.features.get(module) is False

    def permission_mode(self) -> str:
        """权限模式查询：缺省 interactive（对齐 permission「权限模式」四档，取值已过校验）。"""
        if self._config is None:
            return _DEFAULT_PERMISSION_MODE
        perm = cast(dict[str, Any], self._config.extra.get("permission") or {})
        return str(perm.get("mode", _DEFAULT_PERMISSION_MODE))

    def circuit_breaker(self) -> tuple[int, float]:
        """熔断阈值/冷却查询 → ``(failure_threshold, cooldown_s)``，缺省 ``(5, 30.0)``。

        对齐 constraints「容错中间件」；取值已过校验（整数 ≥1 / 数值 ≥0），故此处只做
        env/CLI 字符串归一（``int()`` / ``float()``），不设二次兜底。
        """
        if self._config is None:
            return _DEFAULT_FAILURE_THRESHOLD, _DEFAULT_COOLDOWN_S
        raw = cast(dict[str, Any], self._config.extra.get("constraints") or {})
        return (
            int(raw.get("failure_threshold", _DEFAULT_FAILURE_THRESHOLD)),
            float(raw.get("cooldown_s", _DEFAULT_COOLDOWN_S)),
        )

    # ---- 变更即生效 ----

    def apply_change(self, patch: dict[str, Any]) -> AppConfig:
        """校验 patch 合并结果，通过才生效；写入可逆（失败可回滚）。"""
        if self._config is None:
            raise ConfigurationError("配置尚未加载，无法 apply_change")  # noqa: TRY003
        candidate = _merge_patch(self._config, patch)
        result = self.validate_schema(candidate)
        if not result.ok:
            raise ConfigurationError("; ".join(result.errors))
        previous = self._config
        self._effects.record(
            Effect(
                op="config_apply",
                target="app_config",
                undo=lambda: self._restore(previous),
                reversible=True,
                coeffect=[],
                trace_id="config",
                ts=time.time(),
            )
        )
        self._config = candidate
        return candidate

    def _restore(self, config: AppConfig) -> None:
        self._config = config

    def write_patch(self, patch: dict[str, Any]) -> None:
        """把 patch 写回 config.yaml（只合并用户 patch，不落 env/cli 覆盖与明文密钥）。

        写回基于 yaml 文件原文（``_read_yaml``，未叠加 env/cli），``${VAR}`` 引用
        不解析、原样保留。明文密钥在 ``apply_change`` 已被 ``validate_schema`` 拒绝，
        故不会进入写回。
        """
        raw = self._read_yaml()
        _merge_raw(raw, patch)
        self._yaml_path.write_text(_dump_yaml(raw), encoding="utf-8")

    # ---- 内部：读取 / 覆盖 / 构造 ----

    def _read_yaml(self) -> dict[str, Any]:
        if not self._yaml_path.exists():
            raise ConfigurationError(f"配置文件不存在: {self._yaml_path}")  # noqa: TRY003
        text = self._yaml_path.read_text(encoding="utf-8")
        return _parse_yaml_subset(text)

    def _apply_env(self, raw: dict[str, Any]) -> dict[str, Any]:
        for spec in self._specs:
            if spec.env_var in self._environ:
                _set_path(raw, spec.map_to, self._environ[spec.env_var])
        for env_key, value in self._environ.items():
            if env_key.startswith(_FEATURE_ENV_PREFIX):
                name = env_key[len(_FEATURE_ENV_PREFIX) :].lower()
                raw.setdefault("features", {})[name] = value.lower() in ("true", "1", "yes")
        return raw

    def _apply_cli(self, merged: dict[str, Any]) -> dict[str, Any]:
        for path, value in self._cli.items():
            _set_path(merged, path, value)
        return merged

    def _build_config(self, merged: dict[str, Any]) -> AppConfig:
        llm_raw = cast(dict[str, Any], merged.get("llm") or {})
        llm = LLMConfig(
            provider=str(llm_raw.get("provider", "")),
            model=str(llm_raw.get("model", "")),
            endpoint=str(llm_raw.get("endpoint", "")),
            api_key_ref=str(llm_raw.get("api_key") or ""),
            reasoning_effort=_opt_str(llm_raw.get("reasoning_effort")),
            embedding_model=str(llm_raw.get("embedding_model", "")),
        )
        features_raw = cast(dict[str, Any], merged.get("features") or {})
        features = {str(k): bool(v) for k, v in features_raw.items()}
        im = None
        im_raw = cast(dict[str, Any], merged.get("im") or {})
        if im_raw:
            im = IMConfig(
                gateway=str(im_raw.get("gateway", "")),
                corp_id=str(im_raw.get("corp_id", "")),
                secret_ref=str(im_raw.get("secret") or ""),
            )
        pet = None
        pet_raw = cast(dict[str, Any], merged.get("pet") or {})
        if pet_raw:
            enabled_raw = pet_raw.get("enabled", False)
            pet = PetConfig(
                enabled=(
                    enabled_raw
                    if isinstance(enabled_raw, bool)
                    else str(enabled_raw).lower() in ("true", "1", "yes")
                ),
                persons_dir=str(pet_raw.get("persons_dir", "persons")),
            )
        judgment = None
        judgment_raw = cast(dict[str, Any], merged.get("judgment") or {})
        if judgment_raw:
            threshold_raw = judgment_raw.get("confidence_threshold", 0.7)
            judgment = JudgmentConfig(
                provider=str(judgment_raw.get("provider", "")),
                model=str(judgment_raw.get("model", "")),
                base_url=str(judgment_raw.get("base_url", "")),
                api_key_ref=str(judgment_raw.get("api_key") or ""),
                confidence_threshold=(
                    threshold_raw if isinstance(threshold_raw, (int, float)) else 0.7
                ),
            )
        extra = {
            k: v for k, v in merged.items() if k not in {"llm", "features", "im", "pet", "judgment"}
        }
        return AppConfig(llm=llm, features=features, im=im, pet=pet, judgment=judgment, extra=extra)


# 已知顶层段口径（change `0064` / 账本 E18）：
#   _STRUCTURED_SECTIONS —— `_build_config` 逐段解析的五个结构化段；
#   _KNOWN_EXTRA_SECTIONS —— 寄居 `extra` 但有运行时语义的已知段（本模块消费 permission.mode）；
#   ConfigSpec 声明段（`map_to` 前缀）在 `_known_sections` 中并入 ⇒ 新增 Spec 自动进白名单。
_STRUCTURED_SECTIONS = frozenset({"llm", "features", "im", "pet", "judgment"})
_KNOWN_EXTRA_SECTIONS = frozenset({"permission"})

# 权限模式四档口径来源：doc/openspec/specs/permission/spec.md「权限模式」
# （配置层不 import 能力层，故词表在此复述；变更规格四档时两处同改）
_PERMISSION_MODES = ("read-only", "interactive", "auto-approve", "high-risk-block")
_DEFAULT_PERMISSION_MODE = "interactive"


def _circuit_breaker_errors(raw: dict[str, Any]) -> list[str]:
    """熔断阈值/冷却取值校验（对齐 constraints「容错中间件」）。

    阈值须为 **≥1 的整数**、冷却须为 **≥0 的数值**；``bool`` 视作非法（``true`` 不是次数）。
    非法取值**阻断启动**：静默兜底会把配置错误变成运行时的诡异行为（如阈值 0 ⇒ 首个失败即熔断）。
    """
    errors: list[str] = []
    threshold = _as_number(raw.get("failure_threshold", _DEFAULT_FAILURE_THRESHOLD))
    if threshold is None or threshold < 1 or threshold != int(threshold):
        errors.append(
            f"非法熔断阈值: constraints.failure_threshold={raw.get('failure_threshold')}"
            "（须为 ≥1 的整数）"
        )
    cooldown = _as_number(raw.get("cooldown_s", _DEFAULT_COOLDOWN_S))
    if cooldown is None or cooldown < 0:
        errors.append(
            f"非法熔断冷却: constraints.cooldown_s={raw.get('cooldown_s')}（须为 ≥0 的数值）"
        )
    return errors


def _as_number(value: Any) -> float | None:
    """数值解析：``int``/``float`` 直通，字符串按数值解析；``bool`` 与非数值 → None。"""
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def _secret_ref_error(label: str, ref: str, *, resolvable: bool) -> str | None:
    """单个密钥引用的校验结论（明文 / 空 / 不可解析 → 错误文案；合规 → None）。"""
    if _looks_like_secret(ref):
        return f"{label} 必须为 ${{VAR}} 引用，禁止明文密钥"
    if not ref:
        return f"缺失密钥引用: {label}"
    if not resolvable:
        return f"{label} 引用无法解析"
    return None


def _secret_refs(config: AppConfig) -> list[tuple[str, str]]:
    """待校验的密钥引用：主 LLM 必选，IM / 决策模型按段的参与条件（见 configuration spec）。"""
    refs = [("llm.api_key", config.llm.api_key_ref)]
    if config.im is not None:
        refs.append(("im.secret", config.im.secret_ref))
    if config.judgment is not None and config.judgment.provider:
        refs.append(("judgment.api_key", config.judgment.api_key_ref))
    return refs


def _parse_ref(ref: str) -> str | None:
    """提取 ${VAR} 中的 VAR；非引用格式返回 None。"""
    if ref.startswith("${") and ref.endswith("}"):
        return ref[2:-1]
    return None


def _looks_like_secret(ref: str) -> bool:
    """非空且非 ${VAR} 引用 => 视为明文密钥。"""
    return bool(ref) and _parse_ref(ref) is None


def _merge_patch(config: AppConfig, patch: dict[str, Any]) -> AppConfig:
    """把 patch 浅合并到当前配置，产出候选 AppConfig（不落盘）。"""
    llm_raw = {
        "provider": config.llm.provider,
        "model": config.llm.model,
        "endpoint": config.llm.endpoint,
        "api_key": config.llm.api_key_ref,
    }
    llm_raw.update(cast(dict[str, Any], patch.get("llm") or {}))
    features = dict(config.features)
    features_patch = cast(dict[str, Any], patch.get("features") or {})
    features.update({str(k): bool(v) for k, v in features_patch.items()})
    im = config.im
    im_patch = cast(dict[str, Any], patch.get("im") or {})
    if im_patch:
        base = {
            "gateway": im.gateway if im else "",
            "corp_id": im.corp_id if im else "",
            "secret": im.secret_ref if im else "",
        }
        base.update(im_patch)
        im = IMConfig(
            gateway=str(base["gateway"]),
            corp_id=str(base["corp_id"]),
            secret_ref=str(base["secret"]),
        )
    return AppConfig(
        llm=LLMConfig(
            provider=str(llm_raw["provider"]),
            model=str(llm_raw["model"]),
            endpoint=str(llm_raw["endpoint"]),
            api_key_ref=str(llm_raw["api_key"]),
            reasoning_effort=_opt_str(llm_raw.get("reasoning_effort")),
            embedding_model=str(llm_raw.get("embedding_model", "")),
        ),
        features=features,
        im=im,
        pet=config.pet,
        judgment=config.judgment,
        extra=dict(config.extra),
    )


def _parse_yaml_subset(text: str) -> dict[str, Any]:
    """极简 YAML 子集解析：仅支持 config.yaml 所需的缩进映射 + 标量。

    覆盖：嵌套 ``key: value``、``true/false/null``、整数/浮点、引号字符串、
    ``${VAR}`` 引用与 ``#`` 注释；不含列表 / 锚点 / 多行块。
    """
    root: dict[str, Any] = {}
    stack: list[tuple[int, dict[str, Any]]] = [(-1, root)]
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip(" "))
        if ":" not in line:
            raise ConfigurationError(f"无法解析的 yaml 行: {stripped}")  # noqa: TRY003
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        if not stack:
            raise ConfigurationError(f"yaml 缩进错误: {stripped}")  # noqa: TRY003
        parent = stack[-1][1]
        if value == "":
            child: dict[str, Any] = {}
            parent[key] = child
            stack.append((indent, child))
        else:
            parent[key] = _parse_scalar(value)
    return root


def _parse_scalar(value: str) -> Any:
    if len(value) > 1 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    lowered = value.lower()
    if lowered in _BOOL_NULL:
        return _BOOL_NULL[lowered]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _merge_raw(raw: dict[str, Any], patch: dict[str, Any]) -> None:
    """递归浅合并 patch 进 raw（原地），未触及的键原样保留。"""
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(raw.get(key), dict):
            _merge_raw(cast(dict[str, Any], raw.get(key)), cast(dict[str, Any], value))
        else:
            raw[key] = value


def _dump_yaml(data: dict[str, Any], indent: int = 0) -> str:
    """嵌套 dict → 缩进 yaml（仅标量 + 映射，与 ``_parse_yaml_subset`` 对称）。"""
    lines: list[str] = []
    pad = "  " * indent
    for key, value in data.items():
        if isinstance(value, dict):
            lines.append(f"{pad}{key}:")
            lines.append(_dump_yaml(cast(dict[str, Any], value), indent + 1))
        else:
            lines.append(f"{pad}{key}: {_dump_scalar(value)}")
    return "\n".join(lines)


def _dump_scalar(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "null"
    return str(value)


# ---- ConfigSpec 单一真源：优先级链解析 / 三面生成 / map_to 校验 ----


def _set_path(root: dict[str, Any], path: str, value: Any) -> None:
    """把点分路径写入嵌套 dict，自动补建中间层。"""
    parts = path.split(".")
    node = root
    for part in parts[:-1]:
        node = node.setdefault(part, {})
    node[parts[-1]] = value


def _find_spec(specs: list[ConfigSpec], key: str) -> ConfigSpec | None:
    for spec in specs:
        if spec.key == key:
            return spec
    return None


def validate_map_to(specs: list[ConfigSpec]) -> list[str]:
    """校验 ConfigSpec 的 map_to 合法（非空点分路径、无重复），返回错误列表。"""
    errors: list[str] = []
    seen: dict[str, str] = {}
    for spec in specs:
        if not spec.map_to or not all(seg for seg in spec.map_to.split(".")):
            errors.append(f"ConfigSpec[{spec.key}] map_to 非法: {spec.map_to!r}")
            continue
        if spec.map_to in seen:
            errors.append(
                f"ConfigSpec[{spec.key}] map_to 冲突: {spec.map_to} 已由 {seen[spec.map_to]} 声明"
            )
        else:
            seen[spec.map_to] = spec.key
    return errors


def config_specs() -> list[ConfigSpec]:
    """返回 ConfigSpec 单一真源清单的副本（ParamMapper 等消费）。"""
    return list(_CONFIG_SPECS)


def resolve(
    key: str,
    *,
    cli: Mapping[str, Any] | None = None,
    env: Mapping[str, str] | None = None,
    yaml: Mapping[str, Any] | None = None,
    specs: list[ConfigSpec] | None = None,
) -> Any:
    """按优先级链 CLI flag > env > config.yaml > 默认值 解析配置项（ConfigSpec 单一真源）。"""
    spec_list = specs if specs is not None else _CONFIG_SPECS
    spec = _find_spec(spec_list, key)
    cli = cli or {}
    env = env or {}
    yaml = yaml or {}
    if key in cli:
        return cli[key]
    if spec is not None and spec.env_var in env:
        return env[spec.env_var]
    if key in yaml:
        return yaml[key]
    return spec.default if spec is not None else None


def generate_cli_flags(specs: list[ConfigSpec] | None = None) -> list[str]:
    """由 ConfigSpec 生成 CLI 参数面。"""
    return [s.cli_flag for s in (specs if specs is not None else _CONFIG_SPECS)]


def generate_env_vars(specs: list[ConfigSpec] | None = None) -> list[str]:
    """由 ConfigSpec 生成 env 变量面。"""
    return [s.env_var for s in (specs if specs is not None else _CONFIG_SPECS)]


def generate_yaml_defaults(specs: list[ConfigSpec] | None = None) -> dict[str, Any]:
    """由 ConfigSpec 生成 yaml 默认值面（map_to -> default）。"""
    return {s.map_to: s.default for s in (specs if specs is not None else _CONFIG_SPECS)}
