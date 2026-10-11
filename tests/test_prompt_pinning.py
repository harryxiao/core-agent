"""提示词文本 pin（change 0215 → 扩展 0219 / ADR-0205、ADR-0209 / 台账 E152、E156）。

**规格中性**：零 `src/` 改动。本文件把 12 条核心 prompt 头的**措辞**与**渲染结构不变量**钉死
（`0215` 立 9 条；`0219` 补情景归纳 / 源码修补 / 候选审查 3 条），
拦截「措辞一改、模型行为静默变」的漂移 —— 承 `tests/test_memory.py` 的 `build_prompt` 内容锚先例。

「头」= prompt 的**身份句**（首句「你是……器。」）＋ 该条独有的**承重措辞**（JSON 形状 / 脱敏
规则 / 引用规则 / 步骤清单约束 / 块内不得混写）。逐字比较 ⇒ 任一字符改动即红。
"""

from __future__ import annotations

from core.evolution import author, validator
from core.loop import planner as loop_planner
from core.memory import episodic, extract, importance, summarize
from core.memory.protocol import MemoryEntry
from core.orchestration import planner as orch_planner
from core.skills import iteration, sop
from core.skills.feedback import SkillStats
from core.skills.models import Skill

# ── 逐字副本（pin 的本质：独立副本，src 一改即红并给出清晰 diff）──────────────────────

_EXTRACT_HEAD = (
    "你是关键事实抽取器。从下面的会话事件中抽取「实体 → 取值」的关键事实，最多 {max} 条。"
    '只输出一个 JSON 数组，元素形如 {{"entity": "实体名", "value": "取值", "ref": ""}}。'
    "**绝不**输出任何密钥 / 凭据 / 口令的明文：凡属此类，value 一律写 "
    '"<redacted>" 并在 ref 写 "coeffect:<名称>"；若给不出引用，就不要输出该条。'
    'ref **只允许**形如 "coeffect:<名称>" 的引用；给不出这样的引用时 ref 留**空字符串**，'
    "**不要**用出处说明（如「第 N 轮」「某结论」「证据链」）充数。"
    "不要输出解释或多余文字。"
)

_RELATION_HEAD = (
    "你是实体关系抽取器。从下面的会话事件中抽取「头实体 — 谓词 — 尾实体」三元组，最多 {max} 条。"
    '只输出一个 JSON 数组，元素形如 {{"head": "头实体", "predicate": "谓词", "tail": "尾实体"}}。'
    "谓词**必须**归入下表之一（可用中英任一变体，落库会归一化）：{predicates}。"
    "归不入下表的关系**不要输出**。"
    "**绝不**输出任何密钥 / 凭据 / 口令的明文（含作为实体名的情形）。不要输出解释或多余文字。"
)

_SUMMARIZE_HEAD = (
    "你是记忆压实器。把新的会话事件合并进既有摘要，保留结论、决策与未决事项；"
    "既有摘要为空则据事件首次提炼。只输出更新后的摘要，不要复述过程。"
)

_IMPORTANCE_HEAD = (
    "你是记忆重要度评分器。判断这条记忆对后续任务的价值，只输出 0 到 1 之间的一个数值"
    "（1 = 高度可复用，0 = 无价值），不要解释。"
)

_SOP_HEAD = (
    "你是 SOP 提炼器。下面是同一类任务的多次成功执行轨迹（任务 + 行动/结果序列）。"
    "请提炼为可复用的标准作业步骤：只输出编号步骤清单，不要复述轨迹、不要解释理由。"
)

_ITERATION_HEAD = (
    "你是技能迭代器。下面是某技能的现行标准作业步骤与最近的实际执行情况。"
    "请针对失败给出更稳健的改进版步骤：只输出编号步骤清单，不要复述原文、不要解释理由。"
)

_PLANNER_SYSTEM = (
    "你是 CORE-Harness 无特权核心的推理规划器，把用户任务推理为下一步动作。\n"
    '输出格式二选一：①自然语言回复；②JSON 工具调用 {"tool_id": "...", "args": {...}}。\n'
    "工具调用 JSON 须**单独成块**：不得与解释文字混写在同一段，不得用代码块围栏包裹。"
)

_DECOMPOSE_SYSTEM = (
    "你是任务拆解器。把目标拆成 2-6 个可执行的子任务 DAG，"
    '仅输出 JSON：{"subtasks": [{"id": "1", "goal": "...", '
    '"acceptance": "...", "depends_on": [], "priority": 0, "difficulty": "medium"}]}。'
    "规则：goal 是给执行智能体的单一明确指令；acceptance 是可判定的验收标准；"
    "depends_on 只引用已声明的 id，无依赖则留空数组；无依赖子任务不要伪造依赖；"
    'difficulty 是该子任务的难易度，只能取 "easy" / "medium" / "hard" 三档之一，'
    "把握不足时取 medium。"
)

