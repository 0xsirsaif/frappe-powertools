"""Config source protocol and in-memory implementation for tests."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConfigRepository(Protocol):
    """Abstraction over where config values come from.

    Implementations provide three lookup methods corresponding to the
    standard Frappe config sources.
    """

    def get_env(self, key: str) -> str | None:
        ...

    def get_site_config(self, key: str) -> Any:
        ...

    def get_common_config(self, key: str) -> Any:
        ...


class FakeConfigRepository:
    """Dict-backed config repository for tests.

    >>> repo = FakeConfigRepository(env={"DEBUG": "1"}, site={"db_name": "test"})
    >>> repo.get_env("DEBUG")
    '1'
    """

    def __init__(
        self,
        env: dict[str, str] | None = None,
        site: dict[str, Any] | None = None,
        common: dict[str, Any] | None = None,
    ) -> None:
        self._env: dict[str, str] = dict(env or {})
        self._site: dict[str, Any] = dict(site or {})
        self._common: dict[str, Any] = dict(common or {})

    # -- Protocol methods ---------------------------------------------------

    def get_env(self, key: str) -> str | None:
        return self._env.get(key)

    def get_site_config(self, key: str) -> Any:
        return self._site.get(key)

    def get_common_config(self, key: str) -> Any:
        return self._common.get(key)

    # -- Mutation helpers for test setup ------------------------------------

    def set_env(self, key: str, value: str) -> None:
        self._env[key] = value

    def set_site(self, key: str, value: Any) -> None:
        self._site[key] = value

    def set_common(self, key: str, value: Any) -> None:
        self._common[key] = value
