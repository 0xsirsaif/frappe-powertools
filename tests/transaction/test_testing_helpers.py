from __future__ import annotations

from types import SimpleNamespace

import frappe

from frappe_powertools.transaction.testing import FakeAtomic, disable_commits


def test_fake_atomic_commits_on_success():
    atomic = FakeAtomic()
    events: list[str] = []

    def on_commit():
        events.append("commit")

    def on_rollback():
        events.append("rollback")

    atomic.register_on_commit(on_commit)
    atomic.register_on_rollback(on_rollback)

    with atomic:
        events.append("body")

    assert atomic.committed is True
    assert atomic.rolled_back is False
    assert events == ["body", "commit"]


def test_fake_atomic_rolls_back_on_exception():
    atomic = FakeAtomic()
    events: list[str] = []

    def on_commit():
        events.append("commit")

    def on_rollback():
        events.append("rollback")

    atomic.register_on_commit(on_commit)
    atomic.register_on_rollback(on_rollback)

    try:
        with atomic:
            events.append("body")
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert atomic.committed is False
    assert atomic.rolled_back is True
    assert events == ["body", "rollback"]


def test_disable_commits_patches_frappe_db_commit(monkeypatch):
    calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def real_commit(*args, **kwargs):
        calls.append((args, kwargs))

    fake_db = SimpleNamespace(commit=real_commit)

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)

    with disable_commits():
        frappe.db.commit("x", key="y")

    assert calls == []

    frappe.db.commit("z")

    assert calls == [(("z",), {})]
