"""SOP 提炼质量门与 draft 发布（change 0295）。

对应规格：doc/openspec/specs/skills/spec.md（SOP 提炼、技能状态运维）
"""

from __future__ import annotations

import pytest

from core.entry import _state_path, main
from core.skills import Skill, SkillLibrary, SkillRouter, SopExtractor, build_sop_prompt

_TASK = "release process document"
_GOOD = "## 适用场景\n发布流程\n\n## 步骤\n1. 运行 pytest\n2. 打 tag\n\n## 验证\npytest 全绿"


def _trace(i: int = 0) -> list[str]:
    return [f"tools.file_write（path=f{i}.py）→ ok", "tools.code_run（script=pytest）→ 全绿"]


def _writer(text: str = _GOOD, calls: list[str] | None = None):
    def _write(prompt: str) -> str:
        if calls is not None:
            calls.append(prompt)
        return text

    return _write


def _extractor(
    lib: SkillLibrary | None = None,
    *,
    text: str = _GOOD,
    threshold: int = 3,
    namespace: str = "",
    calls: list[str] | None = None,
) -> tuple[SopExtractor, SkillLibrary]:
    library = lib if lib is not None else SkillLibrary()
    return (
        SopExtractor(
            library,
            writer=_writer(text, calls),
            threshold=threshold,
            namespace=namespace,
        ),
        library,
    )


def test_publish_is_draft_and_not_routable() -> None:
    extractor, lib = _extractor()
    skill = None
    for i in range(3):
        skill = extractor.observe(_TASK, _trace(i))
    assert skill is not None
    assert skill.status == "draft", "SOP 一律先 draft"
    assert lib.lookup(skill.skill_id).status == "draft"
    assert SkillRouter(lib).match(_TASK) == [], "draft 不进路由"

    lib.activate(skill.skill_id)
    matches = SkillRouter(lib).match(_TASK)
    assert matches and matches[0].skill.skill_id == skill.skill_id


@pytest.mark.parametrize("task", ["继续", "hi", "完成了吗", "ok"])
def test_short_task_never_sampled(task: str) -> None:
    calls: list[str] = []
    extractor, lib = _extractor(calls=calls)
    for i in range(5):
        assert extractor.observe(task, _trace(i)) is None
    assert calls == []
    assert lib.all_skills() == []


def test_empty_steps_never_sampled() -> None:
    calls: list[str] = []
    extractor, lib = _extractor(calls=calls)
    for _ in range(5):
        assert extractor.observe(_TASK, []) is None
    assert calls == []
    assert lib.all_skills() == []


def test_no_tool_action_never_sampled() -> None:
    calls: list[str] = []
    extractor, lib = _extractor(calls=calls)
    chat = ['assistant: {"tool_id": "tools.echo"}', "tool: 你好"]
    for _ in range(5):
        assert extractor.observe(_TASK, chat) is None
    assert calls == []
    assert lib.all_skills() == []


def test_duplicate_trace_does_not_inflate_samples() -> None:
    calls: list[str] = []
    extractor, lib = _extractor(calls=calls)
    for _ in range(5):
        assert extractor.observe(_TASK, _trace(0)) is None
    assert calls == [], "同一轨迹重复提交不得达阈值"
    assert lib.all_skills() == []


def test_task_namespace_accepts_skeleton_steps() -> None:
    extractor, lib = _extractor(namespace="task")
    steps = ["子任务 一：写代码", "子任务 二：跑测试"]
    for _ in range(3):
        extractor.observe(_TASK, steps)
    skills = lib.all_skills()
    assert len(skills) == 1
    assert skills[0].status == "draft"


def test_refusal_text_is_rejected() -> None:
    refusal = "未提供有效的执行轨迹（轨迹为空），且任务描述仅为 hi，无法提炼出标准作业步骤。"
    extractor, lib = _extractor(text=refusal)
    for i in range(3):
        assert extractor.observe(_TASK, _trace(i)) is None
    assert lib.all_skills() == []


def test_existing_active_skill_not_overwritten() -> None:
    extractor, lib = _extractor()
    skill: Skill | None = None
    for i in range(3):
        skill = extractor.observe(_TASK, _trace(i))
    assert skill is not None
    lib.activate(skill.skill_id)
    original = skill.instructions

    extractor2, _ = _extractor(lib, text="## 步骤\n1. 完全不同\n2. 的步骤")
    for i in range(3, 6):
        extractor2.observe(_TASK, _trace(i))
    loaded = lib.lookup(skill.skill_id)
    assert loaded.status == "active"
    assert loaded.instructions == original, "已发布技能不被重抽覆盖"


def test_existing_deprecated_skill_not_resurrected() -> None:
    extractor, lib = _extractor()
    skill: Skill | None = None
    for i in range(3):
        skill = extractor.observe(_TASK, _trace(i))
    assert skill is not None
    lib.deprecate(skill.skill_id)

    extractor2, _ = _extractor(lib)
    for i in range(3, 6):
        extractor2.observe(_TASK, _trace(i))
    assert lib.lookup(skill.skill_id).status == "deprecated"


def test_prompt_requests_structured_sections() -> None:
    prompt = build_sop_prompt("发布流程", [["tools.file_write（path=a）→ ok"]])
    assert "## 步骤" in prompt
    assert "## 验证" in prompt
    assert "任务：发布流程" in prompt


def test_cli_skill_list_and_deprecate(capsys: pytest.CaptureFixture[str]) -> None:
    lib = SkillLibrary(path=_state_path("skills.json"))
    lib.register(Skill(skill_id="skills.demo.draft", description="演示", status="draft"))

    assert main(["skill", "list", "--status", "draft"]) == 0
    out = capsys.readouterr().out
    assert "skills.demo.draft" in out and "draft" in out

    assert main(["skill", "deprecate", "skills.demo.draft"]) == 0
    assert SkillLibrary(path=_state_path("skills.json")).lookup("skills.demo.draft").status == (
        "deprecated"
    )
    assert main(["skill", "deprecate", "skills.unknown"]) == 1
