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
        rollback=lambda *args, **kwargs: rollback_spy(*args, **kwargs),
        release_savepoint=release_spy,
    )

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)

    return savepoint_spy, rollback_spy, release_spy


def test_atomic_happy_path_uses_savepoint_and_release(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    with atomic():
        pass

    assert len(savepoint_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1


def test_atomic_rolls_back_to_savepoint_on_exception(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    try:
        with atomic():
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert len(savepoint_spy.calls) == 1
    assert len(rollback_spy.calls) == 1
    assert rollback_spy.calls[0][1].get("save_point") is not None
    assert len(release_spy.calls) == 0


def test_atomic_nested_savepoints_and_inner_exception(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    try:
        with atomic():
            with atomic():
                raise ValueError("inner")
    except ValueError:
        pass

    assert len(savepoint_spy.calls) == 2
    assert len(rollback_spy.calls) == 1
    inner_save_point = rollback_spy.calls[0][1].get("save_point")
    assert inner_save_point is not None
    assert len(release_spy.calls) == 0


def test_atomic_decorator_behaves_like_context_manager(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db(monkeypatch)

    @atomic
    def do_work():
        return "ok"

    result = do_work()

    assert result == "ok"
    assert len(savepoint_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1


def test_atomic_manage_transactions_true_not_implemented(monkeypatch):
    _install_fake_db(monkeypatch)

    try:
        with atomic(manage_transactions=True):
            pass
    except NotImplementedError:
        raised = True
    else:
        raised = False

    assert raised is True
