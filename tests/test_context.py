"""context 单元测试（对齐 §5 契约 + M2 验收锚点）。

覆盖：预算控制超限裁剪保留关键 / 信息地图定位与失效重建 / 压实不丢关键 /
宪法与项目信息注入。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from core.configuration import ConfigManager
from core.context import (
    BudgetManager,
    Compactor,
    ContextError,
    ContextErrorCode,
    ContextPack,
    DynamicAssembler,
    InfoMap,
)
from core.context.compactor import _STEP_THRESHOLD
from core.memory import MemoryEntry, MemoryStore
from core.runtime import build_runtime

# ---- 预算控制 ----


def test_enforce_trims_low_priority_facts() -> None:
    fact_count = 5
    budget = 20
    pack = ContextPack(
        task="t",
        stage="s",
        constitution=["rule"],
        pending=["todo"],
        facts=[{"source": "m", "content": "f" * 40} for _ in range(fact_count)],
    )
    out = BudgetManager().enforce(pack, budget=budget)
    assert len(out.facts) < fact_count
    assert out.token_used <= budget


def test_enforce_skips_oversized_fact_keeps_smaller() -> None:
    """放不下的项应**跳过**而非掐断后续——避免头部大项阻塞（B5）。"""
    big = {"source": "m", "content": "x" * 400}
    small1 = {"source": "m", "content": "a" * 40}
    small2 = {"source": "m", "content": "b" * 40}
    pack = ContextPack(task="t", stage="s", facts=[small1, big, small2])
    budget = 40
    out = BudgetManager().enforce(pack, budget=budget)
    contents = [f["content"] for f in out.facts]
    assert small1["content"] in contents and small2["content"] in contents, "小项应被填充"
    assert big["content"] not in contents, "超预算大项被裁剪"
    assert out.token_used <= budget


def test_enforce_budget_exceeded_when_mandatory_over() -> None:
    pack = ContextPack(task="t", stage="s", constitution=["x" * 40], pending=["p" * 40])
    with pytest.raises(ContextError) as exc_info:
        BudgetManager().enforce(pack, budget=1)
    assert exc_info.value.code is ContextErrorCode.BUDGET_EXCEEDED


class _FixedEstimator:
    """定值估算器：每次调用记 1 token（change 0230 / G1）。"""

    def __init__(self, value: int) -> None:
        self.value = value
        self.calls = 0

    def estimate(self, text: str) -> int:
        self.calls += 1
        return self.value


def test_budget_default_estimator_is_heuristic() -> None:
    """未注入估算器 ⇒ 共享启发式（task/stage 各 1 token）。"""
    pack = ContextPack(task="t", stage="s")
    out = BudgetManager().enforce(pack, budget=100)
    assert out.token_used == 2  # noqa: PLR2004 — task/stage 各 1


def test_budget_uses_injected_estimator() -> None:
    """注入估算器 ⇒ 测量与裁剪全部取自注入实现。"""
    estimator = _FixedEstimator(7)
    pack = ContextPack(task="t", stage="s")
    out = BudgetManager(estimator=estimator).enforce(pack, budget=100)
    assert out.token_used == 14  # noqa: PLR2004 — 两个字段 × 固定 7
    assert estimator.calls > 0


def test_assembler_passes_estimator_to_budget() -> None:
    estimator = _FixedEstimator(5)
    assembler = DynamicAssembler(
        project_info=["project"], constitution=["rule"], token_estimator=estimator
    )
    pack = assembler.build("task", "stage", budget=100)
    assert pack.token_used == 20  # noqa: PLR2004 — 四个字段 × 固定 5
    assert estimator.calls > 0


# ---- 信息地图 ----


def test_info_map_index_and_lookup() -> None:
    m = InfoMap()
    m.index("doc", "# 结论\n正文")
    pointers = m.lookup("doc", "结论")
    assert pointers and pointers[0].section == "结论"


def test_info_map_lookup_missing_empty() -> None:
    m = InfoMap()
    assert m.lookup("absent", "q") == []


def test_info_map_rebuild_if_stale_missing_raises() -> None:
    m = InfoMap()
    with pytest.raises(ContextError) as exc_info:
        m.rebuild_if_stale("missing", "hash")
    assert exc_info.value.code is ContextErrorCode.MAP_STALE


def test_info_map_rebuild_if_stale_reindexes_on_change() -> None:
    m = InfoMap()
    m.index("doc", "# old")
    m.rebuild_if_stale("doc", "new-hash")  # 不抛异常，重建成功
    assert len(m.lookup("doc", "")) == 1


def test_info_map_register_raw_only_falls_back_to_linear_scan() -> None:
    """change 0140 / E77：仅登记原文（索引不可用）⇒ 二阶兜底逐段命中，不因索引缺失中断。"""
    m = InfoMap()
    m.register("doc", "第一段\n目标段落\n第三段")
    pointers = m.lookup("doc", "目标")
    assert [p.section for p in pointers] == ["seg-1"]
    assert pointers[0].summary == "目标段落"


def test_info_map_linear_scan_is_bounded() -> None:
    """「**受控**分段线性扫描」：段数设硬上界，索引不可用时不把窗口撑爆。"""
    m = InfoMap()
    m.register("doc", "\n".join(f"line-{i}" for i in range(100)))
    assert len(m.lookup("doc", "line")) == 20  # noqa: PLR2004 — 段数上界 _MAX_SCAN_SEGMENTS


def test_info_map_documents_lists_registered_ids() -> None:
    m = InfoMap()
    m.index("indexed", "# 一")
    m.register("raw-only", "原文")
    assert m.documents() == ["indexed", "raw-only"]


# ---- 压实 ----


def test_compactor_should_compact_threshold() -> None:
    """首参为**本轮工具步数**（阈值缺省 6），与 token 维度取或（change 0182 诚实化）。"""
    c = Compactor()
    assert c.should_compact(_STEP_THRESHOLD, 0, 100) is True, "步数达阈值即触发"
    assert c.should_compact(_STEP_THRESHOLD - 1, 200, 100) is True, "token 达预算亦触发"
    assert c.should_compact(_STEP_THRESHOLD - 1, 50, 100) is False, "两维度均未达 ⇒ 不触发"


def test_compactor_extracts_key_info() -> None:
    c = Compactor()
    result = c.compact(
        [
            {"id": "1", "content": "结论：任务完成", "redundant": True},
            {"id": "2", "content": "决定采用方案A"},
            {"id": "3", "content": "下一步：写测试"},
            {"id": "4", "content": "普通内容"},
        ]
    )
    assert result.conclusions
    assert result.decisions
    assert result.open_items
    assert "1" in result.dropped


def test_compactor_persist_lossy_rejected() -> None:
    c = Compactor()
    result = c.compact([{"id": "1", "content": "普通内容"}])
    with pytest.raises(ContextError) as exc_info:
        c.persist(result)
    assert exc_info.value.code is ContextErrorCode.COMPACTION_LOSSY


def test_compactor_persist_writes_to_memory() -> None:
    memory = MemoryStore()
    c = Compactor(memory=memory)
    c.persist(c.compact([{"id": "1", "content": "结论：完成"}]))
    assert memory.read("") != []


def test_compactor_persist_writes_semantic_with_provenance() -> None:
    """沉淀产物为 semantic 条目，且 tags 携带原始 id 出处（0041：不再写匿名条目）。"""
    memory = MemoryStore()
    c = Compactor(memory=memory)
    c.persist(
        c.compact(
            [
                {"id": "h1", "content": "结论：完成"},
                {"id": "h2", "content": "决定采用方案A"},
            ]
        )
    )
    entries = memory.audit()
    assert entries and all(e.kind == "semantic" for e in entries)
    tags = {tag for e in entries for tag in e.tags}
    assert {"from:h1", "from:h2"} <= tags


# ---- 动态装配 ----


def test_assembler_injects_constitution_and_project() -> None:
    assembler = DynamicAssembler(constitution=["宪法规则"], project_info=["项目信息"])
    pack = assembler.build("任务", "阶段", budget=1000)
    assert "宪法规则" in pack.constitution
    assert any(f["source"] == "project" and f["content"] == "项目信息" for f in pack.facts)


def test_assembler_fetch_detail() -> None:
    info_map = InfoMap()
    info_map.index("doc", "# 章节\n内容")
    assembler = DynamicAssembler(info_map=info_map)
    assert assembler.fetch_detail("doc#章节") == "章节"


def test_assembler_build_injects_pointer_catalog() -> None:
    """change 0140 / E77：`build()` 真的读信息地图 ⇒ 目录层进上下文包（全文不进窗口）。"""
    info_map = InfoMap()
    info_map.index("doc", "# 章节\n内容")
    assembler = DynamicAssembler(info_map=info_map)
    pack = assembler.build("章节", "reason", budget=2048)
    assert pack.pointers == [
        {"doc_id": "doc", "section": "章节", "summary": "章节", "pointer": "doc#章节"}
    ]


def test_assembler_build_pointers_empty_without_documents() -> None:
    """地图为空（未登记任何文档）⇒ 目录层为空，装配行为与既往逐字一致。"""
    pack = DynamicAssembler(info_map=InfoMap()).build("任务", "reason", budget=2048)
    assert pack.pointers == []


def test_assembler_missing_project_degrades() -> None:
    assembler = DynamicAssembler()
    pack = assembler.build("t", "s", budget=100)
    assert pack.facts == []


def test_assembler_recalls_facts_by_task() -> None:
    """检索 query 为任务目标（task-keyed），非阶段名——对齐架构图数据流 :117。"""

    class _SpyMemory:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def read(self, query: str, budget: int = 0, **kwargs: Any) -> list[SimpleNamespace]:
            self.queries.append(query)
            if "L2" not in kwargs.get("layers", ("L2",)):
                return []
            return [
                SimpleNamespace(
                    id=f"fact:{query}",
                    layer="L2",
                    source="episodic",
                    content=f"fact:{query}",
                    tags=[],
                    ts=1.0,
                )
            ]

    spy = _SpyMemory()
    assembler = DynamicAssembler(memory=spy)  # type: ignore[arg-type]
    pack = assembler.build("部署流水线", "reason", budget=1000)
    assert set(spy.queries) == {"部署流水线"}, "应以任务为目标 query 检索，而非阶段名"
    assert any(f["content"] == "fact:部署流水线" for f in pack.facts)


@pytest.fixture
def state_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("CORE_STATE_DIR", str(tmp_path / "state"))
    return tmp_path / "state"


def _write_config(tmp_path: Any) -> str:
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


# ---- 压缩产物退出事实注入面（change 0185 / ADR-0176 / 账本 E122）----
# 规格「动态上下文构建」：已由专块（「历史摘要（长期）/（中期）」）每轮注入的压缩产物
# （会话长期 / 中期摘要，`source == "compaction"`）SHALL NOT 再次进入「相关事实」注入面 ——
# 同一份正文两条通道是纯浪费预算，且会被读成两条独立证据。无专块承载的压缩产出
# （`source == "context"`，压缩产出的事实 / 未决）不受影响。


def _fact_spy() -> Any:
    """假 MemoryStore：返回两条压缩产物（`compaction`）+ 两条压缩派生物（`context`）。"""

    def _entry(entry_id: str, source: str, content: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=entry_id,
            layer="L2",
            source=source,
            content=content,
            tags=["compaction"],
            ts=1.0,
        )

    class _SpyMemory:
        def read(self, query: str, budget: int = 0, **kwargs: Any) -> list[SimpleNamespace]:
            return [
                _entry("compaction.summary.default", "compaction", "长期摘要"),
                _entry("compaction.mid.default", "compaction", "中期摘要"),
                _entry("compaction.fact.default.0", "context", "事实"),
                _entry("compaction.open.default.0", "context", "未决"),
            ]

    return _SpyMemory()


def test_fact_source_exclusion_drops_compaction_entries() -> None:
    """排除面 `("compaction",)` ⇒ 长期 / 中期摘要不进 `facts`（前缀匹配 `MemoryEntry.source`）。"""
    assembler = DynamicAssembler(memory=_fact_spy(), exclude_fact_sources=("compaction",))
    pack = assembler.build("t", "s", budget=4096)

    sources = [f["source"] for f in pack.facts]
    assert "compaction" not in sources, "已由专块注入的压缩产物不得再进事实面"
    assert sources == ["context", "context"], "压缩派生物（source=context）不受影响"


def test_fact_source_exclusion_default_is_verbatim() -> None:
    """缺省**空**排除面 ⇒ 不建过滤、装配结果与既往**逐字一致**（四条全在）。"""
    assembler = DynamicAssembler(memory=_fact_spy())
    pack = assembler.build("t", "s", budget=4096)

    assert [f["source"] for f in pack.facts] == ["compaction", "compaction", "context", "context"]


def test_fact_source_exclusion_is_prefix_based() -> None:
    """前缀语义：`("compaction.",)`（带点）匹配不到裸 `compaction` ⇒ 排除面按前缀**字面**生效。"""
    assembler = DynamicAssembler(memory=_fact_spy(), exclude_fact_sources=("compaction.",))
    pack = assembler.build("t", "s", budget=4096)

    assert [f["source"] for f in pack.facts] == ["compaction", "compaction", "context", "context"]


def test_fact_source_exclusion_survives_namespace_derivation() -> None:
    """`with_allow_source_prefixes` 派生装配器**继承**事实面排除面（放行面不与之纠缠）。"""
    sealed = DynamicAssembler(memory=_fact_spy(), exclude_fact_sources=("compaction",))
    derived = sealed.with_allow_source_prefixes("beast.qinglong")

    assert derived._exclude_fact_sources == ("compaction",)  # noqa: SLF001 — 派生继承断言
    facts = derived.build("t", "s", budget=4096).facts
    assert [f["source"] for f in facts] == ["context", "context"]


def test_summary_stays_readable_through_memory_read() -> None:
    """排除**只**落在装配面的注入步骤：`MemoryStore.read` 仍能取回摘要（检索语义逐字不变）。"""
    store = MemoryStore()
    store.write(
        "L2",
        MemoryEntry(
            id="compaction.mid.default",
            layer="L2",
            content="中期摘要正文",
            tags=["compaction", "mid"],
            source="compaction",
            trace_id="compaction.mid.default",
        ),
    )
    assert [e.id for e in store.read("中期摘要正文")] == ["compaction.mid.default"]


def test_build_runtime_excludes_compaction_from_fact_face(tmp_path, state_dir) -> None:
    """组合根装配的主装配器真的带上排除面（接线，非仅接口存在）。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assembler = runtime.loop._planner._assembler  # noqa: SLF001 — 主 loop 的真实装配器
    assert assembler._exclude_fact_sources == ("compaction",)  # noqa: SLF001 — 接线断言
    assert assembler._exclude_source_prefixes == ("beast.", "pet")  # noqa: SLF001 — 封存红线逐字不动


