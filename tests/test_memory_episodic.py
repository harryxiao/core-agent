"""情景归纳（change 0218 / ADR-0208 / 台账 E155）。

四个面：① 新模块 `core.memory.episodic` 的 prompt / 工厂形状；② `MemoryStore` 新接缝
`episodic_extractor` 的**缺省零变化**与**缺省关**；③ 归纳条目形状（`id` / `source` / `kind` /
`tags` / `trace_id` / `session_id`）＋ 脱敏有界 ＋ 幂等覆盖 ＋ 异常降级；④ **承重**：归纳产物
**不回喂**摘要器（自激环的结构性阻断）＋ 配置三面 ＋ 组合根接线。
"""

from __future__ import annotations

import warnings
from pathlib import Path
from typing import cast

import pytest

from core.configuration import ConfigManager, config_specs
from core.memory import (
    MAX_EPISODIC_CHARS,
    MemoryEntry,
    MemoryStore,
    build_episodic_prompt,
    consolidate_with,
    redact_secrets,
)
from core.runtime import build_runtime

_MAX_ENTRY_CHARS = 400  # 与 `episodic._MAX_ENTRY_CHARS` 同刻度（单条入 prompt 节选上界）

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


def _contents(store: MemoryStore) -> dict[str, str]:
    return {entry.id: entry.content for entry in store.audit()}


# ---- ① 模块形状 ----


def test_prompt_head_declares_four_sections() -> None:
    """专属 prompt 四段结构（目标 / 经过 / 结果 / 教训）＋ 概要口径。"""
    prompt = build_episodic_prompt([_episodic("e0", "s1")])

    assert "情景归纳" in prompt
    for section in ("目标", "经过", "结果", "教训"):
        assert section in prompt, section


def test_build_prompt_renders_bounded_entry_lines() -> None:
    """条目逐条渲染为 ``- `` 行且**逐条节选**（token 有界）。"""
    long_text = "甲" * 900
    entries = [_episodic("e0", "s1", long_text), _episodic("e1", "s1")]
    prompt = build_episodic_prompt(entries)

    lines = [line for line in prompt.splitlines() if line.startswith("- ")]
    assert len(lines) == len(entries)
    assert all(len(line) <= _MAX_ENTRY_CHARS + 2 for line in lines), "单条节选上界（400 ＋ '- '）"
    assert long_text not in prompt


def test_consolidate_with_calls_llm_and_strips() -> None:
    """工厂把「prompt → 文本」桥接为归纳契约；首尾空白剥除。"""
    seen: list[str] = []

    def fake_llm(prompt: str) -> str:
        seen.append(prompt)
        return "  归纳：完成了部署  \n"

    extractor = consolidate_with(fake_llm)
    result = extractor([_episodic("e0", "s1")])

    assert result == "归纳：完成了部署"
    assert len(seen) == 1
    assert "会话事件：" in seen[0]


# ---- ② 缺省零变化 / 缺省关 ----


def test_default_store_has_no_extractor() -> None:
    """缺省 UNWIRED ⇒ 不归纳（既有路径逐字不变）。"""
    assert MemoryStore()._episodic_extractor is None  # noqa: SLF001 — 接线锚


def test_disabled_only_switches_consolidation() -> None:
    """逐字锚：门**只**切归纳 —— 未注入与「注入恒返回空串」的产物**逐字相同**。"""
    unwired = _compact(None)
    blank = _compact(lambda _entries: "   ")

    assert [eid for eid in unwired if eid.startswith("episodic.")] == [], "未注入 ⇒ 无归纳条目"
    assert [eid for eid in blank if eid.startswith("episodic.")] == [], "空文本 ⇒ 不落条目"
    assert unwired == blank, "两态产物逐字相同"


def _compact(extractor: object) -> dict[str, str]:
    store = MemoryStore(summarizer=lambda _entries: "摘要：事实", episodic_extractor=extractor)  # type: ignore[arg-type]
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    return _contents(store)


# ---- ③ 条目形状 / 脱敏 / 幂等 / 降级 ----


