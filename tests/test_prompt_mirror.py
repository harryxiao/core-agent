"""镜像一致性门禁（PA-05 / change 0220）：`prompts.md` 的每条 prompt 正文须与模块常量一致。

`doc/03-interfaces/prompts.md` 自称「全仓内置 prompt 的现状快照（镜像）」，其 §7 定的纪律是
**改三处**：模块常量 → `tests/test_prompt_pinning.py` 逐字副本 → 本表镜像。前两处由
`test_prompt_pinning.py` 钉住，**第三处（镜像）此前无任何自动校验**，全靠人肉 —— 漏改即镜像
失真、评审依据错误。本文件补这道闸：逐条取模块常量，断言其**每一非空行**都出现在镜像里。

镜像记录的是**模型看到的（渲染后）形态**，故先去掉 `.format()` 的转义（⑤⑥ 的 `{{`→`{`）；
模板占位符（`{max}` / `{predicates}` / `{text}`）在镜像里**保留原形**，可直接子串匹配。
⑬ 人格面为**动态拼接**（无固定常量）⇒ 不逐字核对，但须在镜像总表**登记**（缺口可见）。
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core.entry import _DOC_SUMMARY_PROMPT
from core.evolution import author, validator
from core.loop import planner as loop_planner
from core.memory import episodic, extract, importance, summarize
from core.orchestration import planner as orch_planner
from core.skills import iteration, sop

_MIRROR = Path(__file__).resolve().parents[1] / "doc" / "03-interfaces" / "prompts.md"

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