# ---- 原始步序素材退出事实注入面（change 0186 / ADR-0177 / 账本 E123）----
# 规格「动态上下文构建」：声明角色为**抽取器素材**的原始行动序列（`loop.steps.<trace>`，
# `tags` 含 `steps`）SHALL NOT 进入「相关事实」注入面 —— 其信息已由同轮轨迹条目
# （`loop.<trace>`）与（失败时）失败摘要（`loop.failure.<trace>`）承载。三者的 `source`
# **同为** `"loop"` ⇒ 来源面天然不可分（这正是 `exclude_fact_sources` 在此够不着的原因），
# 区分判据只有 `tags`（`loop` / `steps` / `trajectory` / `failure`）。`read()` 语义不变
# ⇒ 抽取器素材角色不受影响。


def _steps_spy() -> Any:
    """假 MemoryStore：返原始步序（含 `steps` 标签）+ 轨迹 + 失败摘要（皆不含 `steps`）。"""

    def _entry(entry_id: str, source: str, tags: list[str], content: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=entry_id, layer="L2", source=source, tags=tags, content=content, ts=1.0
        )

    class _SpyMemory:
        def read(self, query: str, budget: int = 0, **kwargs: Any) -> list[SimpleNamespace]:
            return [
                _entry("loop.steps.t1", "loop", ["loop", "steps"], "原始步序"),
                _entry("loop.t1", "loop", ["loop", "trajectory"], "轨迹"),
                _entry("loop.failure.t1", "loop", ["loop", "failure"], "失败摘要"),
            ]

    return _SpyMemory()