def test_consolidated_entry_shape() -> None:
    """归纳条目形状：id / source / kind / tags / trace_id / session_id 六项齐备。"""
    store = MemoryStore(episodic_extractor=lambda _entries: "归纳：完成")
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    entry = store._entry_by_id("episodic.s1")  # noqa: SLF001 — 形状锚
    assert entry is not None
    assert (entry.source, entry.kind, entry.layer) == ("episodic", "semantic", "L2")
    assert entry.tags == ["episodic", "session:s1"]
    assert entry.trace_id == "compaction.s1"
    assert entry.session_id == "", "全局层（同关键事实 / 关系）"
    assert entry.content == "归纳：完成"


def test_one_entry_per_session_and_overwrite() -> None:
    """每会话至多一条：同会话再归纳按同一 id **覆盖**，条目不增长。"""
    store = MemoryStore(
        episodic_extractor=lambda entries: "归纳：" + "+".join(e.id for e in entries)
    )
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")
    first = _contents(store)["episodic.s1"]

    store.write("L2", _episodic("e1", "s1"))
    store.compact(session_id="s1")

    assert _contents(store)["episodic.s1"] != first, "覆盖式更新"
    assert [eid for eid in _contents(store) if eid.startswith("episodic.")] == ["episodic.s1"]


def test_entries_are_per_session() -> None:
    """会话间**不互相覆盖**（id 带 key）且互不串材料。"""
    store = MemoryStore(episodic_extractor=lambda entries: f"归纳：{entries[0].session_id}")
    store.write("L2", _episodic("e0", "s1"))
    store.write("L2", _episodic("e1", "s2"))
    store.compact()

    contents = _contents(store)
    assert contents["episodic.s1"] == "归纳：s1"
    assert contents["episodic.s2"] == "归纳：s2"


def test_not_fed_back_to_summarizer() -> None:
    """**承重**：归纳产物（`kind="semantic"`）不进 `_episodic_groups` ⇒ 不回喂摘要器。

    必须走**全量**压实（`compact()` 不带 `session_id`）：会话收窄路径本就按 `session_id` 过滤，
    归纳条目（`session_id=""`）在那里**无论如何**都不入选 ⇒ 用会话路径测不出 `kind` 承重
    （反证 B 即由此暴露）。全量路径无会话过滤 ⇒ 唯一挡它的是 `kind` 判据。
    """
    seen: list[list[str]] = []

    def summarizer(entries: list[MemoryEntry]) -> str:
        seen.append([entry.id for entry in entries])
        return "摘要：事实"

    store = MemoryStore(summarizer=summarizer, episodic_extractor=lambda _entries: "归纳：完成")
    store.write("L2", _episodic("e0", "s1"))
    store.compact()
    assert "episodic.s1" in _contents(store), "归纳确已落地（前置条件）"

    mark = len(seen)
    store.write("L2", _episodic("e1", "s1"))
    store.compact()

    # 逐组**全查**（不能只看 `seen[-1]`）：全量压实会按 `session_id` 分多组，归纳产物若入选会
    # 自成 `""` 组 —— 只看最后一次调用会漏掉它（反证 B 第一次跑即栽在此处）。
    fed = [entry_id for ids in seen[mark:] for entry_id in ids]
    assert "e1" in fed, "新事件仍进材料"
    assert "episodic.s1" not in fed, "归纳产物**不**回喂（`kind` 承重，无自激环）"


def test_content_redacted_and_bounded() -> None:
    """store 侧**无条件**脱敏 ＋ 截断有界（归纳器不构成信任边界）。"""
    raw = "api_key: sk-abcdefghijklmnop  " + "乙" * (MAX_EPISODIC_CHARS * 3)
    store = MemoryStore(episodic_extractor=lambda _entries: raw)
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    content = _contents(store)["episodic.s1"]
    assert len(content) <= MAX_EPISODIC_CHARS, "有界"
    assert "sk-abcdefghijklmnop" not in content, "明文密钥不得落库"
    assert "<redacted>" in content


