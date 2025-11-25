from __future__ import annotations

from types import SimpleNamespace

import frappe

from frappe_powertools import transaction


class _CallbackSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _make_fake_db(monkeypatch, **overrides):
    callbacks_namespace = SimpleNamespace()
    callbacks_namespace.add = _CallbackSpy()

    fake_db = SimpleNamespace(
        before_commit=callbacks_namespace,
        after_commit=callbacks_namespace,
        before_rollback=callbacks_namespace,
        after_rollback=callbacks_namespace,
        commit=_CallbackSpy(),
        rollback=_CallbackSpy(),
    )

    for name, value in overrides.items():
        setattr(fake_db, name, value)

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)
    return fake_db


def test_on_commit_uses_frappe_after_commit(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    callback = _CallbackSpy()
    transaction.on_commit(callback)

    assert fake_db.after_commit.add.calls == [((callback,), {})]


def test_on_rollback_uses_frappe_after_rollback(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    callback = _CallbackSpy()
    transaction.on_rollback(callback)

    assert fake_db.after_rollback.add.calls == [((callback,), {})]


def test_before_commit_uses_frappe_before_commit(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    callback = _CallbackSpy()
    transaction.before_commit(callback)

    assert fake_db.before_commit.add.calls == [((callback,), {})]


def test_before_rollback_uses_frappe_before_rollback(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    callback = _CallbackSpy()
    transaction.before_rollback(callback)

    assert fake_db.before_rollback.add.calls == [((callback,), {})]


def test_commit_delegates_to_frappe_db_commit_without_chain(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    transaction.commit()

    assert len(fake_db.commit.calls) == 1
    assert fake_db.commit.calls[0] == ((), {})


def test_commit_passes_chain_when_supported(monkeypatch):
    def commit_with_chain(*, chain: bool = False) -> None:
        spy(chain)

    spy = _CallbackSpy()

    fake_db = _make_fake_db(monkeypatch, commit=commit_with_chain)

    transaction.commit(chain=True)

    assert len(spy.calls) == 1
    assert spy.calls[0] == ((True,), {})


def test_rollback_without_savepoint_or_chain(monkeypatch):
    fake_db = _make_fake_db(monkeypatch)

    transaction.rollback()

    assert len(fake_db.rollback.calls) == 1
    assert fake_db.rollback.calls[0] == ((), {})


def test_rollback_with_savepoint(monkeypatch):
    def rollback_with_savepoint(*, save_point: str) -> None:
        spy(save_point)

    spy = _CallbackSpy()

    _make_fake_db(monkeypatch, rollback=rollback_with_savepoint)

    transaction.rollback(save_point="sp1")

    assert len(spy.calls) == 1
    assert spy.calls[0] == (("sp1",), {})


def test_rollback_with_savepoint_and_chain_when_supported(monkeypatch):
    def rollback_with_options(*, save_point: str | None = None, chain: bool = False) -> None:
        spy(save_point, chain)

    spy = _CallbackSpy()

    _make_fake_db(monkeypatch, rollback=rollback_with_options)

    transaction.rollback(save_point="sp1", chain=True)

    assert len(spy.calls) == 1
    assert spy.calls[0] == (("sp1", True), {})


def test_rollback_rejects_invalid_savepoint(monkeypatch):
    _make_fake_db(monkeypatch)

    try:
        transaction.rollback(save_point="")
    except ValueError as exc:
        message = str(exc)
    else:
        message = ""

    assert "save_point must be a non-empty string" in message


def test_error_when_db_not_initialized(monkeypatch):
    if hasattr(frappe, "db"):
        monkeypatch.delattr(frappe, "db", raising=False)

    callback = _CallbackSpy()

    try:
        transaction.on_commit(callback)
    except transaction.TransactionError as exc:
        message = str(exc)
    else:
        message = ""

    assert "Frappe database is not initialized" in message
