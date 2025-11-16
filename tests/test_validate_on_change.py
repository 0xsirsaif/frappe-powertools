import types

from frappe_powertools import validate_on_change
from frappe_powertools.listeners import ChangeListenerMixin, change_listeners


class DummyDoc:
    def __init__(self, new=False, fields=None, tables_changed=None, old_available=True):
        self._is_new = new
        self._fields = fields or {}
        self._tables_changed = set(tables_changed or [])
        self._old_available = old_available

    def is_new(self):
        return self._is_new

    def get_doc_before_save(self):
        return {} if self._old_available else None

    def has_value_changed(self, field):
        return bool(self._fields.get(field))

    def is_child_table_same(self, table):
        return table not in self._tables_changed


def _spy(func):
    def wrapper(*args, **kwargs):
        wrapper.calls += 1
        return func(*args, **kwargs)

    wrapper.calls = 0
    wrapper.__name__ = func.__name__
    wrapper.__doc__ = func.__doc__
    wrapper.__module__ = func.__module__
    return wrapper


def test_runs_on_new_doc():
    doc = DummyDoc(new=True)

    @_spy
    def base(self):
        return "ran"

    validator = validate_on_change("x")(base)
    method = types.MethodType(validator, doc)
    assert method() == "ran"
    assert base.calls == 1


def test_skips_when_nothing_changed():
    doc = DummyDoc(new=False, fields={"x": False}, tables_changed=[])

    @_spy
    def base(self):
        return "ran"

    validator = validate_on_change("x", tables=("items",))(base)
    method = types.MethodType(validator, doc)
    assert method() is None
    assert base.calls == 0


def test_runs_when_field_changed():
    doc = DummyDoc(new=False, fields={"x": True})

    @_spy
    def base(self):
        return "ran"

    validator = validate_on_change("x")(base)
    method = types.MethodType(validator, doc)
    assert method() == "ran"
    assert base.calls == 1


def test_runs_when_table_changed():
    doc = DummyDoc(new=False, tables_changed=["items"])

    @_spy
    def base(self):
        return "ran"

    validator = validate_on_change(tables=("items",))(base)
    method = types.MethodType(validator, doc)
    assert method() == "ran"
    assert base.calls == 1


def test_missing_old_skip():
    doc = DummyDoc(new=False, old_available=False)

    @_spy
    def base(self):
        return "ran"

    validator = validate_on_change("x", missing_old="skip")(base)
    method = types.MethodType(validator, doc)
    assert method() is None
    assert base.calls == 0


def test_mixin_auto_runs_listener_only_when_changed():
    class BaseDoc:
        def __init__(self, fields=None):
            self._fields = fields or {}
            self.base_validate_calls = 0
            self.listener_calls = 0

        def is_new(self):
            return False

        def get_doc_before_save(self):
            return {}

        def has_value_changed(self, field):
            return bool(self._fields.get(field))

        def is_child_table_same(self, table):
            return True

        def validate(self):
            self.base_validate_calls += 1

    class MyDoc(ChangeListenerMixin, BaseDoc):
        @validate_on_change("x")
        def _listener(self):
            self.listener_calls += 1

    changed = MyDoc(fields={"x": True})
    changed.validate()
    assert changed.base_validate_calls == 1
    assert changed.listener_calls == 1

    unchanged = MyDoc(fields={"x": False})
    unchanged.validate()
    assert unchanged.base_validate_calls == 1
    assert unchanged.listener_calls == 0


def test_class_decorator_auto_runs_listener():
    class BaseDoc:
        def __init__(self, fields=None):
            self._fields = fields or {}
            self.base_validate_calls = 0
            self.listener_calls = 0

        def is_new(self):
            return False

        def get_doc_before_save(self):
            return {}

        def has_value_changed(self, field):
            return bool(self._fields.get(field))

        def is_child_table_same(self, table):
            return True

        def validate(self):
            self.base_validate_calls += 1

    @change_listeners
    class MyDoc(BaseDoc):
        @validate_on_change("x")
        def _listener(self):
            self.listener_calls += 1

    changed = MyDoc(fields={"x": True})
    changed.validate()
    assert changed.base_validate_calls == 1
    assert changed.listener_calls == 1

    unchanged = MyDoc(fields={"x": False})
    unchanged.validate()
    assert unchanged.base_validate_calls == 1
    assert unchanged.listener_calls == 0