_VERIFY_SYSTEM = (
    "你是验收判定器。对照验收标准判定子任务结果是否达标，"
    '仅输出 JSON：{"passed": true, "reason": "..."}。'
    "结果未提供、与标准无关或未达标准时判 false，并给出一句话理由。"
)

# ── 逐字副本（`0219` 补：情景归纳 / 源码修补 / 候选审查）────────────────────────────

_EPISODIC_HEAD = (
    "你是情景归纳器。把下面这段会话事件归纳为一段**结论快照**，四段结构依次写："
    "目标（这段会话要做什么）、经过（实际怎么做的）、结果（最终达成了什么）、"
    "教训（下次同类任务该注意什么）。只输出归纳本身，不要复述过程、不要罗列原始事件。"
)

_AUTHOR_HEAD = (
    "你是核心源码修补者。只修这一个模块，保持其现有风格与对外契约不变；"
    "只输出修补后的**完整**文件内容，不要解释、不要 diff、不要代码围栏。"
)

_REVIEW_HEAD = (
    "你是候选变更的审查者。只审这一个候选**自身是否自洽**（候选类型 / 目标模块 / 变更内容三者"
    "是否互相说得通、是否是真该由该目标承担的变更）；不评收益、不写实现。"
    "第一行以 PASS 起首表示通过，以 REJECT 起首表示不通过，其后可附一句理由。"
)


# 单条入 prompt 的正文节选上界（实为既有实现常量；此处独立持有 ⇒ src 一改即红）
_EXCERPT_BOUND = 400

_EXPECTED_PREDICATES = frozenset(
    {
        "depends_on",
        "part_of",
        "uses",
        "causes",
        "blocks",
        "owns",
        "implements",
        "related_to",
    }
)


def _entry(content: str, *, eid: str = "e1") -> MemoryEntry:
    return MemoryEntry(id=eid, layer="L2", content=content, tags=[], source="loop", trace_id="t1")


# ── 1. 逐字头（9 条）──────────────────────────────────────────────────────────────


def test_extract_head_verbatim() -> None:
    """关键事实抽取头逐字钉死（JSON 数组形状 / 密钥 `<redacted>` / `ref` 只认 `coeffect:`）。"""
    assert extract._PROMPT_HEAD == _EXTRACT_HEAD


def test_relation_head_verbatim() -> None:
    """实体关系抽取头逐字钉死（谓词必须归入闭表白名单 / 归不入不输出 / 密钥含实体名亦不透传）。"""
    assert extract._RELATION_PROMPT_HEAD == _RELATION_HEAD


def test_summarize_head_verbatim() -> None:
    """会话摘要头逐字钉死（保留结论·决策·未决 / 只输出更新后摘要）。"""
    assert summarize._PROMPT_HEAD == _SUMMARIZE_HEAD


def test_importance_head_verbatim() -> None:
    """重要度评分头逐字钉死（只输出 0–1 数值 / 不解释）。"""
    assert importance._PROMPT_HEAD == _IMPORTANCE_HEAD


def test_sop_head_verbatim() -> None:
    """SOP 提炼头逐字钉死（只输出编号步骤清单 / 不复述轨迹）。"""
    assert sop._PROMPT_HEAD == _SOP_HEAD


def test_iteration_head_verbatim() -> None:
    """技能迭代头逐字钉死（针对失败给更稳健步骤 / 不复述原文）。"""
    assert iteration._PROMPT_HEAD == _ITERATION_HEAD


def test_planner_system_prompt_verbatim() -> None:
    """主推理规划头逐字钉死（二选一格式 / 工具 JSON 单独成块 / 不得围栏包裹）。"""
    assert loop_planner._SYSTEM_PROMPT == _PLANNER_SYSTEM


def test_decompose_system_verbatim() -> None:
    """任务拆解头逐字钉死（2–6 子任务 DAG / 不伪造依赖 / difficulty 三档）。"""
    assert orch_planner._DECOMPOSE_SYSTEM == _DECOMPOSE_SYSTEM


def test_verify_system_verbatim() -> None:
    """验收判定头逐字钉死（只输出 JSON / 未达标准判 false）。"""
    assert orch_planner._VERIFY_SYSTEM == _VERIFY_SYSTEM


# ── 2. 渲染结构不变量（3 条）────────────────────────────────────────────────────


