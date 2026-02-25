"""Typed, validated configuration layer for Frappe apps.

Provides fail-fast config reading with type casting, environment variable
support, and secret redaction — all without depending on a running Frappe site.
"""

from ._app_config import AppConfig
from ._casters import Choices, Csv
from ._reader import config
from ._repository import ConfigRepository, FakeConfigRepository
from ._testing import override_config
from ._types import ConfigError, Secret, UndefinedValueError

__all__ = [
    # Core
    "config",
    "ConfigError",
    "UndefinedValueError",
    # Typed groups
    "AppConfig",
    "Secret",
    # Helpers
    "Csv",
    "Choices",
    # Testing
    "override_config",
    "FakeConfigRepository",
    "ConfigRepository",
]
