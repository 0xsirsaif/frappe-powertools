from __future__ import annotations

from collections.abc import Callable
from contextlib import ContextDecorator
from typing import Optional, TypeVar, ParamSpec, overload

import frappe

from .state import _get_state


P = ParamSpec("P")
R = TypeVar("R")


def _generate_savepoint_name(depth: int) -> str:
    """Generate a deterministic savepoint name based on nesting depth."""

    return f"powertools_sp_{depth}"


class Atomic(ContextDecorator):
    """Savepoint-based transaction wrapper aligned with Frappe's model.

    This class does not own the outer transaction in managed contexts.
    It only creates and manages savepoints so that nested blocks can
    roll back independently while letting Frappe handle the overall
    BEGIN / COMMIT / ROLLBACK.
    """

    def __init__(self, manage_transactions: bool = False):
        if manage_transactions:
            raise NotImplementedError(
                "manage_transactions=True is not implemented yet. "
                "Use Atomic() without manage_transactions or plain Frappe APIs."
            )

        self.manage_transactions = manage_transactions
        self._savepoint_name: Optional[str] = None

    def __enter__(self) -> "Atomic":
        state = _get_state()
        state.depth += 1

        name = _generate_savepoint_name(state.depth)
        self._savepoint_name = name
        state.savepoints.append(name)

        frappe.db.savepoint(name)

        return self

    def __exit__(self, exc_type, exc, tb) -> bool | None:
        state = _get_state()

        try:
            name = self._savepoint_name

            if not name:
                return False

            if exc_type is not None:
                if not state.error_rolled_back:
                    frappe.db.rollback(save_point=name)
                    state.error_rolled_back = True
            else:
                release_savepoint = getattr(frappe.db, "release_savepoint", None)

                if callable(release_savepoint):
                    release_savepoint(name)
        finally:
            if state.savepoints:
                state.savepoints.pop()

            if state.depth > 0:
                state.depth -= 1

            if state.depth == 0:
                state.error_rolled_back = False

        return False


@overload
def atomic(func_or_none: None = None, *, manage_transactions: bool = False) -> Atomic:
    ...


@overload
def atomic(func_or_none: Callable[P, R], *, manage_transactions: bool = False) -> Callable[P, R]:
    ...


def atomic(func_or_none: Callable[P, R] | None = None, *, manage_transactions: bool = False):
    """Django-like atomic decorator / context manager.

    Usage as context manager:

        with atomic():
            ...

    Usage as decorator:

        @atomic
        def handler(...):
            ...
    """

    if manage_transactions:
        raise NotImplementedError(
            "atomic(manage_transactions=True) is not implemented yet. "
            "Use manage_transactions=False for savepoint-based blocks."
        )

    if func_or_none is None:
        return Atomic(manage_transactions=manage_transactions)

    func = func_or_none

    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        with Atomic(manage_transactions=manage_transactions):
            return func(*args, **kwargs)

    return wrapper
