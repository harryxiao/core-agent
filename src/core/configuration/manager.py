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
    LLMConfig,
    PetConfig,
    ValidationResult,
)

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
]

_FEATURE_ENV_PREFIX = "CORE_FEATURES_"

_BOOL_NULL: dict[str, Any] = {"true": True, "false": False, "null": None, "~": None}


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
        self._yaml_path = Path(yaml_path) if yaml_path else Path("config.yaml")
        self._environ = dict(environ) if environ is not None else dict(os.environ)
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
        self._config = config
        return config

    def validate_schema(self, config: AppConfig) -> ValidationResult:
        """schema 校验：拒绝 yaml 明文密钥，校验 LLM 必选项完整性。"""
        errors: list[str] = []
        if _looks_like_secret(config.llm.api_key_ref):
            errors.append("llm.api_key 必须为 ${VAR} 引用，禁止明文密钥")
        if config.im is not None and _looks_like_secret(config.im.secret_ref):
            errors.append("im.secret 必须为 ${VAR} 引用，禁止明文密钥")
        for key, value in (
            ("provider", config.llm.provider),
            ("model", config.llm.model),
            ("endpoint", config.llm.endpoint),
        ):
            if not value:
                errors.append(f"缺失 LLM 配置项: llm.{key}")
        if not config.llm.api_key_ref:
            errors.append("缺失 LLM 配置项: llm.api_key")
        else:
            try:
                self.resolve_secret(config.llm.api_key_ref)
            except ConfigurationError:
                errors.append("llm.api_key 引用无法解析")
        return ValidationResult(ok=not errors, errors=errors)

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

    def permission_mode(self) -> str:
        """权限模式查询：缺省 interactive（对齐 permission「权限模式」四档）。"""
        if self._config is None:
            return "interactive"
        perm = cast(dict[str, Any], self._config.extra.get("permission") or {})
        return str(perm.get("mode", "interactive"))

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
            api_key_ref=str(llm_raw.get("api_key", "")),
        )
        features_raw = cast(dict[str, Any], merged.get("features") or {})
        features = {str(k): bool(v) for k, v in features_raw.items()}
        im = None
        im_raw = cast(dict[str, Any], merged.get("im") or {})
        if im_raw:
            im = IMConfig(
                gateway=str(im_raw.get("gateway", "")),
                corp_id=str(im_raw.get("corp_id", "")),
                secret_ref=str(im_raw.get("secret", "")),
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
        extra = {k: v for k, v in merged.items() if k not in {"llm", "features", "im", "pet"}}
        return AppConfig(llm=llm, features=features, im=im, pet=pet, extra=extra)


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
        ),
        features=features,
        im=im,
        pet=config.pet,
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
