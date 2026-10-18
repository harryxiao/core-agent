"""CLI 运维动词盘点守卫（change 0288 / ADR-0278 / 台账 E100）。

`cli_ops/dispatcher.py` 的六组动词是**接口层清单**；argparse 顶层子命令才是**用户可达面**。
E100 的定义就是两者之差。本组用例把差集钉在 `cli-ops-interface.md` 的唯一一行
「未注册动词（守卫）」上：今后注册或新增动词而忘记同步文档即转红。
"""

from __future__ import annotations

import re
from pathlib import Path

from core.cli_ops import dispatcher
from core.entry import _build_parser

_DOC = Path(__file__).resolve().parents[1] / "doc/03-interfaces/cli-ops-interface.md"
_MARKER = "未注册动词（守卫）"
_VERB = re.compile(r"`([a-z][a-z-]*)`")
_COUNT = re.compile(r"共 \*\*(\d+)\*\* 个")


def _top_level_commands() -> set[str]:
    parser = _build_parser()
    return set(parser._subparsers._group_actions[0].choices)  # type: ignore[union-attr]


def _dispatcher_verbs() -> set[str]:
    """按 `_group_of` 的语义取顶层动词：`mcp` 是命令，`add/remove/list` 是其子动作。"""
    return (
        set(dispatcher._LIFECYCLE)
        | set(dispatcher._STATUS)
        | set(dispatcher._ASSET)
        | set(dispatcher._SECURITY)
        | {"mcp", "gateway"}
    )


def _actual_unregistered() -> set[str]:
    return _dispatcher_verbs() - _top_level_commands()


def _declared_line() -> str:
    matches = [line for line in _DOC.read_text("utf-8").splitlines() if _MARKER in line]
    assert matches, _MARKER
    return matches[0]


def test_documented_unregistered_verbs_match_code() -> None:
    documented = set(_VERB.findall(_declared_line().split("——", 1)[0]))
    assert documented == _actual_unregistered()


def test_documented_count_matches_code() -> None:
    match = _COUNT.search(_declared_line())
    assert match is not None
    assert int(match.group(1)) == len(_actual_unregistered())
