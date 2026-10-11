"""结构化关键事实抽取（memory）。

``MemoryStore`` 的抽取契约是 ``(list[MemoryEntry]) -> list[KeyFact]``；LLM 侧是
「prompt → 文本」。本模块把后者桥接为前者 —— memory **不 import 任何 LLM / rag 抽象**
（照 ``summarize.batch_embed`` / ``summarize_with`` 先例、ADR-0045 同一依赖方向），
prompt 文本属 memory 域，生产侧由 L5 组合根注入模型调用。

**密钥红线**：本模块的 ``scrub_key_fact`` 是「**密钥只引用不读取、绝不进记忆**」的落地点 ——
脱敏在**落库前**由 memory 侧对每一条抽取结果**无条件**执行（抽取器**不构成信任边界**），
方向恒为 **over-redact**（拿不准即多脱敏），且**裸密钥无可用引用即整条丢弃**（fail-closed）。

对应接口：doc/03-interfaces/memory-interface.md §3
规格：doc/openspec/specs/memory/spec.md「结构化实体抽取（关键事实）」（change 0155 / ADR-0147）
"""

from __future__ import annotations

import json
import math
import re
import warnings
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from .protocol import MemoryEntry

# 单条入 prompt 的事件节选上界（token 有界；与 `summarize._MAX_ENTRY_CHARS` 同口径）
_MAX_ENTRY_CHARS = 400

# 单次压实抽取条数上界：随本次聚合的 episodic 条数**自适应**（change 0177 / ADR-0168）。
# `key_fact_cap(n) = clamp(ceil(n × RATIO), MIN, MAX)`；`MIN` 取既有固定上界原值 ⇒ 任何会话
# 长度下名额都不收紧（自适应只放宽）。上限/比例/下限为常量、不引入 LLM 判断。
KEY_FACTS_RATIO = 0.25
KEY_FACTS_MIN = 8
KEY_FACTS_MAX = 16

# 既有固定上界：保留公开名作**兼容别名**（语义上等于自适应下限 `KEY_FACTS_MIN`）。
MAX_KEY_FACTS_PER_COMPACT = KEY_FACTS_MIN

# 实体名 / 取值长度上界（**先脱敏后截断**：截断不得使明文逃逸；`value` 超长时**首尾保留**）
_MAX_FACT_CHARS = 200

# 脱敏字面量：引用式取值的占位
REDACTED = "<redacted>"

# 密钥形态启发式（**方向恒为 over-redact**：误伤即多脱敏，落在安全侧）。
# 覆盖：已知令牌前缀族 / 私钥块 / JWT / `key[:=]value` 赋值式 / 长随机串兜底。
_SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bsk-[A-Za-z0-9_\-]{8,}"),  # OpenAI / Anthropic 风格
    re.compile(r"\b(?:gh[pousr]|github_pat)_[A-Za-z0-9_]{16,}"),  # GitHub
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),  # AWS access key id
    re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"),  # Slack
    re.compile(r"\beyJ[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]{8,}\.[A-Za-z0-9_\-]*"),  # JWT
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),  # PEM 私钥
    re.compile(r"(?i)\b(?:api[_-]?key|secret|token|passwd|password|credential)\b\s*[:=]\s*\S{6,}"),
    re.compile(r"\b[A-Za-z0-9_\-]{32,}\b"),  # 长随机串（未知格式兜底）
)


@dataclass(frozen=True)
class KeyFact:
    """一条关键事实：实体 → 取值。

    ``ref`` 非空 ⇒ **引用式**（形如 ``coeffect:<名称>``）—— 真实取值在使用时经
    ``CoeffectResolver`` 注入，记忆里**只留名字**；此时 ``value`` 恒为 ``REDACTED``。
    """

    entity: str
    value: str = ""
    ref: str = ""


# 抽取器契约：被聚合的 episodic 条目 → 关键事实列表
KeyFactExtractor = Callable[[list[MemoryEntry]], list[KeyFact]]


