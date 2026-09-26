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
from .models import AppConfig, IMConfig, LLMConfig, ValidationResult

# env 覆盖 yaml 的固定映射：env 变量名 -> (yaml 段, yaml 键)
_ENV_OVERRIDES: dict[str, tuple[str, str]] = {
    "CORE_LLM_PROVIDER": ("llm", "provider"),
    "CORE_LLM_MODEL": ("llm", "model"),
    "CORE_LLM_ENDPOINT": ("llm", "endpoint"),
    "CORE_LLM_API_KEY": ("llm", "api_key"),
    "CORE_IM_GATEWAY": ("im", "gateway"),
    "CORE_IM_CORP_ID": ("im", "corp_id"),
    "CORE_IM_SECRET": ("im", "secret"),
}

_FEATURE_ENV_PREFIX = "CORE_FEATURES_"

_BOOL_NULL: dict[str, Any] = {"true": True, "false": False, "null": None, "~": None}


class ConfigManager:
    """配置加载 / 校验 / 密钥解析 / 功能开关 / 变更即生效。"""

    def __init__(
        self,
        yaml_path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        keychain: CoeffectResolver | None = None,
        effects: EffectTracker | None = None,
    ) -> None:
        self._yaml_path = Path(yaml_path) if yaml_path else Path("config.yaml")
        self._environ = dict(environ) if environ is not None else dict(os.environ)
        self._keychain = keychain if keychain is not None else CoeffectResolver()
        self._effects = effects if effects is not None else EffectTracker()
        self._config: AppConfig | None = None

    # ---- 加载与校验 ----

    def load(self) -> AppConfig:
        """加载 config.yaml：env 覆盖 yaml，校验通过才生效；LLM 缺失则阻断。"""
        raw = self._read_yaml()
        merged = self._apply_env(raw)
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
        for env_key, (section, key) in _ENV_OVERRIDES.items():
            if env_key in self._environ:
                raw.setdefault(section, {})[key] = self._environ[env_key]
        for env_key, value in self._environ.items():
            if env_key.startswith(_FEATURE_ENV_PREFIX):
                name = env_key[len(_FEATURE_ENV_PREFIX) :].lower()
                raw.setdefault("features", {})[name] = value.lower() in ("true", "1", "yes")
        return raw

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
        extra = {k: v for k, v in merged.items() if k not in {"llm", "features", "im"}}
        return AppConfig(llm=llm, features=features, im=im, extra=extra)


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
