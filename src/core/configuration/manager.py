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
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any, cast

from core.plugin_registry import CoeffectResolver, Effect, EffectTracker

from .errors import ConfigurationError
from .model_windows import known_window
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

# 循环预算缺省口径来源：doc/openspec/specs/loop/spec.md「错误与预算控制」（同上，配置层复述）
_DEFAULT_MAX_ROUNDS = 10
_DEFAULT_OUTPUT_RESERVE = 8192
_DEFAULT_TOKEN_BUDGET = 65536
# 回灌轮数缺省口径来源：doc/openspec/specs/configuration/spec.md「循环预算配置」
_DEFAULT_HISTORY_TURNS = 20
# 压实步数阈值缺省口径来源：同规格「循环预算配置」（change 0182 / ADR-0173）。
# 与 `context.compactor._STEP_THRESHOLD` **同值两地**（configuration 不 import context —— 分层
# 方向；先例 `_DEFAULT_PERMISSION_MODE`）。一致性由 `test_config_default_matches_compactor_default`
# 钉住；缺省 **6 < `max_rounds` 缺省 10** ⇒ 步数维度可真正提前触发。
_DEFAULT_COMPACT_STEPS = 6

# 编排调度缺省口径来源：doc/openspec/specs/configuration/spec.md「编排调度配置」
# （change 0123）。`_DEFAULT_ORCHESTRATION_POLICY = "off"` ⇒ 缺省**不启用**难易度策略，
# 同波次仍按依赖拓扑并发（与引入前逐字一致）；并发上限默认与 `TaskScheduler` 构造缺省同值。
_DEFAULT_ORCHESTRATION_POLICY = "off"
_DEFAULT_ORCHESTRATION_MAX_CONCURRENCY = 4
# 策略词表（规格 `orchestration`「难易度感知的调度策略」；配置层不 import 能力层，故此处复述）
_ORCHESTRATION_POLICIES = ("off", "difficulty")

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
        "permission.sandbox.host_allowlist",
        "--permission.sandbox.host-allowlist",
        "CORE_SANDBOX_HOST_ALLOWLIST",
        default="",
        map_to="permission.sandbox.host_allowlist",
        exposure=ConfigExposure.ADVANCED,
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
    ConfigSpec(
        "llm.context_window",
        "--llm.context-window",
        "CORE_LLM_CONTEXT_WINDOW",
        default=0,
        map_to="llm.context_window",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "loop.output_reserve",
        "--loop.output-reserve",
        "CORE_LOOP_OUTPUT_RESERVE",
        default=_DEFAULT_OUTPUT_RESERVE,
        map_to="loop.output_reserve",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "loop.max_rounds",
        "--loop.max-rounds",
        "CORE_LOOP_MAX_ROUNDS",
        default=_DEFAULT_MAX_ROUNDS,
        map_to="loop.max_rounds",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "loop.history_turns",
        "--loop.history-turns",
        "CORE_LOOP_HISTORY_TURNS",
        default=_DEFAULT_HISTORY_TURNS,
        map_to="loop.history_turns",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "loop.compact_steps",
        "--loop.compact-steps",
        "CORE_LOOP_COMPACT_STEPS",
        default=_DEFAULT_COMPACT_STEPS,
        map_to="loop.compact_steps",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "orchestration.difficulty_policy",
        "--orchestration.difficulty-policy",
        "CORE_ORCHESTRATION_DIFFICULTY_POLICY",
        default=_DEFAULT_ORCHESTRATION_POLICY,
        map_to="orchestration.difficulty_policy",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "orchestration.max_concurrency",
        "--orchestration.max-concurrency",
        "CORE_ORCHESTRATION_MAX_CONCURRENCY",
        default=_DEFAULT_ORCHESTRATION_MAX_CONCURRENCY,
        map_to="orchestration.max_concurrency",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "loop.block_plan",
        "--loop.block-plan",
        "CORE_LOOP_BLOCK_PLAN",
        default=False,
        map_to="loop.block_plan",
        exposure=ConfigExposure.ADVANCED,
    ),
    ConfigSpec(
        "memory.importance_gate",
        "--memory-importance-gate",
        "CORE_MEMORY_IMPORTANCE_GATE",
        default=False,
        map_to="memory.importance_gate",
        exposure=ConfigExposure.ADVANCED,
    ),
]

