"""结构化关键事实抽取（key_facts）单测：抽取落库 + 密钥引用式脱敏（fail-closed）。

对应规格：doc/openspec/specs/memory/spec.md「结构化实体抽取（关键事实）」。
change 0155 / ADR-0147 / 记忆三面路线图 G4（账本 E92）。
"""

from __future__ import annotations

import warnings

import pytest

from core.memory import (
    REDACTED,
    KeyFact,
    MemoryEntry,
    MemoryStore,
    extract_with,
    parse_key_facts,
    scrub_key_fact,
)
from core.memory.extract import _MAX_FACT_CHARS, MAX_KEY_FACTS_PER_COMPACT
from core.plugin_registry import EffectTracker

# 已知令牌前缀族 + 私钥块的样例（值本身是**测试哨兵**，非真实凭据）
_SECRETS = [
    "sk-abcdefgh12345678",
    "sk-ant-abcdefgh12345678",
    "ghp_" + "a" * 36,
    "AKIAIOSFODNN7EXAMPLE",
    "xoxb-1234567890-abcdefghijkl",
    "-----BEGIN RSA PRIVATE KEY-----",
    "password: hunter2xyz",
]
_LONG_RANDOM = "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"  # 38 字符长随机串


def _episodic(entry_id: str, session_id: str, content: str = "事件") -> MemoryEntry:
    return MemoryEntry(
        id=entry_id,
        layer="L2",
        content=content,
        tags=["loop"],
        source="loop",
        session_id=session_id,
        kind="episodic",
        trace_id="t",
    )


def _store(facts: list[KeyFact], *, session_id: str = "s1") -> MemoryStore:
    """构造注入了「定值抽取器」的 store（摘要器同注入，压实照常走完整流程）。"""
    store = MemoryStore(
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=lambda entries: list(facts),
    )
    store.write("L2", _episodic("e0", session_id))
    return store


def _facts(store: MemoryStore) -> list[MemoryEntry]:
    return [entry for entry in store.audit() if "key_fact" in entry.tags]


# ---- 脱敏原语（scrub_key_fact） ----


@pytest.mark.parametrize("secret", _SECRETS)
def test_scrub_redacts_secret_shaped_values(secret: str) -> None:
    """密钥形态（已知前缀族 / 私钥块 / 赋值式）⇒ 强制 `<redacted>`（引用在场即落库）。"""
    cleaned = scrub_key_fact(KeyFact(entity="凭据", value=secret, ref="coeffect:cred"))
    assert cleaned is not None
    assert cleaned.value == REDACTED, "密钥形态 ⇒ 强制脱敏"
    assert cleaned.ref == "coeffect:cred", "引用原样保留"


def test_scrub_redacts_long_random_string() -> None:
    """长随机串（未知密钥格式兜底）⇒ 强制脱敏。"""
    cleaned = scrub_key_fact(KeyFact(entity="令牌", value=_LONG_RANDOM, ref="coeffect:tok"))
    assert cleaned is not None and cleaned.value == REDACTED


def test_scrub_forces_redacted_when_ref_present() -> None:
    """有 `ref` ⇒ `value` **一律** `<redacted>`（即便原值看起来正常）。"""
    cleaned = scrub_key_fact(KeyFact(entity="部署环境", value="生产集群 A", ref="coeffect:env"))
    assert cleaned is not None
    assert cleaned.value == REDACTED, "引用式：有引用就不留明文取值"
    assert cleaned.ref == "coeffect:env"


def test_scrub_keeps_plain_value_without_ref() -> None:
    """无 `ref` 且取值不含密钥形态 ⇒ 原样保留（普通关键事实）。"""
    cleaned = scrub_key_fact(KeyFact(entity="部署环境", value="生产集群 A"))
    assert cleaned == KeyFact(entity="部署环境", value="生产集群 A", ref="")


@pytest.mark.parametrize("secret", [*_SECRETS, _LONG_RANDOM])
def test_scrub_drops_bare_secret_without_ref(secret: str) -> None:
    """fail-closed：密钥形态**且无可用引用** ⇒ 整条丢弃（记不住引用就不记）。"""
    assert scrub_key_fact(KeyFact(entity="凭据", value=secret)) is None


def test_scrub_drops_empty_entity() -> None:
    """无实体名 ⇒ 丢弃（关键事实必须有实体）。"""
    assert scrub_key_fact(KeyFact(entity="   ", value="x")) is None


