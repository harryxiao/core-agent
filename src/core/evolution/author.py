"""补丁生产者适配器（evolution）。

``EvolutionExecutor`` 的 ``author`` 契约是「候选 → 一份单文件补丁」；LLM 侧是「prompt → 文本」。
本模块把后者桥接为前者 —— evolution **不 import 任何 LLM 抽象**（照 ``memory.summarize_with`` /
``skills.sop_writer_with`` 先例、ADR-0045 同一依赖方向），prompt 文本属 evolution 域，模型调用
由组合根注入。

**路径不问模型**：目标文件路径由候选的**归因目标**（`target_plugin`）经约定解析得出
（``plugin_ids.module_path``）。模型只产出内容 —— 路径若由模型自报，「路径与归因一致」这一关
就无从校验（模型可以指着别人的文件说「我改的是它」）。
"""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Protocol

from .models import GenerationCandidate, PatchProposal
from .plugin_ids import module_path

#: 读目标模块当前源码（仓内相对路径）；不存在 / 不可读 ⇒ ``None``（可行性由执行器的守卫判）
SourceReader = Callable[[str], str | None]


class PatchAuthor(Protocol):
    """补丁生产者契约（执行器视角）：候选 ⇒ 单文件补丁（路径按归因定，内容由模型产）。"""

    def __call__(self, candidate: GenerationCandidate) -> PatchProposal: ...


_PROMPT_HEAD = (
    "你是核心源码修补者。只修这一个模块，保持其现有风格与对外契约不变；"
    "只输出修补后的**完整**文件内容，不要解释、不要 diff、不要代码围栏。"
)

# 模型爱把整份源码裹进 ```python 围栏：围栏必须剥掉，否则会被原样写进源码文件。
_FENCE = re.compile(r"^```[^\n]*\n(?P<body>.*?)\n?```\s*$", re.DOTALL)


def build_prompt(candidate: GenerationCandidate, source: str | None) -> str:
    """把归因目标、问题与原源码渲染为修补 prompt（原源码给全 —— 模型要改的就是它）。"""
    return "\n".join(
        [
            _PROMPT_HEAD,
            "",
            f"目标模块：{candidate.target_plugin}",
            f"问题：{candidate.delta.get('issue', '')}",
            "",
            "当前内容：",
            source if source is not None else "（该模块当前不存在：按需新建）",
        ]
    )


def strip_fence(text: str) -> str:
    """剥掉 Markdown 代码围栏（无围栏则原样返回，不擅自改写模型输出）。"""
    match = _FENCE.match(text.strip())
    return f"{match.group('body').rstrip()}\n" if match else text


def patch_author_with(llm: Callable[[str], str], *, read_source: SourceReader) -> PatchAuthor:
    """把「prompt → 文本」的模型调用适配为执行器的补丁生产者契约。"""

    def _author(candidate: GenerationCandidate) -> PatchProposal:
        path = module_path(candidate.target_plugin)
        source = read_source(path)
        return PatchProposal(path=path, content=strip_fence(llm(build_prompt(candidate, source))))

    return _author