def test_fact_tag_exclusion_drops_step_entries() -> None:
    """排除面 `{"steps"}` ⇒ 原始步序不进 `facts`（**标签交集**匹配），轨迹 / 失败摘要仍在。"""
    assembler = DynamicAssembler(memory=_steps_spy(), exclude_fact_tags=frozenset({"steps"}))
    pack = assembler.build("t", "s", budget=4096)

    ids = [f["content"] for f in pack.facts]
    assert "原始步序" not in ids, "声明角色为素材的原始步序不得进事实面"
    assert ids == ["轨迹", "失败摘要"], "轨迹与失败摘要（无 steps 标签）不受影响"


def test_fact_tag_exclusion_default_is_verbatim() -> None:
    """缺省**空**排除面 ⇒ 不建过滤、装配结果与既往**逐字一致**（三条全在）。"""
    assembler = DynamicAssembler(memory=_steps_spy())
    pack = assembler.build("t", "s", budget=4096)

    assert [f["content"] for f in pack.facts] == ["原始步序", "轨迹", "失败摘要"]


def test_fact_tag_exclusion_is_intersection_based() -> None:
    """**交集**语义：条目多标签**任一**命中即挡；空标签永不挡；排除面**字面**比较（非前缀）。"""

    def _entry(entry_id: str, tags: list[str]) -> SimpleNamespace:
        return SimpleNamespace(
            id=entry_id, layer="L2", source="loop", tags=tags, content=entry_id, ts=1.0
        )

    class _SpyMemory:
        def read(self, query: str, budget: int = 0, **kwargs: Any) -> list[SimpleNamespace]:
            return [
                _entry("multi", ["loop", "steps", "extra"]),
                _entry("no-tags", []),
                _entry("near-miss", ["steps2"]),
            ]

    assembler = DynamicAssembler(memory=_SpyMemory(), exclude_fact_tags=frozenset({"steps"}))
    assert [f["content"] for f in assembler.build("t", "s", budget=4096).facts] == [
        "no-tags",
        "near-miss",
    ]


