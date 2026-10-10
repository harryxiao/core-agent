"""重要度评分器工厂（memory）—— change 0181 / ADR-0172 / 台账 E118。

``score_with`` 与 ``summarize_with`` / ``extract_with`` 同一「prompt → 文本」接缝：
memory **不 import** 任何 LLM / rag 抽象（ADR-0045 单向），prompt 文本属 memory 域。
解析失败 / 界外值**不**在工厂内兜底 —— 交闸门既有路径降级放行（方向恒为放行）。
"""

from __future__ import annotations

import ast
import pathlib
import warnings

import pytest

from core.memory import MemoryEntry, MemoryStore
from core.memory.importance import score_with
from core.memory.store import _IMPORTANCE_FLOOR

SRC = pathlib.Path(__file__).resolve().parents[1] / "src" / "core"


def _entry(content: str = "事实") -> MemoryEntry:
    return MemoryEntry(id="e1", layer="L2", content=content, tags=[], source="loop", trace_id="t")


def test_score_with_parses_model_score() -> None:
    assert score_with(lambda prompt: "0.8")(_entry()) == 0.8  # noqa: PLR2004 — 假件给定分值


def test_score_with_takes_first_number_in_prose() -> None:
    """模型常带散文输出 ⇒ 取**首个**浮点，不要求纯数值。"""
    scorer = score_with(lambda prompt: "该条目对后续任务有中等价值。分值 0.35")
    assert scorer(_entry()) == 0.35  # noqa: PLR2004 — 假件给定分值


def test_score_with_prompt_carries_entry_content() -> None:
    seen: dict[str, str] = {}

    def llm(prompt: str) -> str:
        seen["prompt"] = prompt
        return "0.5"

    score_with(llm)(_entry(content="独特标记内容"))

    assert "独特标记内容" in seen["prompt"], "评分 prompt 必须带条目正文"


def test_score_with_unparseable_output_raises() -> None:
    """无浮点 ⇒ 抛错（由闸门既有异常路径降级放行）——不静默当成 0 分而误杀。"""
    scorer = score_with(lambda prompt: "无法判断")

    with pytest.raises(ValueError, match="score"):
        scorer(_entry())


def test_score_with_out_of_range_value_is_returned_verbatim() -> None:
    """界外值**不** clamp —— 交闸门既有「界外 ⇒ 不评分」路径（越权兜底会误杀）。"""
    assert score_with(lambda prompt: "1.7")(_entry()) == 1.7  # noqa: PLR2004 — 假件给定分值


def test_score_with_unparseable_output_degrades_gate_to_normal_write() -> None:
    """工厂抛错 ⇒ 经闸门降级放行：按意向层入库 + 留痕，不牵连写入主流程。"""
    store = MemoryStore(importance_scorer=score_with(lambda prompt: "无法判断"))

    with pytest.warns(RuntimeWarning, match="scorer"):
        assert store.write("L2", _entry()) == "e1"

    assert store.audit("t")[0].importance == 0.0, "不写 importance"


def test_score_with_low_score_rejects_via_gate() -> None:
    """工厂真实接线：低分 ⇒ 闸门拒收（端到端，非替身）。"""
    store = MemoryStore(importance_scorer=score_with(lambda prompt: str(_IMPORTANCE_FLOOR - 0.1)))

    with pytest.warns(RuntimeWarning, match="importance gate"):
        assert store.write("L2", _entry()) is None


def test_importance_module_imports_no_llm_or_rag() -> None:
    """memory SHALL NOT import LLM / rag 抽象（ADR-0045 单向）——工厂只吃 ``str→str`` 调用。"""
    path = SRC / "memory" / "importance.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    dotted: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            dotted += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            dotted.append(node.module)
    offenders = [
        name
        for name in dotted
        if name.split(".")[:2] in (["core", "llm_provider"], ["core", "rag"])
    ]

    assert not offenders, f"memory 反向依赖 LLM / rag 抽象: {offenders}"


def test_importance_module_emits_no_write_side_effects() -> None:
    """打分**不**落库、不记效应 —— 纯函数式适配器（写入的闸门语义归 ``MemoryStore``）。"""
    store = MemoryStore()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        store.write("L2", _entry())

    assert caught == []
    assert len(store.audit("t")) == 1  # noqa: PLR2004 — 仅条目自身写入
