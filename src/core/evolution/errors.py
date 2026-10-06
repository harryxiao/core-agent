"""进化引擎领域错误码（evolution）。

结构化错误码与异常分离：无证据采集 / 候选待确认 / 验证门拒绝 / 留出集退化 / 无法评测 /
旧口径候选 / 实施被拒 / 实施漂移，以领域异常承载，不向模型抛裸异常。

对应接口：doc/03-interfaces/evolution-interface.md §错误码
"""

from __future__ import annotations

from enum import StrEnum


class EvolutionErrorCode(StrEnum):
    """进化引擎结构化错误码。"""

    NO_EVIDENCE = "NO_EVIDENCE"
    CANDIDATE_PENDING = "CANDIDATE_PENDING"
    GATE_REJECTED = "GATE_REJECTED"
    EVAL_REGRESSED = "EVAL_REGRESSED"
    CONFIRM_REQUIRED = "CONFIRM_REQUIRED"
    # 留出评测**无法评测**（无绑定基准 / 基准无样本 / 执行器未注册 / 未注册基线）⇒ 不下发、不发布；
    # 与 EVAL_REGRESSED（已判退化）分离 —— 「无法评测」不得被谎报为「退化」
    EVAL_FROZEN = "EVAL_FROZEN"
    # 候选的结晶面门口径版本与现口径不符（旧口径候选）⇒ 不得投放，须按现口径重新提案
    GATE_CALIBER_STALE = "GATE_CALIBER_STALE"
    # 原生实施（可选执行器）：实施被拒（前置不满足 / 范围守卫 / 路径与归因不符）
    IMPLEMENT_REJECTED = "IMPLEMENT_REJECTED"
    # 原生实施：目标文件自筹备以来已漂移，拒绝对已改内容覆盖补丁
    IMPLEMENT_STALE = "IMPLEMENT_STALE"


class EvolutionError(Exception):
    """进化引擎业务异常：携带结构化错误码与人类可读信息。"""

    def __init__(self, code: EvolutionErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message

    def __str__(self) -> str:
        return f"{self.code.value}: {self.message}"
