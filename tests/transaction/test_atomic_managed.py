from __future__ import annotations

from types import SimpleNamespace

import frappe

from frappe_powertools.transaction import atomic


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _install_fake_db(monkeypatch):
    begin_spy = Spy()
    commit_spy = Spy()
    rollback_spy = Spy()
    savepoint_spy = Spy()
    release_spy = Spy()

    fake_db = SimpleNamespace(
        begin=begin_spy,
        commit=commit_spy,
        rollback=rollback_spy,
        savepoint=savepoint_spy,
        release_savepoint=release_spy,
    )

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)

    return begin_spy, commit_spy, rollback_spy, savepoint_spy, release_spy


def _ensure_no_frappe_context(monkeypatch):
    if hasattr(frappe, "local"):
        monkeypatch.delattr(frappe, "local", raising=False)

    if hasattr(frappe, "flags"):
        monkeypatch.delattr(frappe, "flags", raising=False)


def test_managed_atomic_begins_and_commits_in_script_context(monkeypatch):
    _ensure_no_frappe_context(monkeypatch)
    begin_spy, commit_spy, rollback_spy, savepoint_spy, release_spy = _install_fake_db(monkeypatch)

    with atomic(manage_transactions=True):
        pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(savepoint_spy.calls) == 1
    assert len(release_spy.calls) == 1


def test_managed_atomic_rolls_back_on_exception_in_script_context(monkeypatch):
    _ensure_no_frappe_context(monkeypatch)
    begin_spy, commit_spy, rollback_spy, savepoint_spy, release_spy = _install_fake_db(monkeypatch)

    try:
        with atomic(manage_transactions=True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 0
    # outer rollback at DB level (not the savepoint rollback)
    assert len(rollback_spy.calls) >= 1
    assert len(savepoint_spy.calls) == 1
    assert len(release_spy.calls) == 0


def test_nested_managed_atomic_uses_single_begin_and_commit(monkeypatch):
    _ensure_no_frappe_context(monkeypatch)
    begin_spy, commit_spy, rollback_spy, savepoint_spy, release_spy = _install_fake_db(monkeypatch)

    with atomic(manage_transactions=True):
        with atomic(manage_transactions=True):
            pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    # two savepoints: outer and inner
    assert len(savepoint_spy.calls) == 2
    assert len(release_spy.calls) == 2


def test_managed_atomic_guard_in_frappe_managed_context(monkeypatch):
    monkeypatch.setattr(frappe, "local", SimpleNamespace(request=object()), raising=False)

    _install_fake_db(monkeypatch)

    raised = False

    try:
        with atomic(manage_transactions=True):
            pass
    except RuntimeError:
        raised = True

    assert raised is True