def looks_like_secret(text: str) -> bool:
    """文本是否呈**密钥形态**（启发式；命中即视为不可入记忆）。

    公开判据（change 0173）：loop 侧把行动序列写入 L2 **前**复用**同一份**启发式脱敏 ——
    判据只有一处定义、两处消费（``scrub_key_fact`` / ``redact_secrets``），不写第二份。
    """
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


def redact_secrets(text: str) -> str:
    """把文本中命中密钥形态的**子串**替换为 ``REDACTED``（保留其余结构）。

    与 ``looks_like_secret`` 同源、方向同为 **over-redact**。用于**行内**脱敏：整行抹除会连
    工具名 / 路径一并丢掉，而「做了什么」正是行动序列要保留的信息（change 0173）。
    """
    cleaned = text
    for pattern in _SECRET_PATTERNS:
        cleaned = pattern.sub(REDACTED, cleaned)
    return cleaned


def _is_coeffect_ref(ref: str) -> bool:
    """``ref`` 是否呈**引用式**形态（``coeffect:<名称>``，且名称非空）。

    仅此形态算「给出引用」；其余（含模型自造的出处说明，如 `round1:…` / `会话事件`）
    一律**视为无引用**（change 0173）。
    """
    prefix = "coeffect:"
    return ref.startswith(prefix) and bool(ref[len(prefix) :].strip())


def slug_entity(entity: str, *, max_len: int = 48) -> str:
    """实体名 → ``note_id`` 式 slug（保留 ``str.isalnum()`` 含 CJK，其余折 ``-``）。

    与 ``notes.models.slug_topic`` 同一口径，但**不得**跨层 import notes（architecture 分层），
    故此处独立实现；无可保留字符时返回空串（调用方据此丢弃该条）。
    """
    chars: list[str] = []
    prev_dash = False
    for ch in entity.strip().lower():
        if ch.isalnum():
            chars.append(ch)
            prev_dash = False
        elif not prev_dash:
            chars.append("-")
            prev_dash = True
    return "".join(chars).strip("-")[:max_len].strip("-")


def key_fact_cap(aggregated: int) -> int:
    """单次压实抽取条数上界：``clamp(ceil(n × RATIO), MIN, MAX)``（change 0177 / ADR-0168）。

    ``n`` = 本次压实聚合的 episodic 条数。下限为既有固定上界原值 ⇒ 任何会话长度下名额都不收紧
    （自适应只放宽）；``n <= 0`` 亦落 ``KEY_FACTS_MIN``。
    """
    scaled = math.ceil(max(0, aggregated) * KEY_FACTS_RATIO)
    return max(KEY_FACTS_MIN, min(KEY_FACTS_MAX, scaled))


def _truncate_value(text: str) -> str:
    """取值截断：超长时**首尾保留**（头/尾各半、中以 ``…`` 连接），总长有界于 ``_MAX_FACT_CHARS``。

    只用于 ``value`` —— ``entity`` / ``ref`` 恒短（尾部无信息），维持头部截断。
    """
    if len(text) <= _MAX_FACT_CHARS:
        return text
    half = (_MAX_FACT_CHARS - 1) // 2
    return f"{text[:half]}…{text[-half:]}"


def scrub_key_fact(fact: KeyFact) -> KeyFact | None:
    """脱敏一条关键事实；返回 ``None`` 表示**整条丢弃**（fail-closed）。

    规则（方向恒为 over-redact）：
    1. 无实体名 ⇒ 丢弃。
    2. ``ref`` **非** ``coeffect:<名称>`` 形态（含像密钥者、含模型自造的出处说明）⇒ 弃用该引用
       —— 引用只认 ``coeffect:`` 形态，自造引述**不能**为明文取值背书（change 0173）。
    3. ``value`` 呈密钥形态**且无可用引用** ⇒ 丢弃（**记不住引用就不记**）。
    4. 有引用 ⇒ ``value`` **一律** ``REDACTED``（有引用即不留明文，即便原值看似正常）。
    5. 先脱敏（第 3/4 步）**后**截断 —— 截断不得使明文逃逸；``value`` 的截断形态为**首尾保留**
       （change 0172：取值常「头定名、尾定值」，只留头部会丢尾部；总长仍 ≤ ``_MAX_FACT_CHARS``）。
    """
    entity = fact.entity.strip()
    if not entity:
        return None
    ref = fact.ref.strip()
    value = fact.value.strip()
    if not _is_coeffect_ref(ref):
        ref = ""
    if not ref and looks_like_secret(value):
        return None
    if ref:
        value = REDACTED
    return KeyFact(
        entity=entity[:_MAX_FACT_CHARS],
        value=_truncate_value(value),
        ref=ref[:_MAX_FACT_CHARS],
    )


