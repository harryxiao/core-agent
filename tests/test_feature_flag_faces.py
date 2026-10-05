"""功能开关三面取值与 CLI 面接线（change 0072 / 账本 E20②、E23）。

规格「功能开关（feature flag）」明文列出三条输入通道：yaml `features.<模块>: false`、
env `CORE_FEATURE_<模块>`、CLI `--feature <模块>=false`。实测两处不符：

① **CLI 面零消费**（账本 E23）：`--feature NAME[=BOOL]` 只是解析进 `args.feature`，
   `_cli_overrides` 只收 `ConfigSpec` 声明键 ⇒ 该 flag **静默无效**（`args.feature` 无任何读者）；
② **取值被 `bool()` 静默强转**（账本 E20②）：yaml 子集解析器只认 `true/false/null/~`，
   故 `features.beast: off`（YAML 1.1 常见写法）落地为**字符串** `"off"` ⇒ `bool("off") is True`
   ⇒ **显式关闭被当成开启**；`"false"`（加引号）同理。

本文件证明：三面取值归一到**同一套取值集合**（含 `yes/no/on/off/1/0` 与原生布尔）、
非法取值**校验期阻断**（不静默兜底），且 CLI 面**真的**支配装配（组合根端到端）。
"""

from __future__ import annotations

from typing import Any

import pytest

from core.configuration import ConfigManager, ConfigurationError
from core.entry import _build_parser, _cli_overrides
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path, features: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + features, encoding="utf-8")
    return str(cfg)


def _yaml_features(**values: str) -> str:
    return "features:\n" + "".join(f"  {k}: {v}\n" for k, v in values.items())


def _cli(argv: list[str]) -> dict[str, Any]:
    """走**真实 argparse 面**取 CLI 覆盖（而非手搓 cli 字典）。"""
    return _cli_overrides(_build_parser().parse_args([*argv, "config", "show"]))


def _manager(
    tmp_path,
    *,
    features: str = "",
    argv: list[str] | None = None,
    environ: dict[str, str] | None = None,
    load: bool = True,
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, features),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
        cli=_cli(argv) if argv else None,
    )
    if load:
        manager.load()
    return manager


@pytest.fixture
def state_dir(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


# ---- ① CLI 面接线（此前静默无效） ----


def test_bare_flag_means_on() -> None:
    """`--feature pet`（metavar `NAME[=BOOL]`）⇒ 裸名为开。"""
    assert _cli(["--feature", "pet"]) == {"features.pet": "true"}


def test_flag_carries_explicit_value() -> None:
    assert _cli(["--feature", "beast=false"]) == {"features.beast": "false"}


def test_flag_precedence_cli_over_yaml(tmp_path) -> None:
    """CLI 覆盖 yaml（配置源分层：CLI > env > yaml）。"""
    manager = _manager(
        tmp_path, features=_yaml_features(beast="false"), argv=["--feature", "beast=true"]
    )
    assert manager.is_disabled("beast") is False


def test_malformed_flag_is_rejected() -> None:
    """语法非法（缺名 / 缺值）⇒ 明确报错，不静默吞掉。"""
    for bad in ("=false", "beast=", ""):
        with pytest.raises(ValueError, match="非法 --feature"):
            _cli(["--feature", bad])


def test_cli_flag_governs_assembly(tmp_path, state_dir) -> None:
    """端到端：`--feature beast=false` ⇒ 组合根**不装配** beast（此前该 flag 无任何效果）。"""
    manager = _manager(tmp_path, argv=["--feature", "beast=false"])
    runtime = build_runtime(manager)
    assert runtime.beast_manager is None
    assert runtime.beast_activator is None
    assert runtime.pet_manager is not None  # 未点名的模块不受影响


# ---- ② 取值归一（`bool()` 静默强转的修复） ----


@pytest.mark.parametrize("raw", ["false", "off", "no", "0", '"false"', '"OFF"'])
def test_falsy_spellings_disable(tmp_path, raw: str) -> None:
    """YAML 1.1 常见假值写法与加引号字符串一律归一为**关闭**。

    修复前 `off` / `"false"` 落地为字符串 ⇒ `bool()` 为真 ⇒ 显式关闭被当成开启。
    """
    manager = _manager(tmp_path, features=_yaml_features(beast=raw))
    assert manager.is_disabled("beast") is True


@pytest.mark.parametrize("raw", ["true", "on", "yes", "1", '"true"'])
def test_truthy_spellings_enable(tmp_path, raw: str) -> None:
    manager = _manager(tmp_path, features=_yaml_features(beast=raw))
    assert manager.is_disabled("beast") is False


def test_native_bool_unchanged(tmp_path) -> None:
    """原生布尔（既有写法）行为逐位不变。"""
    assert _manager(tmp_path, features=_yaml_features(beast="false")).is_disabled("beast") is True
    assert _manager(tmp_path, features=_yaml_features(beast="true")).is_disabled("beast") is False


def test_env_value_is_normalized(tmp_path) -> None:
    """env 面同样归一（`CORE_FEATURES_*` 为既有前缀）。"""
    manager = _manager(tmp_path, environ={"CORE_FEATURES_BEAST": "off"})
    assert manager.is_disabled("beast") is True


# ---- ③ 非法取值校验期阻断（不静默兜底） ----


@pytest.mark.parametrize(
    "kwargs",
    [
        {"features": _yaml_features(beast="maybe")},
        {"features": _yaml_features(beast="")},
        {"environ": {"CORE_FEATURES_BEAST": "banana"}},
        {"argv": ["--feature", "beast=maybe"]},
    ],
    ids=["yaml", "yaml-空值", "env", "cli"],
)
def test_invalid_value_blocks_startup(tmp_path, kwargs: dict[str, Any]) -> None:
    """非法取值 ⇒ 校验期拒绝并阻断启动，错误信息含键名与合法取值（**不**退化成缺省）。"""
    with pytest.raises(ConfigurationError, match="非法功能开关取值"):
        _manager(tmp_path, **kwargs)


def test_apply_change_validates_feature_value(tmp_path) -> None:
    """运行时变更（`config set features.<模块>=...`）同口径校验。"""
    manager = _manager(tmp_path)
    with pytest.raises(ConfigurationError, match="非法功能开关取值"):
        manager.apply_change({"features": {"beast": "maybe"}})