_FEATURE_ENV_PREFIX = "CORE_FEATURES_"

# feature flag 取值集合（三面统一）；大小写不敏感。**不静默强转** —— 集合外取值校验期拒绝
# （`bool("off") is True` 会把 yaml 的「显式关闭」静默当作开启，故必须显式解析）。
_FEATURE_TRUE: frozenset[str] = frozenset({"true", "yes", "on", "1"})
_FEATURE_FALSE: frozenset[str] = frozenset({"false", "no", "off", "0"})

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

    def __init__(  # noqa: PLR0913 — 注入面为 7 项，均为可选依赖注入
        self,
        yaml_path: Path | str | None = None,
        *,
        environ: Mapping[str, str] | None = None,
        keychain: CoeffectResolver | None = None,
        effects: EffectTracker | None = None,
        cli: Mapping[str, Any] | None = None,
        specs: list[ConfigSpec] | None = None,
        known_modules: Iterable[str] | None = None,
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
        # 已知模块名集合（`features` 段子键校验用，账本 E20①）：由**拥有集合的层**（组合根
        # `runtime.GATABLE_MODULES`）经注入提供 —— 配置层仍不 import runtime、不硬编码模块名。
        # 缺省 None ⇒ 不校验子键（向后兼容：自定义键 / 测试夹具不告警）。
        self._known_modules = frozenset(known_modules) if known_modules is not None else None
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

    def config_value(self, key: str) -> Any:
        """单键解析：CLI flag > env > config.yaml > 默认值（ConfigSpec 单一真源）。

        与 ``load()`` 的分工：本方法**不校验、不阻断、不缓存**，供 CLI 层在装配前做前置
        判定（如 ``pet.enabled`` 门控）用；config.yaml 缺失按「无 yaml 层」处理（不抛
        ``ConfigurationError``），故无配置文件时仍按 env / CLI / 缺省解析 —— 前置判定
        只读单键，不应因整份配置尚未校验而失败。返回各层原文（env/CLI 为字符串），
        归一化由调用方负责（与 ``resolve`` 口径一致）。
        """
        yaml_layer: dict[str, Any] = {}
        if self._yaml_path.exists():
            yaml_layer = _flatten_by_specs(self._read_yaml(), self._specs)
        return resolve(key, cli=self._cli, env=self._environ, yaml=yaml_layer, specs=self._specs)

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
        errors.extend(_sandbox_errors(perm))
        cons = cast("dict[str, Any]", config.extra.get("constraints") or {})
        errors.extend(_circuit_breaker_errors(cons))
        loop_raw = cast("dict[str, Any]", config.extra.get("loop") or {})
        errors.extend(_loop_errors(loop_raw))
        errors.extend(_window_reserve_errors(config.llm.context_window, loop_raw))
        orch_raw = cast("dict[str, Any]", config.extra.get("orchestration") or {})
        errors.extend(_orchestration_errors(orch_raw))
        warnings = self._unknown_section_warnings(config) + self._unknown_feature_warnings(config)
        return ValidationResult(ok=not errors, errors=errors, warnings=warnings)

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

    def _unknown_feature_warnings(self, config: AppConfig) -> list[str]:
        """`features` 段未知模块名告警（账本 E20①，change `0085`）：仅当注入已知集合时校验。

        `features` 段子键是**模块名**（`features.<模块>`），模块名拼错 ⇒ `is_disabled(<正确名>)`
        查不到 ⇒ **静默 no-op**（如 `peet: false` 关不掉 `pet`）。已知集合由组合根经注入提供，
        未注入（``None``）⇒ 不校验（向后兼容）。**仅告警不阻断**（同 §2.3 未知配置段口径）。
        """
        if self._known_modules is None:
            return []
        known = ", ".join(sorted(self._known_modules))
        return [
            f"未知功能开关: features.{name}（不在已知模块名 {known} 之内；"
            f"若为拼写错误请订正 —— 模块名拼错将静默不生效）"
            for name in sorted(set(config.features) - self._known_modules)
        ]

    def _resolvable(self, ref: str) -> bool:
        """密钥引用能否经 env/keychain 解析（不返回明文）。"""
        try:
            self.resolve_secret(ref)
        except ConfigurationError:
            return False
        return True

    # ---- 密钥与开关 ----

    def is_resolvable(self, ref: str) -> bool:
        """密钥引用能否经 env/keychain 解析（**只回布尔，不返回、不落明文**）。

        只读消费面（诊断 / 概览）走此公开口，而非 ``resolve_secret``（后者返回明文）——
        与 ``_resolvable`` 同一实现，单一判据。
        """
        return self._resolvable(ref)

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

    def loop_limits(self) -> tuple[int, int]:
        """循环预算上限查询 → ``(max_rounds, token_budget)``。

        对齐 loop「错误与预算控制」：`max_rounds` 缺省 ``10``；`token_budget` 由模型上下文窗口
        **派生** —— 窗口取 ``llm.context_window``（显式配置，``> 0``）；未配置时按 ``llm.model``
        从内置已知模型窗口表**推导**（change 0184 / ADR-0175，见 `model_windows.known_window`）；
        两者皆无 ⇒ 回落内置缺省 ``65536``（与变更前逐位一致）。窗口既得后取
        ``window - output_reserve``（``output_reserve`` 缺省 ``8192``）。
        取值已过校验（整数、显式窗口大于预留），故此处只做 env/CLI 字符串归一，不设二次兜底。
        """
        if self._config is None:
            return _DEFAULT_MAX_ROUNDS, _DEFAULT_TOKEN_BUDGET
        raw = cast("dict[str, Any]", self._config.extra.get("loop") or {})
        rounds = _parse_int(raw.get("max_rounds", _DEFAULT_MAX_ROUNDS))
        reserve = _parse_int(raw.get("output_reserve", _DEFAULT_OUTPUT_RESERVE))
        max_rounds = _DEFAULT_MAX_ROUNDS if rounds is None else rounds
        window = self._config.llm.context_window
        if window <= 0:  # 未显式配置 ⇒ 按模型推导（表未命中返回 0，即「不知道」）
            window = known_window(self._config.llm.model)
        if window <= 0:  # 显式与表皆无 ⇒ 不做窗口派生，回落常量预算（逐字兼容）
            return max_rounds, _DEFAULT_TOKEN_BUDGET
        return max_rounds, window - (_DEFAULT_OUTPUT_RESERVE if reserve is None else reserve)

    def history_turns(self) -> int:
        """会话历史回灌轮数（缺省 ``20``，``0`` = 关闭回灌；change `0115`）。

        **独立访问器**：与 ``loop_limits()`` 无语义关系（后者是预算派生），且既有
        ``(max_rounds, token_budget)`` 二元组被多处解包断言钉死，不合并以免概念污染。
        """
        if self._config is None:
            return _DEFAULT_HISTORY_TURNS
        raw = cast("dict[str, Any]", self._config.extra.get("loop") or {})
        turns = _parse_int(raw.get("history_turns", _DEFAULT_HISTORY_TURNS))
        return _DEFAULT_HISTORY_TURNS if turns is None else turns

    def output_reserve(self) -> int:
        """输出预留（缺省 ``8192``；change `0183` / ADR-0174）。

        与 ``loop_limits()`` 的 token 预算派生**同源**（预算 = 窗口 − 预留）：组合根把它注入
        ``LLMPlanner`` 作为请求侧 ``max_tokens`` ⇒ 预留从**记账假设**变为**端点上界**。

        **独立访问器**：`(max_rounds, token_budget)` 二元组的解包断言已钉死，不合并。
        """
        if self._config is None:
            return _DEFAULT_OUTPUT_RESERVE
        raw = cast("dict[str, Any]", self._config.extra.get("loop") or {})
        reserve = _parse_int(raw.get("output_reserve", _DEFAULT_OUTPUT_RESERVE))
        return _DEFAULT_OUTPUT_RESERVE if reserve is None else reserve

    def compact_steps(self) -> int:
        """上下文压实的**本轮工具步数**阈值（缺省 ``6``；change 0182 / ADR-0173）。

        **独立访问器**（同 `history_turns()` 先例）：与预算/上限无语义关系，不并入
        ``loop_limits()`` 二元组（其 arity 被多处解包断言钉死）。取值已过校验（≥1 的整数），
        故此处只做 env/CLI 字符串归一，不设二次兜底。
        """
        if self._config is None:
            return _DEFAULT_COMPACT_STEPS
        raw = cast("dict[str, Any]", self._config.extra.get("loop") or {})
        steps = _parse_int(raw.get("compact_steps", _DEFAULT_COMPACT_STEPS))
        return _DEFAULT_COMPACT_STEPS if steps is None else steps

    def block_plan(self) -> bool:
        """上下文区块配比开关（缺省 ``False`` = 不接管；change 0201 / ADR-0191）。

        **独立访问器**（同 `history_turns()` 先例）：与预算/上限无语义关系，且既有访问器的
        返回 arity 被解包断言钉死，不合并。取值归一与 feature flag 同集；``loop`` 为**结构化段**
        （非法取值已在校验期阻断启动，见 `_loop_errors`），故此处只做字符串归一。

        关闭 ⇒ planner 沿用其**字面**注入预算 ⇒ 提示词逐字不变。
        """
        if self._config is None:
            return False
        raw = cast("dict[str, Any]", self._config.extra.get("loop") or {})
        value = raw.get("block_plan", False)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _FEATURE_TRUE

    def importance_gate(self) -> bool:
        """写入侧重要度闸门开关（缺省 ``False`` = 不评分；change 0181 / ADR-0172）。

        **独立访问器**（同 `history_turns()` 先例）：与预算/上限无语义关系。
        取值归一与 feature flag 同集（原生布尔 / `true`·`false`·`yes`·`no`·`on`·`off`·`1`·`0`，
        大小写不敏感）；`memory` 为非结构化段（不阻断启动）⇒ 集合外取值归一为**关闭**
        （方向恒为「不评分」，不会把笔误静默当作开启）。
        """
        if self._config is None:
            return False
        raw = cast("dict[str, Any]", self._config.extra.get("memory") or {})
        value = raw.get("importance_gate", False)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in _FEATURE_TRUE

    def orchestration_difficulty_policy(self) -> str:
        """同波次调度策略（缺省 ``off`` = 不启用难易度策略；见规格「难易度感知的调度策略」）。

        **独立访问器**（同 `history_turns()` 先例）：与预算/上限无语义关系，且既有访问器
        的返回 arity 被解包断言钉死，不合并。
        """
        if self._config is None:
            return _DEFAULT_ORCHESTRATION_POLICY
        raw = cast("dict[str, Any]", self._config.extra.get("orchestration") or {})
        policy = str(raw.get("difficulty_policy", _DEFAULT_ORCHESTRATION_POLICY))
        return policy if policy in _ORCHESTRATION_POLICIES else _DEFAULT_ORCHESTRATION_POLICY

    def orchestration_max_concurrency(self) -> int:
        """波次并发上限（缺省 ``4``；取值已过校验，此处只做 env/CLI 字符串归一）。"""
        if self._config is None:
            return _DEFAULT_ORCHESTRATION_MAX_CONCURRENCY
        raw = cast("dict[str, Any]", self._config.extra.get("orchestration") or {})
        limit = _parse_int(raw.get("max_concurrency", _DEFAULT_ORCHESTRATION_MAX_CONCURRENCY))
        return _DEFAULT_ORCHESTRATION_MAX_CONCURRENCY if limit is None else limit

    def sandbox_host_allowlist(self) -> list[str]:
        """出站网络白名单（缺省空 = fail-closed 全拒，安全默认）。

        取值形态为**逗号分隔字符串**（`permission.sandbox.host_allowlist`）：本仓 yaml 子集
        解析器不含列表，故三面（CLI / env / yaml）统一为标量，归一到裸主机名列表。
        条目已过校验（无 scheme / 端口 / 路径），此处只做拆分与去重。
        """
        if self._config is None:
            return []
        perm = cast("dict[str, Any]", self._config.extra.get("permission") or {})
        sandbox = cast("dict[str, Any]", perm.get("sandbox") or {})
        return _split_hosts(str(sandbox.get("host_allowlist", "")))

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

    def _restore_yaml(self, previous: bytes | None) -> None:
        """撤销写回：恢复写盘前的 yaml 原文（``None`` ⇒ 原不存在则删除，对称兜底）。"""
        if previous is None:
            self._yaml_path.unlink(missing_ok=True)
        else:
            self._yaml_path.write_bytes(previous)

    def write_patch(self, patch: dict[str, Any]) -> None:
        """把 patch 写回 config.yaml（只合并用户 patch，不落 env/cli 覆盖与明文密钥）。

        写回基于 yaml 文件原文（``_read_yaml``，未叠加 env/cli），``${VAR}`` 引用
        不解析、原样保留。明文密钥在 ``apply_change`` 已被 ``validate_schema`` 拒绝，
        故不会进入写回。

        原子提交（tmp + ``os.replace``）：直接 ``write_text`` 是**先截断再整写**，中途失败留半写
        文件 ⇒ 调用方「重读回滚」这条路自己就断了（change `0099`）。

        写回**是可逆效应**（change `0130` / ADR-0123 / 账本 E68）：配置变更实际作用于**两处状态**
        （内存 ``AppConfig`` + yaml 文件），而 ``apply_change`` 只记了内存那一处 ⇒ 账不覆盖磁盘时
        按 trace 回滚会留下「内存已退、磁盘未退」的不一致，下次 ``load()`` 把已回滚的变更复活。
        故在 ``os.replace`` **之前**记一条同 trace（``"config"``）的效应，undo 恢复**写盘前的原文
        字节**（重 dump 会改写格式、并可能把 env/cli 覆盖写进 yaml）。记账先于替换：``os.replace``
        原子，若它抛出则 yaml 仍是旧值，undo 写回旧值即幂等。
        """
        raw = self._read_yaml()
        _merge_raw(raw, patch)
        previous = self._yaml_path.read_bytes() if self._yaml_path.exists() else None
        tmp = self._yaml_path.with_name(self._yaml_path.name + ".tmp")
        tmp.write_text(_dump_yaml(raw), encoding="utf-8")
        self._effects.record(
            Effect(
                op="config_write_patch",
                target=str(self._yaml_path),
                undo=lambda: self._restore_yaml(previous),
                reversible=True,
                coeffect=[],
                trace_id="config",
                ts=time.time(),
            )
        )
        os.replace(tmp, self._yaml_path)

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
                raw.setdefault("features", {})[name] = value  # 原文，交由 _normalize_features 归一
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
            context_window=_llm_context_window(llm_raw),
            show_thinking=_llm_show_thinking(llm_raw),
        )
        features_raw = cast(dict[str, Any], merged.get("features") or {})
        features = _normalize_features(features_raw)
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
_KNOWN_EXTRA_SECTIONS = frozenset({"permission", "loop"})

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