_PROMPT_HEAD = (
    "你是关键事实抽取器。从下面的会话事件中抽取「实体 → 取值」的关键事实，最多 {max} 条。"
    '只输出一个 JSON 数组，元素形如 {{"entity": "实体名", "value": "取值", "ref": ""}}。'
    "**绝不**输出任何密钥 / 凭据 / 口令的明文：凡属此类，value 一律写 "
    '"<redacted>" 并在 ref 写 "coeffect:<名称>"；若给不出引用，就不要输出该条。'
    'ref **只允许**形如 "coeffect:<名称>" 的引用；给不出这样的引用时 ref 留**空字符串**，'
    "**不要**用出处说明（如「第 N 轮」「某结论」「证据链」）充数。"
    "不要输出解释或多余文字。"
)


def build_extract_prompt(entries: Sequence[MemoryEntry], *, max_facts: int = KEY_FACTS_MIN) -> str:
    """把会话事件条目渲染为抽取 prompt（逐条节选，token 有界）。"""
    heads = [_PROMPT_HEAD.format(max=max_facts), "", "会话事件："]
    lines = [f"- {entry.content[:_MAX_ENTRY_CHARS]}" for entry in entries]
    return "\n".join([*heads, *lines])


def _json_array(text: str) -> list[object] | None:
    """从文本中截出首个 ``[`` 至末个 ``]`` 的片段并解析为 JSON 数组；失败 ⇒ ``None``。"""
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end <= start:
        return None
    try:
        payload: object = json.loads(text[start : end + 1])
    except ValueError:
        return None
    if not isinstance(payload, list):
        return None
    return cast("list[object]", payload)


def parse_key_facts(text: str) -> list[KeyFact]:
    """容错解析模型输出：只认 JSON 数组（容忍代码围栏与前后杂文）。

    **不可解析 ⇒ 空列表**（降级为不抽取，宁缺勿滥）；元素非对象 / 缺 ``entity`` 或 ``value`` /
    类型不符 ⇒ **跳过该元素**。脱敏**不在**此处做 —— 它由 store 侧对结果无条件执行。
    """
    payload = _json_array(text)
    if payload is None:
        return []
    facts: list[KeyFact] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        fields = cast("dict[object, object]", item)
        entity, value, ref = fields.get("entity"), fields.get("value"), fields.get("ref", "")
        if not isinstance(entity, str) or not isinstance(value, str):
            continue
        facts.append(KeyFact(entity=entity, value=value, ref=ref if isinstance(ref, str) else ""))
    return facts


