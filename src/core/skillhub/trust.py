"""技能签名校验（TrustVerifier）。

以技能关键内容（skill_id / version / instructions）的 SHA-256 摘要作为签名，
发布方 sign、下载方 verify；签名不匹配返回 False（下载方据此拒绝下载）。

对应接口：doc/03-interfaces/skillhub-interface.md §5
"""

from __future__ import annotations

import hashlib

from core.skills import Skill


class TrustVerifier:
    """技能签名校验：sha256(skill_id|version|instructions)。"""

    def __init__(self, *, trusted: set[str] | None = None) -> None:
        self._trusted = set(trusted or ())

    def verify(self, skill: Skill, signature: str) -> bool:
        """校验技能签名与来源可信度；失败返回 False（下载方据此拒绝）。"""
        return signature in self._trusted or self.sign(skill) == signature

    def sign(self, skill: Skill) -> str:
        """生成技能签名摘要（发布方使用）。"""
        return self._digest(skill)

    @staticmethod
    def _digest(skill: Skill) -> str:
        payload = f"{skill.skill_id}|{skill.version}|{skill.instructions}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()
