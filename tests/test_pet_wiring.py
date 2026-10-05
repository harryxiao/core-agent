"""pet 运行时接线测试（change 0053 / 账本 E4）。

证明组合根真的把 pet 依赖接起来：生产激活的宠物持有 runtime 的 loop/记忆，
偏好落 L2；UIAPILayer 自然语言入口落到同一 PetManager。
"""

from __future__ import annotations

import pytest

from core.configuration import ConfigManager
from core.pet.core import PetSessionState
from core.runtime import build_runtime
from core.ui.api import UIAPILayer


def _write_config(tmp_path) -> str:
    cfg = tmp_path / "config.yaml"
    cfg.write_text(
        "llm:\n"
        "  provider: litellm\n"
        "  model: test-model\n"
        "  endpoint: https://example.com/v1\n"
        "  api_key: ${OPENAI_API_KEY}\n"
        "  reasoning_effort: low\n",
        encoding="utf-8",
    )
    return str(cfg)


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    return build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))


def test_build_runtime_assembles_pet_deps(runtime) -> None:
    """组合根产出非空 pet 面。"""
    assert runtime.pet_manager is not None
    assert runtime.pet_activator is not None


def test_production_pet_session_gets_live_deps(runtime) -> None:
    """生产激活的会话持有 runtime 的 loop / 记忆（非 echo 兜底）。"""
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    assert session.state is PetSessionState.ACTIVE
    assert session._loop is runtime.loop  # noqa: SLF001 — 注入生效断言
    assert session._memory is runtime.memory  # noqa: SLF001 — 注入生效断言
    assert runtime.pet_manager.get(session.session_id) is session


def test_production_pet_preference_lands_in_shared_l2(runtime) -> None:
    """偏好经生产激活的宠物落到 runtime 共享 L2。"""
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    session.observe("theme:dark")
    hits = [e for e in runtime.memory.read("theme") if e.source == "user"]
    assert hits, "偏好应以 source=user 落 runtime 共享 L2"


def test_production_pet_notification_reaches_sink(runtime, capsys) -> None:
    """账本 E16：组合根产出的会话持有的通知可调用体真的投递（缺省 sink = stderr）。"""
    session = runtime.pet_activator.activate_from_cli("gather", ["今日新闻"])
    notifier = session._notifier  # noqa: SLF001 — 组合根接线断言
    assert notifier is not None
    notifier("测试通知")
    assert "[pet] 测试通知" in capsys.readouterr().err


def test_ui_layer_activate_pet_registers_session(runtime) -> None:
    """`UIAPILayer.activate_pet`（WebUI 自然语言入口）落到同一 PetManager。"""
    api = UIAPILayer(pet_activator=runtime.pet_activator)
    session_id = api.activate_pet("启动宠物收集新闻")
    assert runtime.pet_manager.get(session_id) is not None
