from __future__ import annotations

from collections.abc import Callable
from contextlib import ContextDecorator, contextmanager

import frappe


class FakeAtomic(ContextDecorator):
    """In-memory stand-in for Atomic, for use in unit tests."""

    def __init__(self) -> None:
        self.committed: bool = False
        self.rolled_back: bool = False
        self.commit_callbacks: list[Callable[[], None]] = []
        self.rollback_callbacks: list[Callable[[], None]] = []

    def __enter__(self) -> "FakeAtomic":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        if exc_type is not None:
            self.rolled_back = True

            for cb in self.rollback_callbacks:
                cb()
        else:
            self.committed = True

            for cb in self.commit_callbacks:
                cb()

        return False

    def register_on_commit(self, cb: Callable[[], None]) -> None:
        self.commit_callbacks.append(cb)

    def register_on_rollback(self, cb: Callable[[], None]) -> None:
        self.rollback_callbacks.append(cb)


@contextmanager
def disable_commits():
    """Temporarily disable frappe.db.commit for test isolation."""

    db = getattr(frappe, "db", None)

    if db is None or not hasattr(db, "commit"):
        yield
        return

    original_commit = db.commit

    try:
        db.commit = lambda *args, **kwargs: None
        yield
    finally:
        db.commit = original_commit
