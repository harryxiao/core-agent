"""context 单元测试（对齐 §5 契约 + M2 验收锚点）。

覆盖：预算控制超限裁剪保留关键 / 信息地图定位与失效重建 / 压实不丢关键 /
宪法与项目信息注入。
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from core.context import (
    BudgetManager,
    Compactor,
    ContextError,
    ContextErrorCode,
    ContextPack,
    DynamicAssembler,
    InfoMap,
)
from core.memory import MemoryStore

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


def test_enforce_allocates_remaining_budget_to_skills() -> None:
    """skills 用**剩余**预算裁剪，而非恒 0（原 _trim(skills, 0) 使技能恒空）。"""
    skill = {"source": "s", "content": "k" * 40}
    pack = ContextPack(task="t", stage="s", facts=[], skills=[skill])
    out = BudgetManager().enforce(pack, budget=100)
    assert out.skills == [skill]


def test_enforce_budget_exceeded_when_mandatory_over() -> None:
    pack = ContextPack(task="t", stage="s", constitution=["x" * 40], pending=["p" * 40])
    with pytest.raises(ContextError) as exc_info:
        BudgetManager().enforce(pack, budget=1)
    assert exc_info.value.code is ContextErrorCode.BUDGET_EXCEEDED


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


# ---- 压实 ----


def test_compactor_should_compact_threshold() -> None:
    c = Compactor()
    assert c.should_compact(10, 0, 100) is True
    assert c.should_compact(5, 200, 100) is True
    assert c.should_compact(5, 50, 100) is False


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


def test_assembler_missing_project_degrades() -> None:
    assembler = DynamicAssembler()
    pack = assembler.build("t", "s", budget=100)
    assert pack.facts == []


def test_assembler_recalls_facts_by_task() -> None:
    """检索 query 为任务目标（task-keyed），非阶段名——对齐架构图数据流 :117。"""

    class _SpyMemory:
        def __init__(self) -> None:
            self.queries: list[str] = []

        def read(self, query: str, budget: int = 0) -> list[SimpleNamespace]:
            self.queries.append(query)
            return [SimpleNamespace(source="episodic", content=f"fact:{query}")]

    spy = _SpyMemory()
    assembler = DynamicAssembler(memory=spy)  # type: ignore[arg-type]
    pack = assembler.build("部署流水线", "reason", budget=1000)
    assert spy.queries == ["部署流水线"], "应以任务为目标 query 检索，而非阶段名"
    assert any(f["content"] == "fact:部署流水线" for f in pack.facts)
