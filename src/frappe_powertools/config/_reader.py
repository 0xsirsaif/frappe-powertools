"""Core ``config()`` function — the primary public API for reading config values.

Lookup order:
1. Environment variable (if ``env=`` specified)
2. Site config (``site_config.json``)
3. Common config (``common_site_config.json``)
4. Default value (returned as-is, **not** passed through ``cast``)
5. Raise ``UndefinedValueError``
"""

from __future__ import annotations

from typing import Any, Callable

from ._casters import _cast_bool
from ._repository import ConfigRepository
from ._types import UNDEFINED, UndefinedValueError, _Undefined

# ---------------------------------------------------------------------------
# Module-level repository management
# ---------------------------------------------------------------------------

_active_repository: ConfigRepository | None = None


def set_repository(repo: ConfigRepository | None) -> None:
    """Set the module-level config repository."""
    global _active_repository
    _active_repository = repo


def get_repository() -> ConfigRepository | None:
    """Return the current module-level config repository (may be ``None``)."""
    return _active_repository


def _auto_repository() -> ConfigRepository:
    """Lazily create a ``FrappeConfigRepository`` if none is set."""
    global _active_repository
    if _active_repository is None:
        from ._frappe_adapter import FrappeConfigRepository

        _active_repository = FrappeConfigRepository()
    return _active_repository


# ---------------------------------------------------------------------------
# Dot-path helpers
# ---------------------------------------------------------------------------


def _resolve_dot_path(source: dict[str, Any], key: str) -> Any:
    """Walk nested dicts using dot-separated key segments.

    Returns ``UNDEFINED`` if any segment is missing.
    """
    segments = key.split(".")
    current: Any = source
    for segment in segments:
        if not isinstance(current, dict):
            return UNDEFINED
        current = current.get(segment, UNDEFINED)
        if isinstance(current, _Undefined):
            return UNDEFINED
    return current


def _lookup_in_source(
    repo: ConfigRepository,
    key: str,
    source: str,
) -> Any:
    """Look up *key* in a single config source, supporting dot-path traversal.

    Returns ``UNDEFINED`` if the key is not found.
    """
    getter = repo.get_site_config if source == "site" else repo.get_common_config

    # 1) Try the literal key first (e.g., "fusion_config.tenant" as-is).
    raw = getter(key)
    if raw is not None:
        return raw

    # 2) Dot-path traversal: split on "." and walk nested dicts.
    if "." in key:
        top_key, _, rest = key.partition(".")
        top_value = getter(top_key)
        if isinstance(top_value, dict):
            result = _resolve_dot_path(top_value, rest)
            if not isinstance(result, _Undefined):
                return result

    return UNDEFINED


# ---------------------------------------------------------------------------
# Cast resolution
# ---------------------------------------------------------------------------


def _identity(value: Any) -> Any:
    """Return the value unchanged. Used as the default no-op caster."""
    return value


def _resolve_cast(cast: Callable | type | None) -> Callable[[Any], Any]:
    """Return the actual callable to apply to raw values."""
    if cast is None:
        return _identity
    if cast is bool:
        return _cast_bool
    return cast


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def config(
    key: str,
    *,
    default: Any = UNDEFINED,
    cast: Callable | type | None = None,
    env: str | None = None,
    repo: ConfigRepository | None = None,
) -> Any:
    """Read a configuration value with type casting and fail-fast semantics.

    Parameters
    ----------
    key:
        Config key to look up. Supports dot-paths (e.g., ``"fusion_config.tenant"``).
    default:
        Fallback value if the key is not found anywhere. Returned **as-is**
        (not passed through *cast*).
    cast:
        Callable to coerce the raw value. ``bool`` is special-cased to handle
        string representations like ``"true"`` / ``"0"``.
    env:
        Explicit environment variable name to check first.
    repo:
        Per-call repository override. Falls back to the module-level repository
        (or auto-creates a ``FrappeConfigRepository``).
    """
    active_repo = repo or _auto_repository()
    caster = _resolve_cast(cast)

    # 1) Environment variable
    if env is not None:
        env_value = active_repo.get_env(env)
        if env_value is not None:
            return caster(env_value)

    # 2) Site config
    site_value = _lookup_in_source(active_repo, key, "site")
    if not isinstance(site_value, _Undefined):
        return caster(site_value)

    # 3) Common config
    common_value = _lookup_in_source(active_repo, key, "common")
    if not isinstance(common_value, _Undefined):
        return caster(common_value)

    # 4) Default (returned as-is, NOT cast)
    if not isinstance(default, _Undefined):
        return default

    # 5) Fail fast
    raise UndefinedValueError(key)