def test_builders_render_head_at_top() -> None:
    """六个 builder 的产物恒以对应 prompt 头开头（占位符 builder 取解析后的头）。"""
    entry = _entry("正文" * 5)
    skill = Skill(skill_id="s1", description="描述")
    stats = SkillStats(hits=3, ok=2, fail=1)

    assert summarize.build_prompt([entry]).startswith(summarize._PROMPT_HEAD)
    assert importance.build_score_prompt(entry).startswith(importance._PROMPT_HEAD)
    assert sop.build_sop_prompt("任务", ["步骤一"]).startswith(sop._PROMPT_HEAD)
    assert iteration.build_iterate_prompt(skill, stats).startswith(iteration._PROMPT_HEAD)
    assert extract.build_extract_prompt([entry]).startswith(
        extract._PROMPT_HEAD.format(max=extract.KEY_FACTS_MIN)
    )
    assert extract.build_relation_prompt([entry]).startswith(
        extract._RELATION_PROMPT_HEAD.format(
            max=extract.KEY_FACTS_MIN, predicates="、".join(extract._CANONICAL_PREDICATES)
        )
    )


def test_item_lines_prefixed_and_placeholders_resolved() -> None:
    """条目行 `- ` 前缀；模板占位符解析后无残留，谓词白名单**集合恒等**且全量出现。"""
    entry = _entry("正文")

    for prompt in (
        summarize.build_prompt([entry]),
        extract.build_extract_prompt([entry]),
        extract.build_relation_prompt([entry]),
        sop.build_sop_prompt("任务", ["步骤一"]),
    ):
        assert "\n- " in prompt, "条目行须以 `- ` 前缀逐条渲染"

    extract_prompt = extract.build_extract_prompt([entry], max_facts=5)
    assert "最多 5 条" in extract_prompt, "`{max}` 须解析为实参"
    assert "{max}" not in extract_prompt, "占位符不得残留"

    relation_prompt = extract.build_relation_prompt([entry])
    assert "{max}" not in relation_prompt and "{predicates}" not in relation_prompt
    assert set(extract._CANONICAL_PREDICATES) == _EXPECTED_PREDICATES, "闭合白名单集合恒等"
    for predicate in _EXPECTED_PREDICATES:
        assert predicate in relation_prompt, "闭合白名单谓词须全量出现"


def test_entry_excerpts_bounded() -> None:
    """节选上界**钉死为字面量**（400）；超长正文经任一 builder 渲染后单条节选 ≤ 该上界。"""
    assert extract._MAX_ENTRY_CHARS == _EXCERPT_BOUND
    assert importance._MAX_ENTRY_CHARS == _EXCERPT_BOUND
    assert summarize._MAX_ENTRY_CHARS == _EXCERPT_BOUND
    assert sop._MAX_STEP_CHARS == _EXCERPT_BOUND

    bound = _EXCERPT_BOUND
    huge = "长" * (bound * 10)
    extract_prompt = extract.build_extract_prompt([_entry(huge)])
    assert huge not in extract_prompt
    assert "长" * bound in extract_prompt

    summarize_prompt = summarize.build_prompt([_entry(huge)])
    assert huge not in summarize_prompt
    assert "长" * bound in summarize_prompt

    step_huge = "步" * (bound * 10)
    sop_prompt = sop.build_sop_prompt("任务", [step_huge])
    assert step_huge not in sop_prompt
    assert "步" * bound in sop_prompt


# ── 3. `0219` 补充的 3 条逐字头 ＋ 1 条结构不变量 ────────────────────────────────


def test_episodic_head_verbatim() -> None:
    """情景归纳头逐字钉死（四段结论快照：目标·经过·结果·教训 / 只输出归纳不复述）。"""
    assert episodic._PROMPT_HEAD == _EPISODIC_HEAD


def test_author_head_verbatim() -> None:
    """源码修补头逐字钉死（只修一个模块 / 保持风格与对外契约 / 只输出完整文件、不围栏）。"""
    assert author._PROMPT_HEAD == _AUTHOR_HEAD


def test_review_head_verbatim() -> None:
    """候选审查头逐字钉死（只审自身自洽 / 不评收益 / PASS·REJECT 首行判词）。"""
    assert validator._REVIEW_PROMPT_HEAD == _REVIEW_HEAD


def test_episodic_builder_renders_head_and_bounded_lines() -> None:
    """情景归纳 builder：头恒首位、条目 `- ` 行、单条节选 ≤ 上界（`_MAX_ENTRY_CHARS`）。"""
    bound = _EXCERPT_BOUND
    huge = "长" * (bound * 10)
    prompt = episodic.build_episodic_prompt([_entry(huge)])

    assert prompt.startswith(episodic._PROMPT_HEAD)
    assert "\n- " in prompt, "条目行须以 `- ` 前缀逐条渲染"
    assert huge not in prompt
    assert "长" * bound in prompt
    assert episodic._MAX_ENTRY_CHARS == _EXCERPT_BOUND
