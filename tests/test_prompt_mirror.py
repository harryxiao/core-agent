"""镜像一致性门禁（PA-05 / change 0220）：`prompts.md` 的每条 prompt 正文须与模块常量一致。

`doc/03-interfaces/prompts.md` 自称「全仓内置 prompt 的现状快照（镜像）」，其 §7 定的纪律是
**改三处**：模块常量 → `tests/test_prompt_pinning.py` 逐字副本 → 本表镜像。前两处由
`test_prompt_pinning.py` 钉住，**第三处（镜像）此前无任何自动校验**，全靠人肉 —— 漏改即镜像
失真、评审依据错误。本文件补这道闸：逐条取模块常量，断言其**每一非空行**都出现在镜像里。

镜像记录的是**模型看到的（渲染后）形态**，故先去掉 `.format()` 的转义（⑤⑥ 的 `{{`→`{`）；
模板占位符（`{max}` / `{predicates}` / `{text}`）在镜像里**保留原形**，可直接子串匹配。
⑬ 人格面为**动态拼接**（无固定常量）⇒ 不逐字核对，但须在镜像总表**登记**（缺口可见）。

change `0225` 补两节（此前只核「常量的行」⇒ **行号与旁注结构性不受保护**）：
§1 落点列的 `文件:行` 核对（14 行参数化）＋ 旁注**已知加固点锚**。
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from core.entry import _DOC_SUMMARY_PROMPT
from core.evolution import author, validator
from core.loop import planner as loop_planner
from core.memory import episodic, extract, importance, summarize
from core.orchestration import planner as orch_planner
from core.skills import iteration, sop

_MIRROR_ROOT = Path(__file__).resolve().parents[1]
_MIRROR = _MIRROR_ROOT / "doc" / "03-interfaces" / "prompts.md"

# 序号 → 承载该 prompt 文本的**模块常量**（⑬ 人格面动态拼接 ⇒ 不在内）。
# ⑭ 虽是内联 `format` 注入，但其模板为常量、镜像保留 `{text}` ⇒ 同样可逐行核对。
_PROMPT_CONSTANTS: dict[str, str] = {
    "①": loop_planner._SYSTEM_PROMPT,
    "②": orch_planner._DECOMPOSE_SYSTEM,
    "③": orch_planner._VERIFY_SYSTEM,
    "④": summarize._PROMPT_HEAD,
    "⑤": extract._PROMPT_HEAD,
    "⑥": extract._RELATION_PROMPT_HEAD,
    "⑦": importance._PROMPT_HEAD,
    "⑧": episodic._PROMPT_HEAD,
    "⑨": sop._PROMPT_HEAD,
    "⑩": iteration._PROMPT_HEAD,
    "⑪": author._PROMPT_HEAD,
    "⑫": validator._REVIEW_PROMPT_HEAD,
    "⑭": _DOC_SUMMARY_PROMPT,
}


@pytest.mark.parametrize(("label", "text"), sorted(_PROMPT_CONSTANTS.items()))
def test_prompt_mirror_matches_constant_line_by_line(label: str, text: str) -> None:
    """镜像须含该 prompt 常量的**每一非空行**（漏改 `prompts.md` ⇒ 红，直指缺哪一行）。

    仅当常量用 `.format()` 转义（含 `{{`，即 ⑤⑥）时去转义 —— ① 的 `{"args": {...}}` 是**字面**
    的双 `}`，镜像亦然，一律去转义会误伤它。
    """
    mirror = _MIRROR.read_text(encoding="utf-8")
    rendered = text.replace("{{", "{").replace("}}", "}") if "{{" in text else text
    missing = [line for line in rendered.splitlines() if line.strip() and line not in mirror]
    assert missing == [], f"{label} 正文与 prompts.md 不一致（漏改镜像）：{missing}"


def test_mirror_registers_persona_and_doc_summary() -> None:
    """⑬（动态拼接）与 ⑭（内联注入）无逐字锚，但**须**在镜像总表登记（否则缺口不可见）。"""
    mirror = _MIRROR.read_text(encoding="utf-8")
    assert "⑬ 宠物人格" in mirror
    assert "⑭ 文档摘要器" in mirror


# ── §1 落点列行号核对（change `0225`）─────────────────────────────────────────────
#
# 文本门禁（上方）只断言「常量的行出现在镜像」，**看不见 §1 落点列的 `文件:行`** ——
# 常量**上方**插入/删除行会让该列无声漂移（`0222` / `0223` 各漂过一次，`0225` 之前共 4 条失准）。
# 本节把该列也钉住：所列行**必须**含所列符号。

_LANDING_ROW = re.compile(
    r"^\|\s*(?P<no>[①-⑭])\s*\|[^|]*\|[^|]*\|\s*"
    r"`(?P<path>[^`]+):(?P<line>\d+)`\s*`(?P<sym>[^`]+)`"
)


def _landing_rows() -> list[tuple[str, str, int, str]]:
    """解析 §1 总表 ⇒ ``(序号, 相对 src/core/ 的路径, 行号, 符号)``（按镜像出现序）。"""
    rows: list[tuple[str, str, int, str]] = []
    for raw in _MIRROR.read_text(encoding="utf-8").splitlines():
        match = _LANDING_ROW.match(raw)
        if match:
            rows.append(
                (
                    match.group("no"),
                    match.group("path"),
                    int(match.group("line")),
                    match.group("sym"),
                )
            )
    return rows


_LANDING_ROWS = _landing_rows()


def test_mirror_landing_column_covers_all_rows() -> None:
    """§1 落点列须覆盖 ①~⑭（顺序一致）—— 漏一行即行号失守而不自知。"""
    assert [row[0] for row in _LANDING_ROWS] == list("①②③④⑤⑥⑦⑧⑨⑩⑪⑫⑬⑭")


@pytest.mark.parametrize(
    ("rel", "lineno", "symbol"),
    [row[1:] for row in _LANDING_ROWS],
    ids=[row[0] for row in _LANDING_ROWS],
)
def test_mirror_landing_line_points_at_symbol(rel: str, lineno: int, symbol: str) -> None:
    """§1 落点列的 ``文件:行`` **须**指向所列符号（常量上方增删行会使其漂移）。"""
    target = _MIRROR_ROOT / "src" / "core" / rel
    assert target.exists(), f"落点文件不存在：src/core/{rel}"

    lines = target.read_text(encoding="utf-8").splitlines()
    assert lineno <= len(lines), f"src/core/{rel}:{lineno} 越界（共 {len(lines)} 行）"

    # 落点列的符号可能带调用括号（如 ⑬ 的 `render_prompt()`），而目标行是定义行
    # （`def render_prompt(self) -> str:`）⇒ 比对时去掉尾随 `()`。
    needle = symbol.removesuffix("()")
    text = lines[lineno - 1]
    assert needle in text, (
        f"src/core/{rel}:{lineno} 不含 {symbol!r}（落点列行号已漂移）：{text.strip()!r}"
    )


# ── 旁注已知加固点锚（change `0225`）──────────────────────────────────────────────
#
# 镜像的**解释性旁注**（动态内置内容 / 解析侧旁注）不是模块常量 ⇒ 不受文本门禁保护。
# 本节只钉**已知加固点**是否被旁注记到 —— 新增加固点须**手工**往下表加一行（已知局限：
# 改旁注而不动常量时本测试不会红，旁注无真源可核。见 ADR-0215 局限②）。

_NOTE_ANCHORS = {
    "0220 strip_fence 末块兜底": "_FENCE_ANY",
    "0222 形态 5 可见失败": "形态 5",
    "0223 失败实况注入": "failure_steps",
}


@pytest.mark.parametrize(("label", "anchor"), sorted(_NOTE_ANCHORS.items()))
def test_mirror_notes_carry_known_hardening_anchors(label: str, anchor: str) -> None:
    """镜像旁注须记到已知加固点 —— 防「把已闭的缺口写成仍开」这类失真。"""
    mirror = _MIRROR.read_text(encoding="utf-8")
    assert anchor in mirror, f"{label}：镜像旁注未记加固点 {anchor!r}"
