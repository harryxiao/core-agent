"""核心画像领域错误码（core-profile）。

本模块按设计**静默降级**：文件缺失不报错、分区非法仅告警并跳过，因此
不向调用方抛异常。这里只提供结构化错误码作为诊断/遥测标签：

- ``PROFILE_MISSING``：Core.md 文件缺失（静默降级，按无该级别预设继续）
- ``SECTION_INVALID``：分区标记格式非法或无法解析（告警跳过，加载其余合法分区）

对应接口：doc/03-interfaces/core-profile-interface.md §7
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """核心画像结构化错误码（诊断标签，非抛出异常）。"""

    PROFILE_MISSING = "PROFILE_MISSING"
    SECTION_INVALID = "SECTION_INVALID"
