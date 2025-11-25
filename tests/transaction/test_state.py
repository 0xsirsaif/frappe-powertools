from __future__ import annotations

from types import SimpleNamespace

import frappe

from frappe_powertools.transaction import state


def test_get_state_uses_frappe_local(monkeypatch):
    """_get_state should store state on frappe.local when available."""

    fake_local = SimpleNamespace()

    monkeypatch.setattr(frappe, "local", fake_local, raising=False)

    first = state._get_state()
    second = state._get_state()

    assert isinstance(first, state.TransactionState)
    assert first is second
    assert getattr(frappe.local, "_powertools_txn_state") is first


def test_get_state_uses_global_singleton_when_no_frappe_local(monkeypatch):
    """_get_state should fall back to a module-level singleton."""

    if hasattr(frappe, "local"):
        monkeypatch.delattr(frappe, "local", raising=False)

    first = state._get_state()
    second = state._get_state()

    assert isinstance(first, state.TransactionState)
    assert first is second


def test_in_request_context_detects_request(monkeypatch):
    fake_local = SimpleNamespace(request=object())

    monkeypatch.setattr(frappe, "local", fake_local, raising=False)

    assert state.in_request_context() is True
    assert state.is_frappe_managed_transaction() is True


def test_in_background_job_detects_job(monkeypatch):
    fake_local = SimpleNamespace(job=object())

    monkeypatch.setattr(frappe, "local", fake_local, raising=False)

    assert state.in_background_job() is True
    assert state.is_frappe_managed_transaction() is True


def test_in_test_context_respects_frappe_flags(monkeypatch):
    fake_flags = SimpleNamespace(in_test=True)

    monkeypatch.setattr(frappe, "flags", fake_flags, raising=False)

    assert state.in_test_context() is True
    assert state.is_frappe_managed_transaction() is True


def test_is_frappe_managed_transaction_false_for_bare_script(monkeypatch):
    """When there is no frappe.local at all, treat context as script/CLI."""

    if hasattr(frappe, "local"):
        monkeypatch.delattr(frappe, "local", raising=False)

    if hasattr(frappe, "flags"):
        monkeypatch.delattr(frappe, "flags", raising=False)

    assert state.is_frappe_managed_transaction() is False
