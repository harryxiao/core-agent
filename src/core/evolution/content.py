"""技能候选内容生成（evolution）。

把诊断 ``issue`` / 有界 ``failure_notes`` 蒸馏为可执行 ``SkillContent``。生成走 DI 接缝
（``skill_content_writer_with``：prompt → SkillContent|None），**evolution 不 import 任何
LLM 抽象**（照 ``skills.sop_writer_with`` / ``author.patch_author_with`` 先例）。

对应规格：evolution/spec.md「技能候选内容生成」｜ change 0236
"""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, cast

# 与 diagnoser 同口径字面量（本模块自持，不 import diagnoser）
_MAX_FAILURE_NOTES = 3
_MAX_NOTE_CHARS = 400

_PROMPT_HEAD = (
    "你是技能内容蒸馏器。根据缺陷描述与失败摘要，产出一条可执行技能内容。"
    "只输出一个 JSON 对象，不要解释、不要代码围栏。字段："
    "task_types（非空字符串数组）、instructions（非空字符串）、"
    "param_schema（对象，可为 {}）、preconditions（可选字符串数组）、"
    "description（可选字符串）。"
)

SkillContentWriter = Callable[[str], "SkillContent | None"]


@dataclass
class SkillContent:
    """技能候选可执行内容（提案写入 delta['content'] 的结构化形态）。"""

    task_types: list[str]
    instructions: str
    param_schema: dict[str, Any]
    preconditions: list[str] = field(default_factory=list[str])
    description: str = ""


def validate_skill_content(content: SkillContent | Mapping[str, Any] | None) -> bool:
    """内容是否有效：接受 dataclass 或 delta 内 asdict 形态；无效 ⇒ False。"""
    hydrated = _hydrate(content)
    if hydrated is None:
        return False
    if not hydrated.task_types:
        return False
    if not hydrated.instructions.strip():
        return False
    # param_schema 在 hydrate 时已要求为 dict；此处再钉一次承四态契约
    return type(hydrated.param_schema) is dict


def build_skill_content_prompt(issue: str, failure_notes: Sequence[str] | None = None) -> str:
    """渲染蒸馏 prompt；failure_notes 条数与单条字符有界。"""
    notes = list(failure_notes or [])[:_MAX_FAILURE_NOTES]
    clipped = [note[:_MAX_NOTE_CHARS] for note in notes]
    blocks = [f"- {note}" for note in clipped] if clipped else ["- （无）"]
    return "\n".join(
        [
            _PROMPT_HEAD,
            "",
            f"缺陷：{issue}",
            "",
            "失败摘要：",
            *blocks,
        ]
    )


def skill_content_writer_with(llm: Callable[[str], str]) -> SkillContentWriter:
    """工厂：把 prompt→文本 适配为 prompt→SkillContent|None（非法/异常 ⇒ None，不抛）。"""

    def _write(prompt: str) -> SkillContent | None:
        try:
            raw = llm(prompt)
            data = json.loads(raw)
            if not isinstance(data, dict):
                return None
            content = _from_mapping(cast("dict[str, Any]", data))
            if content is None or not validate_skill_content(content):
                return None
        except Exception:  # noqa: BLE001 — 模型/解析故障 ⇒ 无内容（fail-closed）
            return None
        else:
            return content

    return _write


def _hydrate(content: SkillContent | Mapping[str, Any] | None) -> SkillContent | None:
    if content is None:
        return None
    if isinstance(content, SkillContent):
        return content
    return _from_mapping(content)


def _from_mapping(data: Mapping[str, Any]) -> SkillContent | None:
    try:
        task_types_raw = data.get("task_types")
        instructions = data.get("instructions")
        param_schema_raw = data.get("param_schema")
        if not isinstance(task_types_raw, list) or not isinstance(instructions, str):
            return None
        if not isinstance(param_schema_raw, dict):
            return None
        preconditions_raw = data.get("preconditions", [])
        description = data.get("description", "")
        if not isinstance(preconditions_raw, list) or not isinstance(description, str):
            return None
        task_types = cast("list[Any]", task_types_raw)
        preconditions = cast("list[Any]", preconditions_raw)
        param_schema = cast("dict[str, Any]", param_schema_raw)
        return SkillContent(
            task_types=[str(t) for t in task_types],
            instructions=instructions,
            param_schema=dict(param_schema),
            preconditions=[str(p) for p in preconditions],
            description=description,
        )
    except (TypeError, ValueError):
        return None
