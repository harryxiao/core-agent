"""配置管理错误。

配置模块在契约速查表中无结构化错误码（见 contracts_summary §3），
以 :class:`ConfigurationError` 承载可读信息：LLM 缺失阻断启动、yaml
明文密钥拒绝、密钥引用未解析等，均抛此异常。
"""

from __future__ import annotations


class ConfigurationError(Exception):
    """配置加载 / 校验失败。"""

    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message
