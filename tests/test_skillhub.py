"""skillhub 单元测试（对齐 §22 契约 + M2 验收锚点）。

覆盖：多源路由健康回退 / 源不存在报错 / 签名校验拒绝下载 / 下载默认 draft /
发布审核流。
"""

from __future__ import annotations

import pytest

from core.skillhub import (
    MarketIndex,
    MarketSkill,
    MarketSource,
    SkillHubClient,
    SkillHubError,
    SkillHubErrorCode,
    SkillPublisher,
    TrustVerifier,
)
from core.skills import Skill, SkillLibrary

# ---- 源路由 / 健康 ----


def test_index_route_source_not_found() -> None:
    index = MarketIndex()
    with pytest.raises(SkillHubError) as exc_info:
        index.route("missing")
    assert exc_info.value.code is SkillHubErrorCode.SOURCE_NOT_FOUND


def test_index_source_unhealthy() -> None:
    index = MarketIndex(
        sources={"official": MarketSource("official"), "bad": MarketSource("bad")},
        health_probe=lambda s: s == "official",
    )
    with pytest.raises(SkillHubError) as exc_info:
        index.list(source="bad")
    assert exc_info.value.code is SkillHubErrorCode.SOURCE_UNHEALTHY


def test_index_health_probe() -> None:
    index = MarketIndex(health_probe=lambda s: s == "official")
    result = index.health("official")
    assert result.healthy is True
    assert result.source == "official"


# ---- 签名 ----


def test_trust_verify_and_sign() -> None:
    verifier = TrustVerifier()
    skill = Skill(skill_id="s.x", description="", version="v1", instructions="do")
    assert verifier.verify(skill, verifier.sign(skill)) is True
    assert verifier.verify(skill, "tampered") is False


def test_trust_whitelist() -> None:
    verifier = TrustVerifier(trusted={"known"})
    skill = Skill(skill_id="s.x", description="", version="v1", instructions="do")
    assert verifier.verify(skill, "known") is True


# ---- 下载 ----


def _client_setup():
    library = SkillLibrary()
    index = MarketIndex()
    verifier = TrustVerifier()
    skill = Skill(
        skill_id="skills.demo.greet", description="greet", version="v1", instructions="say hi"
    )
    index.put(
        "official",
        MarketSkill(
            skill_id="skills.demo.greet",
            name="greet",
            description="greet",
            version="v1",
            signature=verifier.sign(skill),
        ),
    )

    def fetcher(sid: str, src: str):
        return skill if sid == "skills.demo.greet" else None

    return library, index, verifier, fetcher, skill


def test_download_verifies_and_registers_draft() -> None:
    library, index, verifier, fetcher, skill = _client_setup()
    client = SkillHubClient(library, index=index, verifier=verifier, fetcher=fetcher)
    downloaded = client.download("skills.demo.greet")
    assert downloaded.status == "draft"
    assert library.lookup("skills.demo.greet") is downloaded


def test_download_tampered_signature_rejected() -> None:
    library, index, verifier, fetcher, skill = _client_setup()
    market = index.get("official", "skills.demo.greet")
    assert market is not None
    market.signature = "tampered"
    client = SkillHubClient(library, index=index, verifier=verifier, fetcher=fetcher)
    with pytest.raises(SkillHubError) as exc_info:
        client.download("skills.demo.greet")
    assert exc_info.value.code is SkillHubErrorCode.SIGNATURE_INVALID
    with pytest.raises(KeyError):
        library.lookup("skills.demo.greet")  # 未落盘


def test_search_scores_by_query() -> None:
    library, index, verifier, fetcher, skill = _client_setup()
    client = SkillHubClient(library, index=index, verifier=verifier, fetcher=fetcher)
    assert any(m.skill_id == "skills.demo.greet" for m in client.search("greet"))


# ---- 发布审核 ----


def test_publish_and_approve() -> None:
    index = MarketIndex()
    publisher = SkillPublisher(index=index)
    skill = Skill(
        skill_id="skills.demo.greet", description="greet", version="v1", instructions="hi"
    )
    assert publisher.publish(skill) == "skills.demo.greet"
    market = index.get("official", "skills.demo.greet")
    assert market is not None and market.status == "pending"
    publisher.review("skills.demo.greet", "approved")
    assert market.status == "published"
    assert market.version == "v2"


def test_review_rejected_raises() -> None:
    index = MarketIndex()
    publisher = SkillPublisher(index=index)
    publisher.publish(Skill(skill_id="s.x", description="", version="v1", instructions="x"))
    with pytest.raises(SkillHubError) as exc_info:
        publisher.review("s.x", "rejected")
    assert exc_info.value.code is SkillHubErrorCode.PUBLISH_REJECTED
    assert index.get("official", "s.x").status == "rejected"


def test_review_never_published_raises_not_active() -> None:
    publisher = SkillPublisher(index=MarketIndex())
    with pytest.raises(SkillHubError) as exc_info:
        publisher.review("nope", "approved")
    assert exc_info.value.code is SkillHubErrorCode.SKILL_NOT_ACTIVE
