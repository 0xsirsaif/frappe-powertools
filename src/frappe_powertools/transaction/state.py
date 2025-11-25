from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

import frappe


@dataclass
class TransactionState:
    """Internal state for powertools-managed transaction helpers.

    Attributes:
        depth: Nesting depth of powertools-managed atomic blocks.
        savepoints: Stack of savepoint names created by powertools.
        owns_transaction: True when powertools has started the outer transaction
            (scripts/CLI mode with manage_transactions=True).
    """

    depth: int = 0
    savepoints: List[str] = field(default_factory=list)
    owns_transaction: bool = False


def _get_state() -> TransactionState:
    """Return per-request/per-context transaction state.

    In a Frappe environment this is stored on ``frappe.local`` so each
    request / job / worker gets its own state. Outside of Frappe we fall
    back to a module-level singleton.
    """

    local = getattr(frappe, "local", None)

    if local is not None:
        state = getattr(local, "_powertools_txn_state", None)

        if state is None:
            state = TransactionState()
            setattr(local, "_powertools_txn_state", state)

        return state

    global _GLOBAL_STATE

    try:
        return _GLOBAL_STATE
    except NameError:
        _GLOBAL_STATE = TransactionState()
        return _GLOBAL_STATE


def in_request_context() -> bool:
    """Return True if running inside a Frappe HTTP request."""

    local = getattr(frappe, "local", None)
    return bool(local and getattr(local, "request", None) is not None)


def in_background_job() -> bool:
    """Return True if running inside a background job context.

    This uses a simple heuristic: Frappe workers attach a ``job`` object
    to ``frappe.local`` while executing jobs.
    """

    local = getattr(frappe, "local", None)
    return bool(local and getattr(local, "job", None) is not None)


def in_test_context() -> bool:
    """Return True if running under the Frappe test runner."""

    flags = getattr(frappe, "flags", None)
    return bool(flags and getattr(flags, "in_test", False))


def is_frappe_managed_transaction() -> bool:
    """Return True if Frappe should own BEGIN/COMMIT/ROLLBACK.

    This is typically True for:
        - HTTP requests
        - Background / scheduled jobs
        - Patches / migrations
        - Frappe test runner

    For bare scripts / console sessions this is usually False.
    The function is deliberately conservative: when in doubt it returns
    True so we do not accidentally start managing transactions inside
    a Frappe-managed context.
    """

    if in_request_context() or in_background_job() or in_test_context():
        return True

    local = getattr(frappe, "local", None)

    if local is not None:
        # When a site is bound but we do not recognise the context,
        # err on the side of Frappe owning the transaction.
        if getattr(local, "site", None):
            return True

    # No Frappe context at all: likely a bare script / CLI.
    return False