def _parse_int(value: Any) -> int | None:
    """整数解析：``bool`` / 非数值 / 小数 → None（对齐 ``_as_number`` 口径）。"""
    number = _as_number(value)
    if number is None or number != int(number):
        return None
    return int(number)


def _llm_context_window(raw: dict[str, Any]) -> int:
    """llm 段 `context_window` 解析（结构化段 ⇒ **构建前阻断**，对齐 features 口径）。

    取值范围为 ``0``（未配置）或 ≥1 的整数；``bool`` / 小数 / 非数值 / 负数一律当场拒绝 ——
    原文一旦化为 int 便不可追溯，留到 ``validate_schema`` 已看不见原值。缺口径与下游耦合：
    ``token_budget <= 0`` 在 loop 侧语义是「**关闭** token 维度」，放行非正预算等于把配置错误
    静默变成「预算维度失效」。
    """
    value = raw.get("context_window", 0)
    window = _parse_int(value)
    if window is None or window < 0:
        raise ConfigurationError(  # noqa: TRY003
            f"非法上下文窗口: llm.context_window={value!r}（须为 0 或 ≥1 的整数）"
        )
    return window


def _llm_show_thinking(raw: dict[str, Any]) -> bool:
    """llm 段 `show_thinking` 解析（结构化段 ⇒ **构建前阻断**，取值口径与 feature flag 同集）。

    缺省 ``False``；接受原生布尔与 ``true/false``·``yes/no``·``on/off``·``1/0``（大小写不敏感、
    忽略首尾空白）。其余取值当场拒绝 —— `bool("<非空字符串>")` 为真，放行等于把 `maybe` 这类
    笔误静默当作**开启**，与「未开启时事件面与三端呈现逐字一致」的可证伪边界相冲突。
    """
    value = raw.get("show_thinking", False)
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in _FEATURE_TRUE:
        return True
    if text in _FEATURE_FALSE:
        return False
    raise ConfigurationError(  # noqa: TRY003
        f"非法思考回显开关: llm.show_thinking={value!r}"
        "（须为布尔或 true/false、yes/no、on/off、1/0）"
    )


