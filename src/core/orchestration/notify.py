"""失败通知的远程 sink（change 0281 / ADR-0271）。

只提供**一个**通用原语：向配置的 HTTP(S) URL 单次 `POST` 一份 JSON。不做 IM 平台方言、
不做重试队列、不持久化待发送——无人值守场景下「发出一次」优先于复杂投递语义。
仅用 stdlib ``urllib.request``，契合核心零三方运行时依赖红线。
"""

from __future__ import annotations

import json
import urllib.request
from typing import Any

# 单次推送上限（秒）：只发生在任务已失败的收口路径上，必须有界。
WEBHOOK_TIMEOUT_S = 5.0
_USER_AGENT = "core-agent/0.1"


def post_failure_webhook(
    url: str, payload: dict[str, Any], *, timeout: float = WEBHOOK_TIMEOUT_S
) -> None:
    """向 ``url`` POST ``payload``（JSON）；失败原样抛出，由调用方兜底。

    调用方 SHALL 保证 ``payload`` 已脱敏且有界——本函数不做密钥处理。
    """
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": _USER_AGENT},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout):
        pass
