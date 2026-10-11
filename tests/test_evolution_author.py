"""补丁生产者接缝 `patch_author_with` 与**归因→源码文件**约定（change 0112）。

约定：内部核心模块 id `a.b` ⇒ `src/core/a/b.py`（14 个 id 一手核实全部命中）。约定若漂移
（改个文件名），执行器就会指向不存在的路径 ⇒ 本文件用**派生不变量**钉住它，不靠人工维护映射表。
补丁生产者的模型调用**注入**（组合根给 `_llm_text`），故此处全部假件、不出网。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.evolution import INTERNAL_PLUGIN_IDS, GenerationCandidate
from core.evolution.author import patch_author_with, strip_fence
from core.evolution.plugin_ids import module_path

_REPO_ROOT = Path(__file__).resolve().parents[1]


def test_module_path_convention() -> None:
    """点转斜杠 + `.py`，前缀 `src/core/`。"""
    assert module_path("loop.default") == "src/core/loop/default.py"
    assert module_path("evolution.worker") == "src/core/evolution/worker.py"


def test_every_internal_plugin_id_resolves_to_a_real_file() -> None:
    """派生不变量：全部归因白名单 id 都命中真实文件（约定漂移即红，不必人工维护映射表）。"""
    missing = [
        pid for pid in sorted(INTERNAL_PLUGIN_IDS) if not (_REPO_ROOT / module_path(pid)).is_file()
    ]
    assert missing == []


def _candidate(target: str = "loop.default") -> GenerationCandidate:
    return GenerationCandidate(
        generation=1,
        target_plugin=target,
        delta={"issue": "收尾缺少记忆固化"},
        kind="plugin",
        status="confirmed",
        risk_level="high",
    )


def test_author_targets_the_attributed_module_and_feeds_it_to_the_model() -> None:
    """路径由**归因**得出（不问模型）；提示词含目标模块、问题与原源码。"""
    prompts: list[str] = []

    def _llm(prompt: str) -> str:
        prompts.append(prompt)
        return "def run() -> None:\n    return 1\n"

    author = patch_author_with(_llm, read_source=lambda _: "def run() -> None:\n    return 0\n")
    proposal = author(_candidate())

    assert proposal.path == "src/core/loop/default.py"
    assert proposal.content == "def run() -> None:\n    return 1\n"
    assert len(prompts) == 1
    assert "loop.default" in prompts[0]
    assert "收尾缺少记忆固化" in prompts[0]
    assert "return 0" in prompts[0], "原源码须进提示词（模型才能改它）"


def test_author_strips_markdown_fence() -> None:
    """模型爱裹代码围栏：围栏须剥掉，不得把 ``` 写进源码文件。"""
    author = patch_author_with(
        lambda _: "```python\ndef run() -> None:\n    return 1\n```\n",
        read_source=lambda _: "def run() -> None:\n    return 0\n",
    )

    assert author(_candidate()).content == "def run() -> None:\n    return 1\n"


def test_author_handles_absent_source() -> None:
    """读到不存在（`None`）时不炸：按空源码成提示词；是否可行由执行器的守卫判。"""
    prompts: list[str] = []

    def _llm(prompt: str) -> str:
        prompts.append(prompt)
        return "# 新模块\n"

    author = patch_author_with(_llm, read_source=lambda _: None)

    assert author(_candidate("notes.store")).path == "src/core/notes/store.py"
    assert "notes.store" in prompts[0]


@pytest.mark.parametrize("pid", sorted(INTERNAL_PLUGIN_IDS))
def test_module_path_is_stable_for_all_ids(pid: str) -> None:
    """逐个 id 的参数化版本（失败时直接点名是哪个 id 的约定断了）。"""
    assert module_path(pid).startswith("src/core/")
    assert module_path(pid).endswith(".py")


def test_strip_fence_returns_text_when_no_fence() -> None:
    """无围栏 ⇒ 原样返回（不擅自改写模型输出 —— 既有语义，须保持）。"""
    assert strip_fence("def run() -> None:\n    return 1\n") == "def run() -> None:\n    return 1\n"


def test_strip_fence_takes_last_block_when_prose_precedes() -> None:
    """「说明 + 围栏」形态：整体匹配失败时取**最后一个**围栏块，说明文字不得写进源码。"""
    text = "这是修补后的文件：\n\n```python\ndef run() -> None:\n    return 1\n```\n"
    assert strip_fence(text) == "def run() -> None:\n    return 1\n"


def test_strip_fence_takes_last_block_among_several() -> None:
    """说明 + 多块 ⇒ 取**末**块（与「只认尾部」同型：末块即模型最终给出的内容）。

    注意整串若**以围栏起首**则由 `_FENCE` 接管（锚定匹配，跨到末个围栏）—— 本兜底只在
    串首不是围栏时生效，故此处让说明文字打头。
    """
    text = "先说明\n```\n旧的\n```\n再补一句\n```\n新的\n```\n"
    assert strip_fence(text) == "新的\n"


def test_author_strips_fence_with_leading_prose() -> None:
    """接缝级反证：模型「先说一句 + 再给围栏」时，产物是纯源码（不含说明文字）。"""
    author = patch_author_with(
        lambda _: "这是修补后的文件：\n\n```python\ndef run() -> None:\n    return 1\n```\n",
        read_source=lambda _: "def run() -> None:\n    return 0\n",
    )

    assert author(_candidate()).content == "def run() -> None:\n    return 1\n"