def _loop_errors(raw: dict[str, Any]) -> list[str]:
    """循环预算取值校验（对齐 loop「错误与预算控制」）。

    轮数上限与压实步数阈值须为 **≥1 的整数**、输出预留与回灌轮数须为 **≥0 的整数**；``bool``
    视作非法（``true`` 不是次数）。非法取值**阻断启动**：静默兜底会把配置错误变成运行时的
    诡异行为。压实步数阈值**不做**「≤ max_rounds」跨键校验 —— 阈值达上限是**合法退化配置**
    （语义仍是「至少压实一次」，只不再提前；change 0182 / ADR-0173）。
    """
    errors: list[str] = []
    rounds = _parse_int(raw.get("max_rounds", _DEFAULT_MAX_ROUNDS))
    if rounds is None or rounds < 1:
        errors.append(
            f"非法循环次数上限: loop.max_rounds={raw.get('max_rounds')}（须为 ≥1 的整数）"
        )
    reserve = _parse_int(raw.get("output_reserve", _DEFAULT_OUTPUT_RESERVE))
    if reserve is None or reserve < 0:
        errors.append(
            f"非法输出预留: loop.output_reserve={raw.get('output_reserve')}（须为 ≥0 的整数）"
        )
    turns = _parse_int(raw.get("history_turns", _DEFAULT_HISTORY_TURNS))
    if turns is None or turns < 0:
        errors.append(
            f"非法回灌轮数: loop.history_turns={raw.get('history_turns')}（须为 ≥0 的整数）"
        )
    steps = _parse_int(raw.get("compact_steps", _DEFAULT_COMPACT_STEPS))
    if steps is None or steps < 1:
        errors.append(
            f"非法压实步数阈值: loop.compact_steps={raw.get('compact_steps')}（须为 ≥1 的整数）"
        )
    value = raw.get("block_plan", False)
    if not isinstance(value, bool) and str(value).strip().lower() not in (
        _FEATURE_TRUE | _FEATURE_FALSE
    ):
        errors.append(f"非法区块配比开关: loop.block_plan={value}（须为 true/false 之一）")
    return errors


