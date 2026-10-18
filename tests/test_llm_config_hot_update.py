"""LLM 配置热生效与落盘持久化（change 0099）。

规格「LLM API 可配置」要求 UI 保存 LLM 配置后**写入后端配置源并立即生效**、密钥只存 `${VAR}` 引用、
持久化失败时**回滚不留半写状态**。本文件证明：`apply_llm_config` 真的落盘（新进程可重读）、真的把
派生后的上限推给**运行中**的执行循环、非法取值**拒绝且原值不被破坏**、写盘失败时**旧文件原样**
（原子提交 —— 非原子的 `write_text` 会先截断，回滚路径自身失效）。

另有一条回归守护：`set_llm_config`（启动期 hydrate）**不得**落盘 —— 否则每次 CLI 启动都重写 yaml。
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.configuration.models import LLMConfig
from core.loop import DefaultLoop
from core.ui import UIAPILayer, UiError, UiErrorCode

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
    "  reasoning_effort: low\n"
)


def _write_config(tmp_path: Path) -> Path:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION, encoding="utf-8")
    return cfg


def _manager(tmp_path: Path) -> ConfigManager:
    mgr = ConfigManager(
        yaml_path=_write_config(tmp_path),
        environ={"OPENAI_API_KEY": "sk-test"},
    )
    mgr.load()
    return mgr


def _api(
    tmp_path: Path, *, with_config: bool = True
) -> tuple[UIAPILayer, DefaultLoop, ConfigManager | None]:
    loop = DefaultLoop()
    mgr = _manager(tmp_path) if with_config else None
    api = UIAPILayer(loop=loop, config=mgr)
    return api, loop, mgr


def _new_llm(window: int) -> LLMConfig:
    return LLMConfig(
        provider="litellm",
        model="new-model",
        endpoint="https://example.com/v1",
        api_key_ref="${OPENAI_API_KEY}",
        reasoning_effort="high",
        embedding_model="",
        context_window=window,
    )


def test_apply_persists_and_survives_reload(tmp_path: Path) -> None:
    """保存 ⇒ 落盘；新进程重读同 yaml ⇒ 值原样生效（非仅内存态）。"""
    api, _, _ = _api(tmp_path)
    api.apply_llm_config(_new_llm(131072), output_reserve=4096, max_rounds=3)

    reloaded = ConfigManager(
        tmp_path / "config.yaml",
        environ={"OPENAI_API_KEY": "sk-test"},
    )
    reloaded_cfg = reloaded.load()
    assert reloaded_cfg.llm.model == "new-model"
    assert reloaded_cfg.llm.context_window == 131072  # noqa: PLR2004 — 即写入值
    assert reloaded.loop_limits() == (3, 131072 - 4096)


def test_apply_hot_updates_running_loop(tmp_path: Path) -> None:
    """运行中的 loop 立即取用新上限（无需重建循环）。"""
    api, loop, _ = _api(tmp_path)
    assert (loop._max_rounds, loop._token_budget) == (20, 65536)  # noqa: SLF001 — 接线断言

    api.apply_llm_config(_new_llm(131072), output_reserve=4096, max_rounds=3)

    assert (loop._max_rounds, loop._token_budget) == (3, 131072 - 4096)  # noqa: SLF001 — 接线断言


def test_api_key_reference_is_preserved_not_plaintext(tmp_path: Path) -> None:
    """密钥以 `${VAR}` 引用原样落盘，绝不物化为明文。"""
    api, _, _ = _api(tmp_path)
    api.apply_llm_config(_new_llm(65536))

    text = (tmp_path / "config.yaml").read_text(encoding="utf-8")
    assert "${OPENAI_API_KEY}" in text
    assert "sk-test" not in text


def test_invalid_value_rejected_and_original_intact(tmp_path: Path) -> None:
    """窗口不敷预留 ⇒ 拒绝，且**内存与 yaml 均不变**（不静默兜底）。"""
    api, loop, mgr = _api(tmp_path)
    before = (tmp_path / "config.yaml").read_text(encoding="utf-8")

    with pytest.raises(UiError) as exc:
        api.apply_llm_config(_new_llm(4096), output_reserve=8192, max_rounds=3)

    assert exc.value.code is UiErrorCode.UI_LLM_CONFIG_INVALID
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == before
    assert mgr is not None
    assert mgr.loop_limits() == (20, 65536)
    assert (loop._max_rounds, loop._token_budget) == (20, 65536)  # noqa: SLF001 — 未动


def test_plaintext_api_key_rejected(tmp_path: Path) -> None:
    """明文 key 直接拒绝（既有口径不因新入口松动）。"""
    api, _, _ = _api(tmp_path)
    plain = LLMConfig(provider="p", model="m", endpoint="https://x", api_key_ref="sk-live-123")
    with pytest.raises(UiError) as exc:
        api.apply_llm_config(plain)
    assert exc.value.code is UiErrorCode.UI_LLM_KEY_UNSET


def test_write_failure_leaves_file_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """写盘中途失败 ⇒ 旧 yaml **逐字不变**；`write_text` 先截断即打掉回滚路径。"""
    api, _, mgr = _api(tmp_path)
    before = (tmp_path / "config.yaml").read_text(encoding="utf-8")

    real_write_text = Path.write_text

    def _partial_then_fail(self: Path, data: str, *args: Any, **kwargs: Any) -> int:
        real_write_text(self, str(data)[:5], *args, **kwargs)  # 半写
        raise OSError("disk full")  # noqa: TRY003 — 模拟磁盘写满

    monkeypatch.setattr(Path, "write_text", _partial_then_fail)

    with pytest.raises(UiError) as exc:
        api.apply_llm_config(_new_llm(131072), output_reserve=4096, max_rounds=3)

    assert exc.value.code is UiErrorCode.UI_LLM_CONFIG_INVALID
    monkeypatch.undo()
    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == before
    assert mgr is not None
    assert mgr.loop_limits() == (20, 65536)  # 内存亦回滚


def test_set_llm_config_does_not_touch_disk(tmp_path: Path) -> None:
    """启动期 hydrate（`set_llm_config`）**不落盘** —— 否则每次 CLI 启动都重写 config.yaml。"""
    api, _, _ = _api(tmp_path)
    before = (tmp_path / "config.yaml").read_text(encoding="utf-8")

    api.set_llm_config(_new_llm(131072))

    assert (tmp_path / "config.yaml").read_text(encoding="utf-8") == before


def test_without_config_manager_keeps_memory_only(tmp_path: Path) -> None:
    """无配置源（裸 `UIAPILayer`）⇒ 纯内存 + 尽力热生效，不假装持久化。"""
    api, loop, mgr = _api(tmp_path, with_config=False)
    assert mgr is None

    api.apply_llm_config(_new_llm(131072), output_reserve=4096, max_rounds=3)

    assert api.get_llm_config().context_window == 131072  # noqa: PLR2004 — 即传入值
    assert (loop._max_rounds, loop._token_budget) == (3, 131072 - 4096)  # noqa: SLF001


def test_get_loop_limits_reports_effective_values(tmp_path: Path) -> None:
    """回显**生效值**（派生后的 token 预算），非旋钮原文。"""
    api, _, _ = _api(tmp_path)
    assert api.get_loop_limits() == (20, 65536)

    api.apply_llm_config(_new_llm(131072), output_reserve=4096, max_rounds=3)
    assert api.get_loop_limits() == (3, 131072 - 4096)


def test_get_loop_limits_without_config_is_none(tmp_path: Path) -> None:
    api, _, _ = _api(tmp_path, with_config=False)
    assert api.get_loop_limits() is None