def test_scrub_discards_secret_shaped_ref() -> None:
    """引用本身像密钥 ⇒ 弃用该引用；取值随之按「裸值」判据处理。"""
    cleaned = scrub_key_fact(KeyFact(entity="凭据", value="生产集群 A", ref="sk-abcdefgh12345678"))
    assert cleaned is not None and cleaned.ref == "", "像密钥的引用被弃用"
    assert cleaned.value == "生产集群 A"


def test_scrub_redacts_before_truncating() -> None:
    """先脱敏后截断：超长密钥不得因截断而残留明文片段。"""
    cleaned = scrub_key_fact(KeyFact(entity="凭据", value="sk-" + "a" * 400, ref="coeffect:cred"))
    assert cleaned is not None
    assert cleaned.value == REDACTED, "脱敏在截断之前 ⇒ 不残留明文前缀"


# ---- 落库形态与幂等 ----


def test_extracted_key_fact_lands_with_expected_shape() -> None:
    """落库形态：id / kind / source / tags / trace_id / content / 全局层归属。"""
    store = _store([KeyFact(entity="部署环境", value="生产集群 A")])

    store.compact(session_id="s1")

    entry = next(e for e in _facts(store) if e.id == "keyfact.部署环境")
    assert entry.kind == "semantic"
    assert entry.source == "extraction"
    assert entry.trace_id == "compaction.s1"
    assert entry.content == "部署环境: 生产集群 A"
    assert "entity:部署环境" in entry.tags and "session:s1" in entry.tags
    assert entry.session_id == "", "关键事实属全局层（不参与会话隔离），会话只作溯源标注"


def test_same_entity_is_idempotent_overwrite() -> None:
    """同实体至多一条：重复抽取覆盖式更新，条目不增长。"""
    holder: dict[str, list[KeyFact]] = {"facts": [KeyFact(entity="部署环境", value="生产集群 A")]}
    store = MemoryStore(
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=lambda entries: list(holder["facts"]),
    )
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    holder["facts"] = [KeyFact(entity="部署环境", value="生产集群 B")]
    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    hits = [e for e in _facts(store) if e.id == "keyfact.部署环境"]
    assert len(hits) == 1, "同实体 ⇒ 单条（不增长）"
    assert hits[0].content == "部署环境: 生产集群 B", "覆盖式更新"


def test_key_fact_is_global_so_visible_across_sessions() -> None:
    """全局层 ⇒ 他会话检索（`session_id` 过滤）仍可见。"""
    store = _store([KeyFact(entity="部署环境", value="生产集群 A")])
    store.compact(session_id="s1")

    found = store.read("部署环境", session_id="s2")

    assert any(e.id == "keyfact.部署环境" for e in found), "跨会话可见"


# ---- 密钥红线（端到端） ----


def test_secret_without_ref_is_dropped_with_warning() -> None:
    """裸密钥无引用 ⇒ 不落库 + `warnings.warn` 留痕（留痕**不含**取值）。"""
    store = _store([KeyFact(entity="API Key", value="sk-abcdefgh12345678")])

    with pytest.warns(RuntimeWarning) as caught:
        store.compact(session_id="s1")

    assert _facts(store) == [], "裸密钥 ⇒ 整条丢弃"
    joined = " ".join(str(w.message) for w in caught)
    assert "API Key" in joined, "留痕含实体名"
    assert "sk-abcdefgh12345678" not in joined, "留痕**不含**取值"


def test_secret_with_ref_is_stored_redacted() -> None:
    """引用式：密钥形态 + 引用 ⇒ 落库但取值为 `<redacted>`、引用进 tags。"""
    store = _store(
        [KeyFact(entity="API Key", value="sk-abcdefgh12345678", ref="coeffect:test_api_key")]
    )

    store.compact(session_id="s1")

    entry = next(iter(_facts(store)))
    assert entry.content == "API Key: <redacted>", "落库内容不含明文"
    assert "ref:coeffect:test_api_key" in entry.tags


def test_mixed_batch_keeps_compliant_facts() -> None:
    """fail-closed 只丢违规条：同批其余合规事实照常落库。"""
    store = _store(
        [
            KeyFact(entity="API Key", value="sk-abcdefgh12345678"),
            KeyFact(entity="部署环境", value="生产集群 A"),
        ]
    )

    with pytest.warns(RuntimeWarning):
        store.compact(session_id="s1")

    ids = {e.id for e in _facts(store)}
    assert ids == {"keyfact.部署环境"}, "只丢违规条"


# ---- 降级 / 有界 / 可撤销 / 零回归 ----