def _orchestration_errors(raw: dict[str, Any]) -> list[str]:
    """编排调度取值校验（对齐 orchestration「难易度感知的调度策略」，change 0123）。

    并发上限须为 **≥1 的整数**（``bool`` 视作非法 —— ``true`` 不是并发度）、策略须为
    ``off`` / ``difficulty`` 之一。非法取值**阻断启动**：这里是**人工配置**，与「模型自报的
    难易度弱信号归一为 medium」口径**有意不同**（来源不同 ⇒ 处置不同）。
    """
    errors: list[str] = []
    limit = _parse_int(raw.get("max_concurrency", _DEFAULT_ORCHESTRATION_MAX_CONCURRENCY))
    if limit is None or limit < 1:
        errors.append(
            f"非法波次并发上限: orchestration.max_concurrency={raw.get('max_concurrency')}"
            "（须为 ≥1 的整数）"
        )
    policy = str(raw.get("difficulty_policy", _DEFAULT_ORCHESTRATION_POLICY))
    if policy not in _ORCHESTRATION_POLICIES:
        errors.append(
            f"非法编排调度策略: orchestration.difficulty_policy={policy}"
            f"（可选：{'/'.join(_ORCHESTRATION_POLICIES)}）"
        )
    return errors


def _window_reserve_errors(context_window: int, raw: dict[str, Any]) -> list[str]:
    """交叉校验：窗口已配置却**不大于**输出预留 ⇒ 派生预算非正。

    ``token_budget <= 0`` 在 ``DefaultLoop`` 侧的语义是「关闭 token 维度」⇒ 静默放行会把
    「窗口配小了」变成「预算维度失效」。故与熔断阈值同口径：**校验期拒绝，不静默兜底**。
    预留本身非法时由 ``_loop_errors`` 报出，此处不重复。
    """
    if context_window <= 0:
        return []
    reserve = _parse_int(raw.get("output_reserve", _DEFAULT_OUTPUT_RESERVE))
    if reserve is None or context_window > reserve:
        return []
    return [
        f"上下文窗口不敷输出预留: llm.context_window={context_window} ≤ "
        f"loop.output_reserve={reserve}（派生 token 预算须为正）"
    ]


