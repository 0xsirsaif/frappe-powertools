from __future__ import annotations

from collections.abc import Callable
import inspect

import frappe


class TransactionError(RuntimeError):
    """Raised when the Frappe database connection is not available."""


def _get_db():
    """Return the active Frappe database connection or raise a clear error."""

    db = getattr(frappe, "db", None)

    if db is None:
        raise TransactionError(
            "Frappe database is not initialized. "
            "Make sure frappe.init() and frappe.connect() have been called."
        )

    return db


def before_commit(callback: Callable[[], None]) -> None:
    """Register a callback to run before the next successful commit."""

    db = _get_db()
    db.before_commit.add(callback)


def after_commit(callback: Callable[[], None]) -> None:
    """Register a callback to run after the next successful commit."""

    db = _get_db()
    db.after_commit.add(callback)


def before_rollback(callback: Callable[[], None]) -> None:
    """Register a callback to run before the next rollback."""

    db = _get_db()
    db.before_rollback.add(callback)


def after_rollback(callback: Callable[[], None]) -> None:
    """Register a callback to run after the next rollback."""

    db = _get_db()
    db.after_rollback.add(callback)


def on_commit(callback: Callable[[], None]) -> None:
    """Convenience alias for registering an after-commit callback."""

    after_commit(callback)


def on_rollback(callback: Callable[[], None]) -> None:
    """Convenience alias for registering an after-rollback callback."""

    after_rollback(callback)


def commit(*, chain: bool = False) -> None:
    """Commit the current transaction using Frappe's database API.

    The ``chain`` argument is accepted for forward compatibility with
    possible future Frappe signatures. In current Frappe versions it is
    ignored, but tests assert that it is passed through when supported.
    """

    db = _get_db()

    signature = inspect.signature(db.commit)
    parameters = signature.parameters

    if "chain" in parameters:
        db.commit(chain=chain)
    else:
        db.commit()


def rollback(*, save_point: str | None = None, chain: bool = False) -> None:
    """Roll back the current transaction using Frappe's database API.

    Args:
        save_point: Optional savepoint name to roll back to.
        chain: Forward‑compatibility flag, passed through only if supported
            by the underlying Frappe ``rollback`` implementation.
    """

    if save_point is not None:
        if not isinstance(save_point, str) or not save_point:
            raise ValueError("save_point must be a non-empty string when provided")

    db = _get_db()

    signature = inspect.signature(db.rollback)
    parameters = signature.parameters
    kwargs: dict[str, object] = {}

    if "save_point" in parameters and save_point is not None:
        kwargs["save_point"] = save_point

    if "chain" in parameters:
        kwargs["chain"] = chain

    if kwargs:
        db.rollback(**kwargs)
    else:
        db.rollback()
