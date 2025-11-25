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
    savepoint_spy = Spy()
    rollback_spy = Spy()
    release_spy = Spy()

    fake_db = SimpleNamespace(
        savepoint=savepoint_spy,
        rollback=rollback_spy,
        release_savepoint=release_spy,
    )

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)

    return savepoint_spy, rollback_spy, release_spy


def test_explicit_savepoint_inside_atomic(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    with atomic() as txn:
        with txn.savepoint():
            pass

    # outer atomic savepoint + inner explicit savepoint
    assert len(savepoint_spy.calls) == 2
    assert len(rollback_spy.calls) == 0
    # outer atomic release + inner savepoint release
    assert len(release_spy.calls) == 2


def test_explicit_savepoint_rolls_back_only_inner(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    try:
        with atomic() as txn:
            with txn.savepoint():
                raise RuntimeError("inner failure")
    except RuntimeError:
        pass

    # one atomic savepoint + one explicit savepoint
    assert len(savepoint_spy.calls) == 2
    # two rollbacks: one for the inner explicit savepoint and one from the outer atomic
    assert len(rollback_spy.calls) == 2
    assert rollback_spy.calls[0][1].get("save_point") is not None
    assert rollback_spy.calls[1][1].get("save_point") is not None
    # no releases since we rolled back
    assert len(release_spy.calls) == 0


def test_savepoint_usage_outside_atomic(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    from frappe_powertools.transaction.atomic import Savepoint

    with Savepoint("sp_outside"):
        pass

    assert len(savepoint_spy.calls) == 1
    assert savepoint_spy.calls[0][0] == ("sp_outside",)
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1
