"""skillhub 单元测试（对齐 §22 契约 + M2 验收锚点）。

覆盖：多源路由健康回退 / 源不存在报错 / 签名校验拒绝下载 / 下载默认 draft /
发布审核流 / 目录落盘与跨进程续接（change 0105）。
"""

from __future__ import annotations

from pathlib import Path

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


# ---- 目录落盘与跨进程续接（change 0105） ----


def _greet_skill() -> Skill:
    return Skill(
        skill_id="skills.demo.greet", description="greet", version="v1", instructions="say hi"
    )


def test_index_persists_across_instances(tmp_path: Path) -> None:
    """一次 put 的条目在**另一个实例**（模拟另一进程）中可见。"""
    path = tmp_path / "skillhub-index.json"
    MarketIndex(path=path).put(
        "official",
        MarketSkill(
            skill_id="skills.demo.greet",
            name="greet",
            description="greet",
            version="v1",
            signature="sig",
        ),
    )
    market = MarketIndex(path=path).get("official", "skills.demo.greet")
    assert market is not None
    assert market.signature == "sig"
    assert [m.skill_id for m in MarketIndex(path=path).list()] == ["skills.demo.greet"]


def test_index_corrupt_file_degrades_to_empty_official(tmp_path: Path) -> None:
    """损坏的目录文件降级为空目录（仅告警），官方源仍在。"""
    path = tmp_path / "skillhub-index.json"
    path.write_text("{ 不是合法 json", encoding="utf-8")
    with pytest.warns(UserWarning):
        index = MarketIndex(path=path)
    assert index.list() == []
    assert index.locate("skills.demo.greet") is None


def test_index_locate_across_sources() -> None:
    """locate 跨源按 skill_id 定位（审核不需要调用方知道源）。"""
    index = MarketIndex(
        sources={"official": MarketSource("official"), "third": MarketSource("third")}
    )
    index.put(
        "third",
        MarketSkill(
            skill_id="skills.demo.greet",
            name="greet",
            description="greet",
            version="v1",
            signature="sig",
        ),
    )
    located = index.locate("skills.demo.greet")
    assert located is not None and located[0] == "third"
    assert index.locate("skills.demo.other") is None


def test_publish_registers_artifacts_for_fetch(tmp_path: Path) -> None:
    """发布 = 元数据上架 + 制品入库（消费侧据此拉取并验签）。"""
    artifacts = SkillLibrary(path=tmp_path / "skillhub-artifacts.json")
    skill = _greet_skill()
    SkillPublisher(index=MarketIndex(path=tmp_path / "index.json"), artifacts=artifacts).publish(
        skill
    )
    stored = SkillLibrary(path=tmp_path / "skillhub-artifacts.json").lookup("skills.demo.greet")
    assert stored is not skill  # 制品是副本（审核改写本体不波及本地技能库）
    client = SkillHubClient(
        SkillLibrary(),
        index=MarketIndex(path=tmp_path / "index.json"),
        fetcher=lambda sid, _src: artifacts.lookup(sid),
    )
    assert client.download("skills.demo.greet").status == "draft"


def test_publish_missing_source_leaves_no_artifact(tmp_path: Path) -> None:
    """源不存在 ⇒ 拒绝上架，且制品不入库（先上架后入库的顺序保证）。"""
    artifacts = SkillLibrary(path=tmp_path / "skillhub-artifacts.json")
    publisher = SkillPublisher(index=MarketIndex(path=tmp_path / "index.json"), artifacts=artifacts)
    with pytest.raises(SkillHubError) as exc_info:
        publisher.publish(_greet_skill(), source="missing")
    assert exc_info.value.code is SkillHubErrorCode.SOURCE_NOT_FOUND
    with pytest.raises(KeyError):
        artifacts.lookup("skills.demo.greet")


def test_review_across_instances_bumps_market_version(tmp_path: Path) -> None:
    """审核跨实例续接：目录定位源 ⇒ published + v2（未注入制品库时制品不动）。"""
    index_path = tmp_path / "index.json"
    artifacts_path = tmp_path / "skillhub-artifacts.json"
    SkillPublisher(
        index=MarketIndex(path=index_path),
        artifacts=SkillLibrary(path=artifacts_path),
    ).publish(_greet_skill(), source="official")

    SkillPublisher(index=MarketIndex(path=index_path)).review("skills.demo.greet", "approved")

    market = MarketIndex(path=index_path).get("official", "skills.demo.greet")
    assert market is not None and market.status == "published"
    assert market.version == "v2"  # 显式不传 artifacts ⇒ 仅目录版本提升
    assert SkillLibrary(path=artifacts_path).lookup("skills.demo.greet").version == "v1"


def test_review_promotes_artifact_and_resigns(tmp_path: Path) -> None:
    """注入制品库时，审核通过把制品本体一并提升到发布版本并重新签名（验签仍成立）。"""
    index_path = tmp_path / "index.json"
    artifacts_path = tmp_path / "skillhub-artifacts.json"
    publisher = SkillPublisher(
        index=MarketIndex(path=index_path),
        artifacts=SkillLibrary(path=artifacts_path),
    )
    publisher.publish(_greet_skill())
    publisher.review("skills.demo.greet", "approved")

    market = MarketIndex(path=index_path).get("official", "skills.demo.greet")
    body = SkillLibrary(path=artifacts_path).lookup("skills.demo.greet")
    assert market is not None and body.version == market.version == "v2"
    assert TrustVerifier().verify(body, market.signature) is True


def test_review_rejected_persists_status(tmp_path: Path) -> None:
    """驳回状态落盘（另一实例可见），允许改后重传。"""
    index_path = tmp_path / "index.json"
    SkillPublisher(index=MarketIndex(path=index_path)).publish(_greet_skill())
    with pytest.raises(SkillHubError) as exc_info:
        SkillPublisher(index=MarketIndex(path=index_path)).review("skills.demo.greet", "rejected")
    assert exc_info.value.code is SkillHubErrorCode.PUBLISH_REJECTED
    market = MarketIndex(path=index_path).get("official", "skills.demo.greet")
    assert market is not None and market.status == "rejected"