def test_extractor_exception_degrades_without_aborting_compaction() -> None:
    """抽取器抛错 ⇒ 不抽取 + 留痕；摘要照写、原条目照迁 L4（压实不中断）。"""

    def boom(entries: list[MemoryEntry]) -> list[KeyFact]:
        raise RuntimeError("extractor boom")  # noqa: TRY003 — 测试用哨兵异常

    store = MemoryStore(summarizer=lambda entries: "摘要：事实", key_fact_extractor=boom)
    store.write("L2", _episodic("e0", "s1"))

    with pytest.warns(RuntimeWarning):
        store.compact(session_id="s1")

    assert _facts(store) == []
    assert store.summary_for("s1") is not None, "摘要仍写回"
    assert dict(store.index().entries)["e0"] == "L4", "原条目仍迁 L4"


def test_unwired_extractor_changes_nothing() -> None:
    """未注入抽取器（缺省）⇒ 无 `key_fact` 条目，摘要 / 迁移逐字不变。"""
    store = MemoryStore(summarizer=lambda entries: "摘要：事实")
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert _facts(store) == [], "未注入 ⇒ 零抽取"
    assert store.summary_for("s1") is not None


def test_extraction_runs_without_summarizer() -> None:
    """抽取与摘要各自独立：未注入摘要器也能抽取（不写摘要条目）。"""
    store = MemoryStore(key_fact_extractor=lambda entries: [KeyFact(entity="部署环境", value="A")])
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")

    assert [e.id for e in _facts(store)] == ["keyfact.部署环境"]
    assert store.summary_for("s1") is None, "未注入摘要器 ⇒ 不写摘要条目"


def test_fact_count_is_bounded() -> None:
    """单次压实抽取条数有界（超出部分不落库）。"""
    over = MAX_KEY_FACTS_PER_COMPACT + 4
    many = [KeyFact(entity=f"实体{i}", value=f"值{i}") for i in range(over)]

    store = _store(many)
    store.compact(session_id="s1")

    assert len(_facts(store)) == MAX_KEY_FACTS_PER_COMPACT


def test_fact_length_is_bounded() -> None:
    """`entity` / `value` 长度有界（先脱敏后截断）。"""
    store = _store([KeyFact(entity="长" * 400, value="值" * 400)])

    store.compact(session_id="s1")

    entry = next(iter(_facts(store)))
    assert entry.content.count("长") <= _MAX_FACT_CHARS, "entity 长度有界"
    assert entry.content.count("值") <= _MAX_FACT_CHARS, "value 长度有界"


def test_key_facts_are_reverted_with_compaction() -> None:
    """关键事实与压实同 trace ⇒ 按 `compaction.<sid>` 回滚一并移除。"""
    tracker = EffectTracker()
    store = MemoryStore(
        effect_tracker=tracker,
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=lambda entries: [KeyFact(entity="部署环境", value="生产集群 A")],
    )
    store.write("L2", _episodic("e0", "s1"))

    store.compact(session_id="s1")
    assert "keyfact.部署环境" in dict(store.index().entries)

    report = tracker.rollback("compaction.s1")

    assert report.undo_failed == []
    assert "keyfact.部署环境" not in dict(store.index().entries), "回滚 ⇒ 关键事实一并移除"


def test_no_episodic_entries_no_extraction() -> None:
    """无 episodic 条目（无行动）⇒ 不抽取（承「无行动不记忆」）。"""
    store = MemoryStore(key_fact_extractor=lambda entries: [KeyFact(entity="X", value="Y")])

    store.compact(session_id="s1")

    assert _facts(store) == []


# ---- 解析（parse_key_facts） ----


def test_parse_tolerates_code_fence_and_surrounding_text() -> None:
    """容忍 ```json 围栏与前后杂文。"""
    text = '好的：\n```json\n[{"entity": "部署环境", "value": "生产集群 A"}]\n```\n以上。'
    assert parse_key_facts(text) == [KeyFact(entity="部署环境", value="生产集群 A", ref="")]


def test_parse_returns_empty_on_unparseable() -> None:
    """不可解析 ⇒ 空列表（降级为不抽取）。"""
    assert parse_key_facts("没有 JSON") == []
    assert parse_key_facts("[{不是 JSON}]") == []
    assert parse_key_facts('{"entity": "x"}') == []


def test_parse_skips_malformed_items() -> None:
    """非对象 / 缺字段 / 类型不符的元素被跳过，合规元素保留。"""
    text = '[1, {"entity": "A"}, {"entity": "B", "value": "b"}, {"entity": "C", "value": 3}]'
    assert parse_key_facts(text) == [KeyFact(entity="B", value="b", ref="")]


