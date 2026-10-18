"""coding-plan 索引守卫（change 0287 / ADR-0277 / 台账 E223）。

PA-11：README 自述「36 份 / phase-0~34」，实际已有 `phase-41.md`；走查因此漏掉最相关的两册。
本文件把「计数、最大编号、§1 索引覆盖」钉成断言 —— 新增 Phase 未补索引即转红。
PA-12：`phase-38.md` §0 批内缺口曾与「记忆三面路线图」共用 `G1`/`G2`；改用 `B38-*` 并注明非同组。

只判结构，不判描述内容是否过时（同 `test_arbitration_ledger.py` 的纪律）。
"""

from __future__ import annotations

import re
from pathlib import Path

_PLAN = Path(__file__).resolve().parents[1] / "coding-plan"
_README = _PLAN / "README.md"
_PHASE38 = _PLAN / "phase-38.md"

#: 本地未跟踪、按约定不提交的两份（用户工作区专有；不计入仓库索引守卫）。
_LOCAL_ONLY = frozenset({"phase-32.md", "phase-3-prompt.md"})

_MAIN_PHASE = re.compile(r"^phase-\d+(?:\.\d+)?\.md$")
_COUNT_LINE = re.compile(
    r"`phase-\*\.md` 共 \*\*(\d+)\*\* 份（主文档 (\d+) ＋ 配套记录 (\d+)），最大 `(phase-\d+\.md)`"
)
_SECTION1 = re.compile(r"^## 1\..*?(?=^## 2\.)", re.MULTILINE | re.DOTALL)
_INDEX_ROW = re.compile(r"^\| `(phase-\d+(?:\.\d+)?\.md)`", re.MULTILINE)
_VERSION = re.compile(r"phase-(\d+(?:\.\d+)?)")


def _phase_files() -> list[Path]:
    return sorted(path for path in _PLAN.glob("phase-*.md") if path.name not in _LOCAL_ONLY)


def _main_phase_files() -> list[Path]:
    return [path for path in _phase_files() if _MAIN_PHASE.match(path.name)]


def _version_key(path: Path) -> tuple[int, ...]:
    match = _VERSION.match(path.stem)
    assert match, f"无法解析 Phase 编号：{path.name}"
    return tuple(int(part) for part in match.group(1).split("."))


def test_readme_declared_count_and_max_match_files() -> None:
    """README 声明的份数与最大编号必须等于实际 `phase-*.md`。"""
    match = _COUNT_LINE.search(_README.read_text(encoding="utf-8"))
    assert match, "README 缺「索引计数（守卫）」行或句式已变"
    declared_total, declared_main, declared_aux, declared_max = match.groups()
    files = _phase_files()
    main = _main_phase_files()
    assert int(declared_total) == len(files)
    assert int(declared_main) == len(main)
    assert int(declared_aux) == len(files) - len(main)
    assert declared_max == max(main, key=_version_key).name


def test_section1_index_covers_every_main_phase_doc() -> None:
    """§1 索引表必须逐行覆盖全部主文档（`phase-N[.N].md`）。"""
    section = _SECTION1.search(_README.read_text(encoding="utf-8"))
    assert section, "README 缺 §1 文档清单"
    listed = set(_INDEX_ROW.findall(section.group(0)))
    expected = {path.name for path in _main_phase_files()}
    assert listed == expected, (
        f"§1 索引差集：缺 {sorted(expected - listed)} / 多 {sorted(listed - expected)}"
    )


def test_phase38_batch_gaps_do_not_reuse_roadmap_labels() -> None:
    """`phase-38.md` §0 批内缺口用 `B38-*`，且注明与路线图 G1~G5 非同组。"""
    text = _PHASE38.read_text(encoding="utf-8")
    section = text.split("## §0", 1)[1].split("## §1", 1)[0]
    for label in ("B38-1", "B38-2", "B38-3"):
        assert label in section, f"§0 缺批内编号 {label}"
    assert "非同组" in section, "§0 缺「与记忆三面路线图 G1~G5 非同组」注记"
    assert "**G1" not in section and "**G2" not in section, "§0 仍有裸 G1/G2 批内标签"