def extract_with(llm: Callable[[str], str], *, max_facts: int = KEY_FACTS_MIN) -> KeyFactExtractor:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的抽取契约。

    **解析失败可观测**（change 0172）：模型**有输出但无可解析 JSON 数组** ⇒ 经 ``warnings.warn``
    留痕（只报失败事实与文本长度、**不含**输出正文 —— 正文可能含明文密钥）。**合法空数组**
    （``[]``，模型明确无可抽）**不**告警。``parse_key_facts`` 契约不变（不可解析仍返回 ``[]``）。
    """

    def _extract(entries: list[MemoryEntry]) -> list[KeyFact]:
        text = llm(build_extract_prompt(entries, max_facts=max_facts))
        facts = parse_key_facts(text)
        if not facts and text.strip() and _json_array(text) is None:
            warnings.warn(
                "key-fact extraction output was unparseable (no JSON array found; "
                f"{len(text)} chars); no key facts were extracted",
                RuntimeWarning,
                stacklevel=2,
            )
        return facts

    return _extract


# --------------------------------------------------------------------------------------
# 实体关系抽取（relations，change 0203 / ADR-0193 / 账本 E140）
# --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Relation:
    """一条关系三元组：头实体 — 谓词 — 尾实体。**不携带任何取值**。

    与 ``KeyFact`` 的**有意不对称**：关键事实可在「无引用 ⇒ 丢弃」与「有引用 ⇒ 抹值」之间选择；
    关系**没有取值可抹**、也没有 ``coeffect:`` 可引用之物 ⇒ 任一侧呈密钥形态时**只能整条丢弃**
    （fail-closed）。
    """

    head: str
    predicate: str
    tail: str


# 抽取器契约：被聚合的 episodic 条目 → 关系三元组列表
RelationExtractor = Callable[[list[MemoryEntry]], list[Relation]]

# 规范谓词（落库形态恒为其中之一）
_CANONICAL_PREDICATES: tuple[str, ...] = (
    "depends_on",
    "part_of",
    "uses",
    "causes",
    "blocks",
    "owns",
    "implements",
    "related_to",
)

# 谓词**闭合白名单**：变体（中 / 英）→ 规范英文谓词。若谓词开放，则「图」不可遍历、且新增一个
# **无界自由文本字段**（新的密钥携带面）、幂等去重的基数失控 ⇒ 故闭合；双语是「可用」与「有界」
# 的折中（纯中文会话的 drop 率显著下降，代价是词表维护面翻倍 —— 登记为局限）。
_PREDICATE_VARIANTS: dict[str, str] = {
    # depends_on
    "依赖": "depends_on",
    "依赖于": "depends_on",
    "取决于": "depends_on",
    "depend on": "depends_on",
    "depends on": "depends_on",
    "depends": "depends_on",
    # part_of
    "属于": "part_of",
    "包含于": "part_of",
    "组成部分": "part_of",
    "part of": "part_of",
    "belongs to": "part_of",
    # uses
    "使用": "uses",
    "采用": "uses",
    "调用": "uses",
    "use": "uses",
    "uses": "uses",
    "utilizes": "uses",
    "calls": "uses",
    # causes
    "导致": "causes",
    "造成": "causes",
    "引起": "causes",
    "引发": "causes",
    "cause": "causes",
    "causes": "causes",
    "leads to": "causes",
    # blocks
    "阻塞": "blocks",
    "阻碍": "blocks",
    "阻止": "blocks",
    "block": "blocks",
    "blocks": "blocks",
    "prevents": "blocks",
    # owns
    "拥有": "owns",
    "持有": "owns",
    "负责": "owns",
    "own": "owns",
    "owns": "owns",
    # implements
    "实现": "implements",
    "落实": "implements",
    "implement": "implements",
    "implements": "implements",
    # related_to
    "相关": "related_to",
    "有关": "related_to",
    "关联": "related_to",
    "related to": "related_to",
    "relates to": "related_to",
}

# 公开的闭合白名单：规范谓词自映射 + 全部变体
RELATION_PREDICATES: dict[str, str] = {
    **{predicate: predicate for predicate in _CANONICAL_PREDICATES},
    **_PREDICATE_VARIANTS,
}

# 谓词两端可能带的包裹引号（模型偶尔回填带引号）
_QUOTES = "\"'“”‘’「」"

# 单次压实抽取条数上界**复用关键事实的同一把旋钮**（`relation_cap is key_fact_cap`）——
# 刻意**不**另起第二组常量：全仓一把调参旋钮（change 0203 / ADR-0193）。
relation_cap = key_fact_cap


def normalize_predicate(raw: str) -> str:
    """谓词 → 规范英文谓词；不在白名单内 ⇒ 空串（调用方据此丢弃）。

    归一化：去首尾空白 → 去包裹引号 → 小写 → 内部空白折叠为单空格 → 查表。中文无大小写，
    故小写化对中文变体无害。
    """
    text = " ".join(raw.strip().strip(_QUOTES).strip().lower().split())
    return RELATION_PREDICATES.get(text, "")


def scrub_relation(relation: Relation) -> tuple[Relation | None, str]:
    """脱敏 + 归一化一条关系；返回 ``(可用关系 | None, 原因码)``。

    原因码：``""``（可用）/ ``"empty"``（空实体）/ ``"predicate"``（未知谓词）/ ``"secret"``
    （呈密钥形态）。**检查顺序即安全**：密钥判定**先于**谓词归一化 —— 否则密钥形状的**原始**
    谓词会走「未知谓词」分支、被**原样回显**进留痕。密钥形态 ⇒ **整条丢弃**（无引用逃生口）。
    """
    head = relation.head.strip()
    tail = relation.tail.strip()
    predicate = relation.predicate.strip()
    if looks_like_secret(head) or looks_like_secret(tail) or looks_like_secret(predicate):
        return None, "secret"
    if not head or not tail:
        return None, "empty"
    canonical = normalize_predicate(predicate)
    if not canonical:
        return None, "predicate"
    return (
        Relation(head=head[:_MAX_FACT_CHARS], predicate=canonical, tail=tail[:_MAX_FACT_CHARS]),
        "",
    )


_RELATION_PROMPT_HEAD = (
    "你是实体关系抽取器。从下面的会话事件中抽取「头实体 — 谓词 — 尾实体」三元组，最多 {max} 条。"
    '只输出一个 JSON 数组，元素形如 {{"head": "头实体", "predicate": "谓词", "tail": "尾实体"}}。'
    "谓词**必须**归入下表之一（可用中英任一变体，落库会归一化）：{predicates}。"
    "归不入下表的关系**不要输出**。"
    "**绝不**输出任何密钥 / 凭据 / 口令的明文（含作为实体名的情形）。不要输出解释或多余文字。"
)


def build_relation_prompt(
    entries: Sequence[MemoryEntry], *, max_relations: int = KEY_FACTS_MIN
) -> str:
    """把会话事件条目渲染为关系抽取 prompt（逐条节选，token 有界）。"""
    head = _RELATION_PROMPT_HEAD.format(
        max=max_relations, predicates="、".join(_CANONICAL_PREDICATES)
    )
    lines = [f"- {entry.content[:_MAX_ENTRY_CHARS]}" for entry in entries]
    return "\n".join([head, "", "会话事件：", *lines])


def parse_relations(text: str) -> list[Relation]:
    """容错解析模型输出：只认 JSON 数组（容忍代码围栏与前后杂文）。

    **不可解析 ⇒ 空列表**；元素非对象 / 缺任一字段 / 类型不符 ⇒ **跳过该元素**。脱敏与归一化
    **不在**此处做 —— 由 store 侧对结果无条件执行（``scrub_relation``）。
    """
    payload = _json_array(text)
    if payload is None:
        return []
    relations: list[Relation] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        fields = cast("dict[object, object]", item)
        head, predicate, tail = fields.get("head"), fields.get("predicate"), fields.get("tail")
        if not isinstance(head, str) or not isinstance(predicate, str) or not isinstance(tail, str):
            continue
        relations.append(Relation(head=head, predicate=predicate, tail=tail))
    return relations


def extract_relations_with(
    llm: Callable[[str], str], *, max_relations: int = KEY_FACTS_MIN
) -> RelationExtractor:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的关系抽取契约。

    **解析失败可观测**（同 ``extract_with``）：有输出但无可解析 JSON 数组 ⇒ ``warnings.warn``
    留痕（只报文本长度、**不含**输出正文）。合法空数组不告警。
    """

    def _extract(entries: list[MemoryEntry]) -> list[Relation]:
        text = llm(build_relation_prompt(entries, max_relations=max_relations))
        relations = parse_relations(text)
        if not relations and text.strip() and _json_array(text) is None:
            warnings.warn(
                "relation extraction output was unparseable (no JSON array found; "
                f"{len(text)} chars); no relations were extracted",
                RuntimeWarning,
                stacklevel=2,
            )
        return relations

    return _extract