def _split_hosts(raw: str) -> list[str]:
    """逗号分隔主机名 → 去空白、去空项、去重（保序）。兼容全角逗号。"""
    hosts: list[str] = []
    for part in raw.replace("，", ",").split(","):
        host = part.strip()
        if host and host not in hosts:
            hosts.append(host)
    return hosts


def _sandbox_errors(perm: dict[str, Any]) -> list[str]:
    """出站白名单取值校验（对齐 permission「沙箱执行颗粒度」）。

    条目须为**裸主机名**：``check_outbound`` 的实参是 ``urlparse(url).hostname``（不含端口 /
    路径），带 scheme / 端口 / 路径 / 空白的条目**永不匹配** —— 静默的后果是「配了却连不上」，
    故与熔断阈值同口径：**校验期拒绝，不静默兜底**。空配置（缺省）合法 = fail-closed 全拒。
    """
    sandbox = cast("dict[str, Any]", perm.get("sandbox") or {})
    raw = sandbox.get("host_allowlist", "")
    if not isinstance(raw, str):
        return [
            f"非法出站白名单取值: permission.sandbox.host_allowlist={raw!r}（须为逗号分隔的主机名）"
        ]
    return [
        f"非法出站白名单条目: permission.sandbox.host_allowlist={host}"
        "（须为裸主机名，不含 scheme / 端口 / 路径）"
        for host in _split_hosts(raw)
        if "/" in host or ":" in host or any(ch.isspace() for ch in host)
    ]


