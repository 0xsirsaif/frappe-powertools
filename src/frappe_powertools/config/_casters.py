"""Cast helpers for config values.

These callables transform raw string values from environment variables or
JSON config into the desired Python types.
"""

from __future__ import annotations

from typing import Any, Callable, Sequence


# ---------------------------------------------------------------------------
# Bool caster
# ---------------------------------------------------------------------------

_TRUTHY = frozenset({"1", "true", "yes", "on", "t", "y"})
_FALSY = frozenset({"0", "false", "no", "off", "f", "n", ""})


def _cast_bool(value: Any) -> bool:
    """Cast a value to ``bool``, handling common string representations.

    Raises ``ValueError`` for unrecognised strings.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        lower = value.strip().lower()
        if lower in _TRUTHY:
            return True
        if lower in _FALSY:
            return False
        raise ValueError(f"Cannot cast {value!r} to bool")
    raise ValueError(f"Cannot cast {type(value).__name__} to bool")


# ---------------------------------------------------------------------------
# Csv
# ---------------------------------------------------------------------------


class Csv:
    """Split a string into a list, with optional per-element casting.

    >>> Csv()("a, b, c")
    ['a', 'b', 'c']
    >>> Csv(cast=int)("1,2,3")
    [1, 2, 3]
    """

    def __init__(
        self,
        cast: Callable[[str], Any] = str,
        delimiter: str = ",",
        strip: bool = True,
        post_process: Callable[[list], Any] | None = None,
    ) -> None:
        self.cast = cast
        self.delimiter = delimiter
        self.strip = strip
        self.post_process = post_process

    def __call__(self, value: Any) -> Any:
        if isinstance(value, (list, tuple)):
            return value

        parts = str(value).split(self.delimiter)
        if self.strip:
            parts = [p.strip() for p in parts]
        result = [self.cast(p) for p in parts if p]

        if self.post_process is not None:
            return self.post_process(result)
        return result


# ---------------------------------------------------------------------------
# Choices
# ---------------------------------------------------------------------------


class Choices:
    """Validate that a value is one of a fixed set of choices.

    >>> Choices(["debug", "info", "warning"])("info")
    'info'
    """

    def __init__(
        self,
        choices: Sequence[Any],
        cast: Callable[[Any], Any] = str,
    ) -> None:
        self.choices = choices
        self.cast = cast

    def __call__(self, value: Any) -> Any:
        casted = self.cast(value)
        if casted not in self.choices:
            raise ValueError(
                f"{casted!r} is not a valid choice. Must be one of {list(self.choices)}"
            )
        return casted
