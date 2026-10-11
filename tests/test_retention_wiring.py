"""保留策略接线（change 0208 / ADR-0198 / 台账 E145）单元 + 配置 + 接线测试。

覆盖：`RetentionManager` 经 `_write_checkpoint` 接线后按 `max_count` / `time_window_s` 自动清理
（超限清理最旧 / 时间窗口清理过期 / pinned 豁免）；**缺省关**零清理（零回归锚）；配置三面
（spec 声明 + yaml + env）；非法值阻断启动。
"""

from __future__ import annotations

import time
from pathlib import Path

import pytest

from core.configuration import ConfigManager, ConfigurationError, config_specs
from core.orchestration import Plan
from core.runtime import build_runtime

_LLM_SECTION = (
    "llm:\n"
    "  provider: litellm\n"
    "  model: test-model\n"
    "  endpoint: https://example.com/v1\n"
    "  api_key: ${OPENAI_API_KEY}\n"
)


def _write_config(tmp_path: Path, extra: str = "") -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(_LLM_SECTION + extra, encoding="utf-8")
    return str(cfg)


def _manager(
    tmp_path: Path, extra: str = "", *, environ: dict[str, str] | None = None
) -> ConfigManager:
    manager = ConfigManager(
        yaml_path=_write_config(tmp_path, extra),
        environ={"OPENAI_API_KEY": "sk-test", **(environ or {})},
    )
    manager.load()
    return manager


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _plan() -> Plan:
    return Plan(subtasks=[], goal="g")


def _write(runtime: object, n: int, task_id: str = "t") -> list[str]:
    """经编排器持有的检查点回调写 N 个检查点（走真实接线路径），返回 id 序。

    每次写入间隔 1ms ⇒ ts 严格递增，清理判据（按 ts）确定。
    """
    scheduler = runtime.orchestrator  # type: ignore[attr-defined]
    ids: list[str] = []
    for _ in range(n):
        before = {cp.checkpoint_id for cp in runtime.checkpoints._store.list_checkpoints()}  # type: ignore[attr-defined]  # noqa: SLF001
        scheduler._checkpoint(task_id, [], _plan(), "sess")  # noqa: SLF001 — 接线断言
        after = {cp.checkpoint_id for cp in runtime.checkpoints._store.list_checkpoints()}  # type: ignore[attr-defined]  # noqa: SLF001
        ids.extend(sorted(after - before))
        time.sleep(0.001)
    return ids


def _ids(runtime: object) -> list[str]:
    return [cp.checkpoint_id for cp in runtime.checkpoints._store.list_checkpoints()]  # type: ignore[attr-defined]  # noqa: SLF001


# ---- 接线：数量上限 ----


def test_max_count_prunes_oldest(tmp_path: Path, state_dir: Path) -> None:
    limit, total = 2, 5
    runtime = build_runtime(
        _manager(tmp_path, f"durability:\n  retention:\n    max_count: {limit}\n")
    )

    written = _write(runtime, total)

    remaining = _ids(runtime)
    assert len(remaining) == limit, "数量上限 ⇒ 未 pinned 检查点回落至上限"
    assert set(remaining) == set(written[-limit:]), "保留最新两个"


# ---- 接线：时间窗口 ----


def test_time_window_prunes_expired(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(
        _manager(tmp_path, "durability:\n  retention:\n    time_window_s: 10\n")
    )

    _write(runtime, 2)
    # 回拨既有检查点 ts（-> 远超窗口前）⇒ 触发下一次写入时被清理
    for cp in runtime.checkpoints._store.list_checkpoints():  # noqa: SLF001
        cp.ts -= 100_000.0

    _write(runtime, 1)

    remaining = _ids(runtime)
    assert len(remaining) == 1, "过期的未 pinned 检查点被清理，窗口内（新写）保留"


# ---- 接线：pinned 豁免 ----


def test_pinned_checkpoint_survives_pruning(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(_manager(tmp_path, "durability:\n  retention:\n    max_count: 1\n"))

    [pinned_id] = _write(runtime, 1)
    runtime.checkpoints._store.set_pinned(pinned_id, True)  # noqa: SLF001 — 置 pinned 断言
    _write(runtime, 3)

    remaining = _ids(runtime)
    expected = 2  # pinned 一个 + 上限内未 pinned 一个
    assert pinned_id in remaining, "pinned 不受数量上限清理"
    assert len(remaining) == expected, "pinned + 最新未 pinned 各一"


# ---- 缺省关（零回归锚） ----


def test_default_off_never_prunes(tmp_path: Path, state_dir: Path) -> None:
    runtime = build_runtime(_manager(tmp_path))

    total = 5
    _write(runtime, total)

    assert len(_ids(runtime)) == total, "两键皆缺省 ⇒ 不清理任何检查点（逐字不变）"


# ---- 配置面（ConfigSpec 单一真源） ----


def test_spec_declares_retention_keys() -> None:
    specs = {spec.key: spec for spec in config_specs()}

    assert specs["durability.retention.max_count"].map_to == "durability.retention.max_count"
    assert specs["durability.retention.max_count"].env_var == (
        "CORE_DURABILITY_RETENTION_MAX_COUNT"
    )
    assert specs["durability.retention.time_window_s"].map_to == (
        "durability.retention.time_window_s"
    )
    assert specs["durability.retention.time_window_s"].env_var == (
        "CORE_DURABILITY_RETENTION_TIME_WINDOW_S"
    )


def test_config_default_is_off(tmp_path: Path) -> None:
    assert _manager(tmp_path).retention_limits() == (None, None)


def test_config_yaml_enables(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path, "durability:\n  retention:\n    max_count: 3\n    time_window_s: 30\n"
    )

    assert manager.retention_limits() == (3, 30.0)


def test_config_env_overrides(tmp_path: Path) -> None:
    manager = _manager(
        tmp_path,
        "durability:\n  retention:\n    max_count: 3\n",
        environ={"CORE_DURABILITY_RETENTION_MAX_COUNT": "7"},
    )

    assert manager.retention_limits() == (7, None)


@pytest.mark.parametrize(
    "extra",
    [
        "durability:\n  retention:\n    max_count: 0\n",  # 0 非法（须 ≥1）
        "durability:\n  retention:\n    max_count: -1\n",
        "durability:\n  retention:\n    max_count: true\n",  # bool 非法
        "durability:\n  retention:\n    time_window_s: -1\n",  # 须 ≥0
        "durability:\n  retention:\n    time_window_s: true\n",
    ],
)
def test_illegal_retention_value_blocks_startup(tmp_path: Path, extra: str) -> None:
    with pytest.raises(ConfigurationError):
        _manager(tmp_path, extra)
