from __future__ import annotations

from types import SimpleNamespace

import frappe

from frappe_powertools import transaction
from frappe_powertools.transaction import atomic, state


class _CallbackSpy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


class Spy:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def __call__(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


# ---------------------------------------------------------------------------
# Hook wrappers
# ---------------------------------------------------------------------------


def _install_fake_db_for_hooks(monkeypatch, **overrides):
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
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    callback = _CallbackSpy()
    transaction.on_commit(callback)

    assert fake_db.after_commit.add.calls == [((callback,), {})]


def test_on_rollback_uses_frappe_after_rollback(monkeypatch):
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    callback = _CallbackSpy()
    transaction.on_rollback(callback)

    assert fake_db.after_rollback.add.calls == [((callback,), {})]


def test_before_commit_uses_frappe_before_commit(monkeypatch):
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    callback = _CallbackSpy()
    transaction.before_commit(callback)

    assert fake_db.before_commit.add.calls == [((callback,), {})]


def test_before_rollback_uses_frappe_before_rollback(monkeypatch):
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    callback = _CallbackSpy()
    transaction.before_rollback(callback)

    assert fake_db.before_rollback.add.calls == [((callback,), {})]


def test_commit_delegates_to_frappe_db_commit_without_chain(monkeypatch):
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    transaction.commit()

    assert len(fake_db.commit.calls) == 1
    assert fake_db.commit.calls[0] == ((), {})


def test_commit_passes_chain_when_supported(monkeypatch):
    def commit_with_chain(*, chain: bool = False) -> None:
        spy(chain)

    spy = _CallbackSpy()

    _install_fake_db_for_hooks(monkeypatch, commit=commit_with_chain)

    transaction.commit(chain=True)

    assert len(spy.calls) == 1
    assert spy.calls[0] == ((True,), {})


def test_rollback_without_savepoint_or_chain(monkeypatch):
    fake_db = _install_fake_db_for_hooks(monkeypatch)

    transaction.rollback()

    assert len(fake_db.rollback.calls) == 1
    assert fake_db.rollback.calls[0] == ((), {})


def test_rollback_with_savepoint(monkeypatch):
    def rollback_with_savepoint(*, save_point: str) -> None:
        spy(save_point)

    spy = _CallbackSpy()

    _install_fake_db_for_hooks(monkeypatch, rollback=rollback_with_savepoint)

    transaction.rollback(save_point="sp1")

    assert len(spy.calls) == 1
    assert spy.calls[0] == (("sp1",), {})


def test_rollback_with_savepoint_and_chain_when_supported(monkeypatch):
    def rollback_with_options(*, save_point: str | None = None, chain: bool = False) -> None:
        spy(save_point, chain)

    spy = _CallbackSpy()

    _install_fake_db_for_hooks(monkeypatch, rollback=rollback_with_options)

    transaction.rollback(save_point="sp1", chain=True)

    assert len(spy.calls) == 1
    assert spy.calls[0] == (("sp1", True), {})


def test_rollback_rejects_invalid_savepoint(monkeypatch):
    _install_fake_db_for_hooks(monkeypatch)

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


# ---------------------------------------------------------------------------
# Transaction state and environment detection
# ---------------------------------------------------------------------------


def test_get_state_uses_frappe_local(monkeypatch):
    fake_local = SimpleNamespace()

    monkeypatch.setattr(frappe, "local", fake_local, raising=False)

    first = state._get_state()
    second = state._get_state()

    assert isinstance(first, state.TransactionState)
    assert first is second
    assert getattr(frappe.local, "_powertools_txn_state") is first


def test_get_state_uses_global_singleton_when_no_frappe_local(monkeypatch):
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
    if hasattr(frappe, "local"):
        monkeypatch.delattr(frappe, "local", raising=False)

    if hasattr(frappe, "flags"):
        monkeypatch.delattr(frappe, "flags", raising=False)

    assert state.is_frappe_managed_transaction() is False


# ---------------------------------------------------------------------------
# Atomic: basic savepoint-based behavior
# ---------------------------------------------------------------------------


def _install_fake_db_for_atomic_basic(monkeypatch):
    savepoint_spy = Spy()
    rollback_spy = Spy()
    release_spy = Spy()

    fake_db = SimpleNamespace(
        savepoint=savepoint_spy,
        rollback=lambda *args, **kwargs: rollback_spy(*args, **kwargs),
        release_savepoint=release_spy,
        begin=Spy(),
        commit=Spy(),
    )

    monkeypatch.setattr(frappe, "db", fake_db, raising=False)

    return savepoint_spy, rollback_spy, release_spy


def test_atomic_happy_path_uses_savepoint_and_release(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_atomic_basic(monkeypatch)

    with atomic():
        pass

    assert len(savepoint_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1


def test_atomic_rolls_back_to_savepoint_on_exception(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_atomic_basic(monkeypatch)

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
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_atomic_basic(monkeypatch)

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
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_atomic_basic(monkeypatch)

    @atomic
    def do_work():
        return "ok"

    result = do_work()

    assert result == "ok"
    assert len(savepoint_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1


def test_atomic_manage_transactions_true_delegates_to_managed_mode(monkeypatch):
    _install_fake_db_for_atomic_basic(monkeypatch)

    try:
        with atomic(manage_transactions=True):
            pass
    except NotImplementedError:
        raised = True
    else:
        raised = False

    assert raised is False


# ---------------------------------------------------------------------------
# Atomic: managed mode for scripts / CLI
# ---------------------------------------------------------------------------


def _install_fake_db_for_atomic_managed(monkeypatch):
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
    (
        begin_spy,
        commit_spy,
        rollback_spy,
        savepoint_spy,
        release_spy,
    ) = _install_fake_db_for_atomic_managed(monkeypatch)

    with atomic(manage_transactions=True):
        pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(savepoint_spy.calls) == 1
    assert len(release_spy.calls) == 1


def test_managed_atomic_rolls_back_on_exception_in_script_context(monkeypatch):
    _ensure_no_frappe_context(monkeypatch)
    (
        begin_spy,
        commit_spy,
        rollback_spy,
        savepoint_spy,
        release_spy,
    ) = _install_fake_db_for_atomic_managed(monkeypatch)

    try:
        with atomic(manage_transactions=True):
            raise RuntimeError("boom")
    except RuntimeError:
        pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 0
    assert len(rollback_spy.calls) >= 1
    assert len(savepoint_spy.calls) == 1
    assert len(release_spy.calls) == 0


def test_nested_managed_atomic_uses_single_begin_and_commit(monkeypatch):
    _ensure_no_frappe_context(monkeypatch)
    (
        begin_spy,
        commit_spy,
        rollback_spy,
        savepoint_spy,
        release_spy,
    ) = _install_fake_db_for_atomic_managed(monkeypatch)

    with atomic(manage_transactions=True):
        with atomic(manage_transactions=True):
            pass

    assert len(begin_spy.calls) == 1
    assert len(commit_spy.calls) == 1
    assert len(rollback_spy.calls) == 0
    assert len(savepoint_spy.calls) == 2
    assert len(release_spy.calls) == 2


def test_managed_atomic_guard_in_frappe_managed_context(monkeypatch):
    monkeypatch.setattr(frappe, "local", SimpleNamespace(request=object()), raising=False)

    _install_fake_db_for_atomic_managed(monkeypatch)

    raised = False

    try:
        with atomic(manage_transactions=True):
            pass
    except RuntimeError:
        raised = True

    assert raised is True


# ---------------------------------------------------------------------------
# Explicit savepoints
# ---------------------------------------------------------------------------


def _install_fake_db_for_savepoints(monkeypatch):
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
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_savepoints(monkeypatch)

    with atomic() as txn:
        with txn.savepoint():
            pass

    assert len(savepoint_spy.calls) == 2
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 2


def test_explicit_savepoint_rolls_back_only_inner(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_savepoints(monkeypatch)

    try:
        with atomic() as txn:
            with txn.savepoint():
                raise RuntimeError("inner failure")
    except RuntimeError:
        pass

    assert len(savepoint_spy.calls) == 2
    assert len(rollback_spy.calls) == 2
    assert rollback_spy.calls[0][1].get("save_point") is not None
    assert rollback_spy.calls[1][1].get("save_point") is not None
    assert len(release_spy.calls) == 0


def test_savepoint_usage_outside_atomic(monkeypatch):
    savepoint_spy, rollback_spy, release_spy = _install_fake_db_for_savepoints(monkeypatch)

    from frappe_powertools.transaction.atomic import Savepoint

    with Savepoint("sp_outside"):
        pass

    assert len(savepoint_spy.calls) == 1
    assert savepoint_spy.calls[0][0] == ("sp_outside",)
    assert len(rollback_spy.calls) == 0
    assert len(release_spy.calls) == 1