def test_redact_secrets_is_the_boundary() -> None:
    """脱敏原语与 store 行为同源（改一处即两处变）。"""
    assert "sk-abcdefghijklmnop" not in redact_secrets("key sk-abcdefghijklmnop")


def test_error_degrades_without_warning_leak() -> None:
    """归纳失败降级：不落条目、告警**只报会话键**，摘要与关键事实**照常完成**。"""

    def boom(_entries: list[MemoryEntry]) -> str:
        raise RuntimeError("consolidate_failed")

    store = MemoryStore(summarizer=lambda _entries: "摘要：事实", episodic_extractor=boom)
    store.write("L2", _episodic("e0", "s1"))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store.compact(session_id="s1")

    messages = [str(w.message) for w in caught]
    assert any("s1" in message for message in messages), "留痕含会话键"
    assert all("事件" not in message for message in messages), "不回显正文"
    contents = _contents(store)
    assert [eid for eid in contents if eid.startswith("episodic.")] == []
    assert contents["compaction.summary.s1"] == "摘要：事实", "摘要照常完成"


def test_consolidation_runs_without_summarizer() -> None:
    """`compact()` 守卫含归纳器 ⇒ 只注入归纳器（无摘要器）也真的跑。"""
    store = MemoryStore(episodic_extractor=lambda _entries: "归纳：完成")
    store.write("L2", _episodic("e0", "s1"))
    store.compact(session_id="s1")

    assert "episodic.s1" in _contents(store)


def test_untouched_when_no_entries() -> None:
    """无被聚合条目 ⇒ 不归纳、零写入（不被空材料调用）。"""
    calls: list[int] = []
    store = MemoryStore(episodic_extractor=lambda entries: calls.append(len(entries)) or "归纳")
    store.compact(session_id="s1")

    assert calls == []
    assert _contents(store) == {}


# ---- ④ 配置三面 ＋ 组合根接线 ----


def test_spec_declares_episodic_extract() -> None:
    """单一真源：新键经 ConfigSpec 声明 ⇒ CLI flag / env / yaml 三面自动齐备，缺省 False。"""
    spec = {spec.key: spec for spec in config_specs()}["memory.episodic_extract"]

    assert (spec.cli_flag, spec.env_var, spec.default, spec.map_to) == (
        "--memory-episodic-extract",
        "CORE_MEMORY_EPISODIC_EXTRACT",
        False,
        "memory.episodic_extract",
    )


def test_default_off(tmp_path: Path) -> None:
    """缺省关 ⇒ 不构造归纳器（未配置路径逐字不变）。"""
    assert _manager(tmp_path).episodic_extract() is False


def test_yaml_and_env_enable(tmp_path: Path) -> None:
    """yaml / env 两面可达（取值归一同 feature flag 集），且 `memory:` 已声明不报未知段。"""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        yaml_on = _manager(tmp_path, "memory:\n  episodic_extract: true\n")
        env_on = _manager(tmp_path, "", environ={"CORE_MEMORY_EPISODIC_EXTRACT": "on"})

    assert yaml_on.episodic_extract() is True
    assert env_on.episodic_extract() is True
    assert [w for w in caught if "未知配置段" in str(w.message)] == []


def test_unknown_value_falls_back_off(tmp_path: Path) -> None:
    """非法取值归一为**关闭**（方向恒为「不归纳」）。"""
    assert _manager(tmp_path, "memory:\n  episodic_extract: maybe\n").episodic_extract() is False


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _memory(runtime: object) -> MemoryStore:
    return cast(MemoryStore, runtime.memory)  # type: ignore[attr-defined]


def test_runtime_wiring_two_states(tmp_path: Path, state_dir: Path) -> None:
    """组合根接线两态：缺省 ⇒ `None`；置 true ⇒ 注入归纳器（同一 `_llm_text` 接缝）。"""
    off = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    on = build_runtime(
        ConfigManager(yaml_path=_write_config(tmp_path, "memory:\n  episodic_extract: true\n"))
    )

    assert _memory(off)._episodic_extractor is None  # noqa: SLF001 — 接线锚
    assert _memory(on)._episodic_extractor is not None  # noqa: SLF001 — 接线锚