def _normalize_features(raw: Any) -> dict[str, bool]:
    """feature flag 段取值归一：三面（yaml / env / CLI）统一取值集合 → 布尔。

    **为什么在构建前归一**（而非 `validate_schema`）：`features` 是**结构化段**，
    取值在 `_build_config` 即被化为布尔，原文不可追溯 —— 与 `load()` 顶部
    `validate_map_to` 同属「构建前阻断」通道（校验期拒绝，**不静默兜底**）。

    接受原生布尔与常见别名（`true/false`、`yes/no`、`on/off`、`1/0`，大小写不敏感）；
    其余取值（如 `maybe`、空串、映射）在**校验期拒绝并阻断启动**，错误信息含键名与合法取值。
    """
    if not isinstance(raw, dict):
        raise ConfigurationError(  # noqa: TRY003
            f"非法功能开关取值: features={raw!r}（features 段须为 `模块名: 布尔` 键值对）"
        )
    normalized: dict[str, bool] = {}
    for key, value in cast(dict[str, Any], raw).items():
        if isinstance(value, bool):
            normalized[str(key)] = value
            continue
        if isinstance(value, int):  # yaml 标量 `1` / `0`（``_parse_scalar`` 归一为 int）
            text = str(value)
        elif isinstance(value, str):
            text = value.strip().lower()
        else:
            text = ""
        if text in _FEATURE_TRUE or text in _FEATURE_FALSE:
            normalized[str(key)] = text in _FEATURE_TRUE
            continue
        raise ConfigurationError(  # noqa: TRY003
            f"非法功能开关取值: features.{key}={value!r}"
            "（可选 true/false·yes/no·on/off·1/0，大小写不敏感）"
        )
    return normalized


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
        "reasoning_effort": config.llm.reasoning_effort,
        "embedding_model": config.llm.embedding_model,
        "context_window": config.llm.context_window,
        "show_thinking": config.llm.show_thinking,
    }
    llm_raw.update(cast(dict[str, Any], patch.get("llm") or {}))
    features = dict(config.features)
    features_patch = cast(dict[str, Any], patch.get("features") or {})
    features.update(_normalize_features(features_patch))
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
    extra = dict(config.extra)
    # 寄居 extra 的已知段（`loop`）须**浅合并**：整份拷贝会把 patch 静默丢弃 ⇒ 报成功却不生效。
    loop_patch = cast(dict[str, Any], patch.get("loop") or {})
    if loop_patch:
        extra["loop"] = {**cast(dict[str, Any], extra.get("loop") or {}), **loop_patch}
    return AppConfig(
        llm=LLMConfig(
            provider=str(llm_raw["provider"]),
            model=str(llm_raw["model"]),
            endpoint=str(llm_raw["endpoint"]),
            api_key_ref=str(llm_raw["api_key"]),
            reasoning_effort=_opt_str(llm_raw.get("reasoning_effort")),
            embedding_model=str(llm_raw.get("embedding_model", "")),
            context_window=_llm_context_window(llm_raw),
            show_thinking=_llm_show_thinking(llm_raw),
        ),
        features=features,
        im=im,
        pet=config.pet,
        judgment=config.judgment,
        extra=extra,
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


def _flatten_by_specs(raw: dict[str, Any], specs: list[ConfigSpec]) -> dict[str, Any]:
    """按 ``ConfigSpec.map_to`` 从嵌套 yaml 取出 ``spec.key`` → 取值 的扁平面。

    ``resolve`` 的 ``yaml`` 层以 **ConfigSpec.key** 为键，而 yaml 文件按 ``map_to`` 点分
    路径嵌套（``im.corp-id`` 等键两者并不相同），故须经单一真源逐键定位路径回填，
    不能简单按点分拼键。
    """
    flat: dict[str, Any] = {}
    for spec in specs:
        parts = spec.map_to.split(".")
        node: dict[str, Any] = raw
        for part in parts[:-1]:
            node = cast("dict[str, Any]", node.get(part) or {})
        if parts[-1] in node:  # 叶子存在即回填（含显式 false / 空串，故不能用真值判断）
            flat[spec.key] = node[parts[-1]]
    return flat


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
