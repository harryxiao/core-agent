"""skillhub × CLI 接线用例（change 0092 / Phase 20 C5；供给侧 change 0105）。

覆盖：`skill search` 走市场（元数据 / 空结果 / 源不可达）、`skill install` 走签名校验下载
（落 draft 且**跨进程可见** / 签名失败拒绝 / 市场未接如实报错）、`skill remove` 作用于持久库；
供给侧 `skill publish` / `skill review` 与「发布 → 索引 → 消费」闭环（change 0105）。

技能库经 `_build_skill_library()` 落在 `$CORE_STATE_DIR/skills.json`，市场目录 / 制品库经
`_build_market_index()` / `_build_market_artifacts()` 落在同一状态目录（测试已隔离该目录）。
"""

from __future__ import annotations

import pytest

from core.entry import (
    _build_market_artifacts,
    _build_market_index,
    _build_skill_library,
    _state_path,
    main,
)
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
    """本地市场无该技能制品：如实报错、退出码非零，不静默成功。"""
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


# ---- 供给侧接线（change 0105） ----


def _register_local_skill(status: str = "active") -> Skill:
    """本地技能库注册一条技能（发布的上游制品）。"""
    skill = Skill(
        skill_id=_SKILL_ID,
        description="greet 问候",
        version="v1",
        instructions="say hi",
        status=status,
    )
    _build_skill_library().register(skill)
    return skill


def _reopen_market() -> MarketIndex:
    """重开市场目录（模拟另一进程）：证明 publish/review 真的落盘。"""
    return _build_market_index()


def test_supply_chain_publish_search_review_install(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """供给侧闭环：本地技能 → publish（落盘 pending）→ search 命中 → review approved →
    install 落 draft。每步都经**重开落盘对象**断言跨进程可见。"""
    _register_local_skill()

    assert main(["skill", "publish", _SKILL_ID]) == 0
    out = capsys.readouterr().out
    assert "pending" in out
    market = _reopen_market().get("official", _SKILL_ID)
    assert market is not None and market.status == "pending"

    assert main(["skill", "search", "greet"]) == 0
    assert f"{_SKILL_ID} (v1)" in capsys.readouterr().out

    assert main(["skill", "review", _SKILL_ID, "approved"]) == 0
    market = _reopen_market().get("official", _SKILL_ID)
    assert market is not None and (market.status, market.version) == ("published", "v2")

    assert main(["skill", "install", _SKILL_ID]) == 0
    assert "draft" in capsys.readouterr().out
    assert _reopen_library().lookup(_SKILL_ID).status == "draft"


def test_skill_publish_unregistered_skill_reports_error(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """未在本地注册的技能无从发布：退出码非零、目录不落盘。"""
    assert main(["skill", "publish", _SKILL_ID]) == 1
    assert "技能未注册" in capsys.readouterr().err
    assert _reopen_market().get("official", _SKILL_ID) is None


def test_skill_publish_missing_source_reports_error(capsys: pytest.CaptureFixture[str]) -> None:
    """源不存在 ⇒ 拒绝上架（不静默落到官方源）。"""
    _register_local_skill()
    assert main(["skill", "publish", _SKILL_ID, "--source", "third-party"]) == 1
    assert "发布失败" in capsys.readouterr().err
    assert _reopen_market().get("official", _SKILL_ID) is None


def test_skill_review_never_published_reports_error(capsys: pytest.CaptureFixture[str]) -> None:
    """审核一个从未发布的技能：退出码非零（跨进程也不误判）。"""
    assert main(["skill", "review", _SKILL_ID, "approved"]) == 1
    assert "审核失败" in capsys.readouterr().err


def test_skill_review_rejected_reports_error(capsys: pytest.CaptureFixture[str]) -> None:
    """驳回 ⇒ 退出码非零，状态落盘为 rejected。"""
    _register_local_skill()
    assert main(["skill", "publish", _SKILL_ID]) == 0
    capsys.readouterr()
    assert main(["skill", "review", _SKILL_ID, "rejected"]) == 1
    assert "审核失败" in capsys.readouterr().err
    market = _reopen_market().get("official", _SKILL_ID)
    assert market is not None and market.status == "rejected"


def test_skill_install_rejects_tampered_artifact(capsys: pytest.CaptureFixture[str]) -> None:
    """末端验签：制品事后被篡改 ⇒ 拒绝安装且不落盘（真实签名校验路径）。"""
    _register_local_skill()
    assert main(["skill", "publish", _SKILL_ID]) == 0
    capsys.readouterr()

    artifacts = _build_market_artifacts()
    body = artifacts.lookup(_SKILL_ID)
    body.instructions = "偷偷改掉说明"
    artifacts.register(body)

    assert main(["skill", "install", _SKILL_ID]) == 1
    assert "安装失败" in capsys.readouterr().err
    assert _reopen_library().lookup(_SKILL_ID).status == "active"  # 拒绝即不改写本地库
