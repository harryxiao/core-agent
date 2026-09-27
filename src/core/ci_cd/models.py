"""CI/CD 交付流水线数据模型（ci-cd）。

门禁 / 门禁结果 / 流水线执行 / 版本化制品 四类数据结构。

对应接口：doc/03-interfaces/ci-cd-interface.md §1
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Gate:
    """门禁：一道质量校验，归属 lint/typecheck/test/build 四类之一。"""

    gate_id: str
    kind: str  # "lint" | "typecheck" | "test" | "build"
    blocking: bool = True


@dataclass
class GateResult:
    """单道门禁执行结果（注入执行器的返回载体，接口文档未列）。"""

    passed: bool
    reason: str = ""


@dataclass
class PipelineRun:
    """一次交付流水线执行：顺序执行四道门禁的结果。"""

    run_id: str
    commit_ref: str
    gates: list[Gate]
    status: str  # "passed" | "blocked" | "running"


@dataclass
class Artifact:
    """版本化制品：门禁通过后的可追溯、可回滚交付物。"""

    artifact_id: str
    version: str
    commit_ref: str
    channel: str
