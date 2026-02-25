"""Tests for _types.py — Secret, UNDEFINED, and exception classes."""

import pytest
from pydantic import BaseModel, ConfigDict, ValidationError

from frappe_powertools.config._types import (
    UNDEFINED,
    ConfigError,
    Secret,
    UndefinedValueError,
    _Undefined,
)


class TestUndefined:
    def test_singleton(self):
        assert _Undefined() is _Undefined()
        assert _Undefined() is UNDEFINED

    def test_falsy(self):
        assert not UNDEFINED
        assert bool(UNDEFINED) is False

    def test_repr(self):
        assert repr(UNDEFINED) == "UNDEFINED"


class TestConfigError:
    def test_is_exception(self):
        assert issubclass(ConfigError, Exception)


class TestUndefinedValueError:
    def test_inherits_config_error(self):
        assert issubclass(UndefinedValueError, ConfigError)

    def test_message_includes_key(self):
        err = UndefinedValueError("my_key")
        assert "my_key" in str(err)
        assert err.key == "my_key"


class TestSecret:
    def test_repr_redacts(self):
        s = Secret("hunter2")
        assert "hunter2" not in repr(s)
        assert "***" in repr(s)

    def test_str_redacts(self):
        assert str(Secret("hunter2")) == "***"

    def test_secret_value_returns_original(self):
        assert Secret("hunter2").secret_value == "hunter2"

    def test_equality(self):
        assert Secret("a") == Secret("a")
        assert Secret("a") != Secret("b")

    def test_not_equal_to_raw(self):
        assert Secret("a") != "a"

    def test_hash(self):
        assert hash(Secret("a")) == hash("a")
        assert {Secret("a"), Secret("a")} == {Secret("a")}

    def test_bool_truthy(self):
        assert bool(Secret("x")) is True

    def test_bool_falsy(self):
        assert bool(Secret("")) is False
        assert bool(Secret(0)) is False


class _SecretModel(BaseModel):
    """Shared Pydantic model for Secret field tests."""

    model_config = ConfigDict(arbitrary_types_allowed=True)
    api_key: Secret[str]


class TestSecretPydantic:
    def test_as_pydantic_field(self):
        m = _SecretModel(api_key="raw-value")
        assert isinstance(m.api_key, Secret)
        assert m.api_key.secret_value == "raw-value"

    def test_passthrough_if_already_secret(self):
        s = Secret("wrapped")
        m = _SecretModel(api_key=s)
        assert m.api_key is s

    def test_model_dump_redacts(self):
        dumped = _SecretModel(api_key="my-secret").model_dump()
        assert dumped["api_key"] == "***"

    def test_required_secret_missing_raises(self):
        with pytest.raises(ValidationError):
            _SecretModel()
