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
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import cast

from .protocol import MemoryEntry

# 单条入 prompt 的事件节选上界（token 有界；与 `summarize._MAX_ENTRY_CHARS` 同口径）
_MAX_ENTRY_CHARS = 400

# 单次压实抽取条数上界（控制单次写入量）
MAX_KEY_FACTS_PER_COMPACT = 8

# 实体名 / 取值长度上界（**先脱敏后截断**：截断不得使明文逃逸）
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


def _looks_secret(text: str) -> bool:
    """文本是否呈**密钥形态**（启发式；命中即视为不可入记忆）。"""
    return any(pattern.search(text) is not None for pattern in _SECRET_PATTERNS)


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


def scrub_key_fact(fact: KeyFact) -> KeyFact | None:
    """脱敏一条关键事实；返回 ``None`` 表示**整条丢弃**（fail-closed）。

    规则（方向恒为 over-redact）：
    1. 无实体名 ⇒ 丢弃。
    2. 像密钥的 ``ref`` 本身 ⇒ 弃用该引用（引用不可是凭据）。
    3. ``value`` 呈密钥形态**且无可用引用** ⇒ 丢弃（**记不住引用就不记**）。
    4. 有引用 ⇒ ``value`` **一律** ``REDACTED``（有引用即不留明文，即便原值看似正常）。
    5. 先脱敏（第 3/4 步）**后**截断 —— 截断不得使明文逃逸。
    """
    entity = fact.entity.strip()
    if not entity:
        return None
    ref = fact.ref.strip()
    value = fact.value.strip()
    if ref and _looks_secret(ref):
        ref = ""
    if not ref and _looks_secret(value):
        return None
    if ref:
        value = REDACTED
    return KeyFact(
        entity=entity[:_MAX_FACT_CHARS],
        value=value[:_MAX_FACT_CHARS],
        ref=ref[:_MAX_FACT_CHARS],
    )


_PROMPT_HEAD = (
    "你是关键事实抽取器。从下面的会话事件中抽取「实体 → 取值」的关键事实，最多 {max} 条。"
    '只输出一个 JSON 数组，元素形如 {{"entity": "实体名", "value": "取值", "ref": ""}}。'
    "**绝不**输出任何密钥 / 凭据 / 口令的明文：凡属此类，value 一律写 "
    '"<redacted>" 并在 ref 写 "coeffect:<名称>"；若给不出引用，就不要输出该条。'
    "不要输出解释或多余文字。"
)


def build_extract_prompt(
    entries: Sequence[MemoryEntry], *, max_facts: int = MAX_KEY_FACTS_PER_COMPACT
) -> str:
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


def extract_with(
    llm: Callable[[str], str], *, max_facts: int = MAX_KEY_FACTS_PER_COMPACT
) -> KeyFactExtractor:
    """把「prompt → 文本」的模型调用适配为 ``MemoryStore`` 的抽取契约。"""

    def _extract(entries: list[MemoryEntry]) -> list[KeyFact]:
        return parse_key_facts(llm(build_extract_prompt(entries, max_facts=max_facts)))

    return _extract