# ---- change 0172：抽取端质量（同批归并 / 解析失败可观测 / 取值首尾保留） ----


def test_same_batch_same_slug_is_merged_keeping_first() -> None:
    """同批同 slug（不同实体撞车 或 同实体不同取值）⇒ 归并为单条、取值为**首条**、并留痕。"""
    store = _store(
        [
            KeyFact(entity="API Key", value="首值"),
            KeyFact(entity="api-key", value="次值"),
        ]
    )

    with pytest.warns(RuntimeWarning) as caught:
        store.compact(session_id="s1")

    hits = _facts(store)
    assert [e.id for e in hits] == ["keyfact.api-key"], "同 slug ⇒ 单条"
    assert hits[0].content == "API Key: 首值", "保留**首条**的取值"
    joined = " ".join(str(w.message) for w in caught)
    assert "api-key" in joined, "归并留痕含实体名"
    assert "次值" not in joined, "归并留痕**不含**取值"


def test_same_batch_merge_does_not_consume_extra_quota() -> None:
    """归并后条数计额：同批重复不再挤占额度（第 8 个**不同**实体仍能落库）。"""
    facts = [KeyFact(entity="实体1", value="v1"), KeyFact(entity="实体1", value="v1重复")]
    facts += [
        KeyFact(entity=f"实体{i}", value=f"v{i}") for i in range(2, MAX_KEY_FACTS_PER_COMPACT + 1)
    ]

    store = _store(facts)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        store.compact(session_id="s1")

    ids = sorted(e.id for e in _facts(store))
    assert len(ids) == MAX_KEY_FACTS_PER_COMPACT, "归并后仍可落满额度"
    assert f"keyfact.实体{MAX_KEY_FACTS_PER_COMPACT}" in ids, "第 8 个不同实体未被重复项挤出"


def test_unparseable_output_warns_without_dumping_model_text() -> None:
    """有输出但无 JSON 数组 ⇒ 不抽取 + 留痕；留痕**不含**模型输出正文（可能含明文密钥）。"""
    sentinel = "sk-abcdefgh12345678"
    store = MemoryStore(
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=extract_with(lambda prompt: f"我无法判断，参考 {sentinel} 好了"),
    )
    store.write("L2", _episodic("e0", "s1"))

    with pytest.warns(RuntimeWarning) as caught:
        store.compact(session_id="s1")

    assert _facts(store) == [], "不可解析 ⇒ 不抽取"
    joined = " ".join(str(w.message) for w in caught)
    assert sentinel not in joined, "留痕**不含**模型输出正文"


def test_empty_json_array_does_not_warn() -> None:
    """合法空数组（模型明确表示无可抽）⇒ 正常结果，**不**告警（防误报）。"""
    store = MemoryStore(
        summarizer=lambda entries: "摘要：事实",
        key_fact_extractor=extract_with(lambda prompt: "[]"),
    )
    store.write("L2", _episodic("e0", "s1"))

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store.compact(session_id="s1")

    assert _facts(store) == []
    assert [w for w in caught if "unparseable" in str(w.message)] == [], "合法空数组不告警"


def test_long_value_keeps_head_and_tail() -> None:
    """取值超长 ⇒ 首尾保留（头尾皆在、中以 `…` 连接），总额度 `_MAX_FACT_CHARS` 不变。"""
    value = "头" * 10 + "甲" * 300 + "尾" * 10  # CJK 填充：不触发「长随机串」脱敏
    store = _store([KeyFact(entity="长文", value=value)])

    store.compact(session_id="s1")

    entry = next(iter(_facts(store)))
    kept = entry.content.split(": ", 1)[1]
    assert len(kept) <= _MAX_FACT_CHARS, "总额度不变"
    assert kept.startswith("头" * 10), "保留头部"
    assert kept.endswith("尾" * 10), "**同时**保留尾部"
    assert "…" in kept, "截断处以省略号标示"


def test_entity_and_ref_keep_head_only_truncation() -> None:
    """`entity` / `ref` 维持头部截断（形态未被误改为首尾保留）。"""
    long_ref = "coeffect:" + "ab." * 70  # 长但非密钥形态（无 ≥32 连续 alnum 段）
    cleaned = scrub_key_fact(KeyFact(entity="长" * 400, value="v", ref=long_ref))

    assert cleaned is not None
    assert cleaned.entity == "长" * _MAX_FACT_CHARS and "…" not in cleaned.entity
    assert cleaned.ref == long_ref[:_MAX_FACT_CHARS] and "…" not in cleaned.ref
