"""Foundation types for the config module.

Provides sentinel values, exception classes, and the Secret wrapper type.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar, get_args

from pydantic import GetCoreSchemaHandler
from pydantic_core import CoreSchema, core_schema

T = TypeVar("T")


# ---------------------------------------------------------------------------
# Sentinel
# ---------------------------------------------------------------------------


class _Undefined:
    """Sentinel for missing config values (distinct from ``None``)."""

    _instance: _Undefined | None = None

    def __new__(cls) -> _Undefined:
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "UNDEFINED"

    def __bool__(self) -> bool:
        return False


UNDEFINED = _Undefined()


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ConfigError(Exception):
    """Base exception for config-related errors."""


class UndefinedValueError(ConfigError):
    """Raised when a required configuration key is missing."""

    def __init__(self, key: str) -> None:
        self.key = key
        super().__init__(f"Configuration key '{key}' is required but not set.")


# ---------------------------------------------------------------------------
# Secret
# ---------------------------------------------------------------------------


class Secret(Generic[T]):
    """Wraps a value so it is redacted in ``repr`` / ``str`` output.

    Access the real value via ``.secret_value``.
    """

    __slots__ = ("_value",)

    def __init__(self, value: T) -> None:
        object.__setattr__(self, "_value", value)

    @property
    def secret_value(self) -> T:
        return self._value  # type: ignore[return-value]

    # -- redaction ----------------------------------------------------------

    def __repr__(self) -> str:
        return "Secret('***')"

    def __str__(self) -> str:
        return "***"

    # -- comparison ---------------------------------------------------------

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Secret):
            return bool(self._value == other._value)
        return NotImplemented

    def __hash__(self) -> int:
        return hash(self._value)

    def __bool__(self) -> bool:
        return bool(self._value)

    # -- Pydantic v2 integration --------------------------------------------

    @classmethod
    def __get_pydantic_core_schema__(
        cls,
        source_type: Any,
        handler: GetCoreSchemaHandler,
    ) -> CoreSchema:
        # Extract the inner type arg (e.g., ``str`` from ``Secret[str]``).
        args = get_args(source_type)
        inner_type = args[0] if args else Any

        # Generate the inner schema so Pydantic knows about the inner type,
        # but we handle validation/serialization ourselves.
        handler.generate_schema(inner_type)

        def _validate(value: Any) -> "Secret[Any]":
            if isinstance(value, Secret):
                return value
            return Secret(value)

        def _serialize(value: "Secret[Any]", _info: Any) -> str:
            return "***"

        return core_schema.no_info_plain_validator_function(
            _validate,
            serialization=core_schema.plain_serializer_function_ser_schema(
                _serialize,
                info_arg=True,
            ),
            metadata={"pydantic_js_functions": []},
        )
