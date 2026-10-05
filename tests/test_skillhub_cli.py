"""skillhub × CLI 接线用例（change 0092 / Phase 20 C5）。

覆盖：`skill search` 走市场（元数据 / 空结果 / 源不可达）、`skill install` 走签名校验下载
（落 draft 且**跨进程可见** / 签名失败拒绝 / 市场未接如实报错）、`skill remove` 作用于持久库。

技能库经 `_build_skill_library()` 落在 `$CORE_STATE_DIR/skills.json`（测试已隔离该目录）。
"""

from __future__ import annotations

import pytest

from core.entry import _build_skill_library, _state_path, main
from core.skillhub import MarketIndex, MarketSkill, SkillHubClient, TrustVerifier
from core.skills import Skill, SkillLibrary

_SKILL_ID = "skills.demo.greet"


def _market_client(
    library: SkillLibrary, *, tamper: bool = False, healthy: bool = True
) -> SkillHubClient:
    """内存市场客户端：官方源含一条已签名技能，`fetcher` 返回技能体。"""
    verifier = TrustVerifier()
    skill = Skill(skill_id=_SKILL_ID, description="greet", version="v1", instructions="say hi")
    index = MarketIndex(health_probe=(lambda _s: True) if healthy else (lambda _s: False))
    index.put(
        "official",
        MarketSkill(
            skill_id=_SKILL_ID,
            name="greet",
            description="greet",
            version="v1",
            signature="tampered" if tamper else verifier.sign(skill),
        ),
    )
    return SkillHubClient(
        library,
        index=index,
        verifier=verifier,
        fetcher=lambda sid, _src: skill if sid == _SKILL_ID else None,
    )


def _reopen_library() -> SkillLibrary:
    """重开技能库（模拟另一进程）：证明 install/remove 真的落盘。"""
    return SkillLibrary(path=_state_path("skills.json"))


def test_skill_search_reports_market_metadata(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("core.entry._build_skillhub_client", _market_client)
    assert main(["skill", "search", "greet"]) == 0
    out = capsys.readouterr().out
    assert f"{_SKILL_ID} (v1)" in out


def test_skill_search_empty_market_reports_not_found(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["skill", "search", "nothing-here"]) == 0
    assert "（未找到匹配技能: nothing-here）" in capsys.readouterr().out


def test_skill_search_unhealthy_source_reports_error(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.entry._build_skillhub_client", lambda library: _market_client(library, healthy=False)
    )
    assert main(["skill", "search", "greet"]) == 1
    assert "搜索失败" in capsys.readouterr().err


def test_skill_install_registers_draft_across_processes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("core.entry._build_skillhub_client", _market_client)
    assert main(["skill", "install", _SKILL_ID]) == 0
    assert "draft" in capsys.readouterr().out
    assert _reopen_library().lookup(_SKILL_ID).status == "draft"


def test_skill_install_signature_failure_rejected(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        "core.entry._build_skillhub_client", lambda library: _market_client(library, tamper=True)
    )
    assert main(["skill", "install", _SKILL_ID]) == 1
    assert "安装失败" in capsys.readouterr().err
    with pytest.raises(KeyError):
        _reopen_library().lookup(_SKILL_ID)  # 拒绝即不落盘


def test_skill_install_without_market_reports_error(capsys: pytest.CaptureFixture[str]) -> None:
    """缺省装配（无市场 fetcher）：如实报错、退出码非零，不静默成功。"""
    assert main(["skill", "install", _SKILL_ID]) == 1
    assert "安装失败" in capsys.readouterr().err


def test_skill_remove_uses_persisted_library(capsys: pytest.CaptureFixture[str]) -> None:
    library = _build_skill_library()
    library.register(
        Skill(skill_id=_SKILL_ID, description="greet", version="v1", instructions="say hi")
    )

    assert main(["skill", "remove", _SKILL_ID]) == 0
    assert "已卸载技能" in capsys.readouterr().out
    with pytest.raises(KeyError):
        _reopen_library().lookup(_SKILL_ID)
