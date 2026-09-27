"""经验采集（evolution）。

从 `MemoryBackend`(Protocol) 采集行动→结果成对证据；无结果证据的 action 跳过
（不产生虚假经验）；强制模式下无证据抛 `NO_EVIDENCE`。

对应接口：doc/03-interfaces/evolution-interface.md ｜ 规格 evolution/spec.md「经验采集」
"""

from __future__ import annotations

from .errors import EvolutionError, EvolutionErrorCode
from .models import Trace


class Collector:
    """经验采集器：过滤出有结果证据的行动→结果对。"""

    plugin_id = "evolution.collector"

    def collect(self, traces: list[Trace], *, require_evidence: bool = False) -> list[Trace]:
        """返回有结果证据的 trace 子集；无证据 action 跳过。

        `require_evidence=True` 时，若全部无证据则抛 `NO_EVIDENCE`（契约红线：
        无结果证据不采集）。
        """
        evidence = [t for t in traces if t.result is not None]
        if require_evidence and not evidence:
            raise EvolutionError(EvolutionErrorCode.NO_EVIDENCE, "无任何行动→结果成对证据")
        return evidence
