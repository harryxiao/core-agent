"""配置管理（configuration）：config.yaml 单一收口 + 密钥分级 + 功能开关 + ConfigSpec 单一真源。"""

from .errors import ConfigurationError
from .manager import (
    ConfigManager,
    config_specs,
    generate_cli_flags,
    generate_env_vars,
    generate_yaml_defaults,
    resolve,
    validate_map_to,
)
from .models import AppConfig, ConfigExposure, ConfigSpec, IMConfig, LLMConfig, ValidationResult

__all__ = [
    "AppConfig",
    "ConfigExposure",
    "ConfigManager",
    "ConfigSpec",
    "ConfigurationError",
    "config_specs",
    "IMConfig",
    "LLMConfig",
    "ValidationResult",
    "generate_cli_flags",
    "generate_env_vars",
    "generate_yaml_defaults",
    "resolve",
    "validate_map_to",
]