def test_step_sequence_stays_readable_through_memory_read() -> None:
    """排除**只**落注入步骤：`MemoryStore.read` 仍能取回原始步序（抽取器素材角色不变）。"""
    store = MemoryStore()
    store.write(
        "L2",
        MemoryEntry(
            id="loop.steps.t1",
            layer="L2",
            content="原始步序正文",
            tags=["loop", "steps"],
            source="loop",
            trace_id="t1",
        ),
    )
    assert [e.id for e in store.read("原始步序正文")] == ["loop.steps.t1"]


def test_build_runtime_excludes_steps_from_fact_face(tmp_path, state_dir) -> None:
    """组合根装配的主装配器真的带上**标签**排除面，且既有两面（来源 / 封存）逐字不动。"""
    runtime = build_runtime(ConfigManager(yaml_path=_write_config(tmp_path)))
    assembler = runtime.loop._planner._assembler  # noqa: SLF001 — 主 loop 的真实装配器
    assert assembler._exclude_fact_tags == frozenset({"steps"})  # noqa: SLF001 — 接线断言
    assert assembler._exclude_fact_sources == ("compaction",)  # noqa: SLF001 — 来源面逐字不动
    assert assembler._exclude_source_prefixes == ("beast.", "pet")  # noqa: SLF001 — 封存红线逐字不动
