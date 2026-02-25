"""Test utilities for the config module."""

from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Iterator

from ._reader import get_repository, set_repository
from ._repository import FakeConfigRepository


@contextmanager
def override_config(
    *,
    site: dict[str, Any] | None = None,
    common: dict[str, Any] | None = None,
    env: dict[str, str] | None = None,
) -> Iterator[FakeConfigRepository]:
    """Temporarily replace the config source with a ``FakeConfigRepository``.

    Usage::

        with override_config(site={"aws_enabled": True}, env={"AWS_KEY": "test"}) as repo:
            assert config("aws_enabled", cast=bool) is True
            repo.set_site("extra", 42)  # mutate inside context
    """
    previous = get_repository()
    fake = FakeConfigRepository(env=env, site=site, common=common)
    set_repository(fake)
    try:
        yield fake
    finally:
        set_repository(previous)
