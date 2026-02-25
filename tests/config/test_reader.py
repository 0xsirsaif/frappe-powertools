"""Tests for _reader.py — the core config() function."""

import pytest

from frappe_powertools.config._casters import Choices, Csv
from frappe_powertools.config._reader import config
from frappe_powertools.config._repository import FakeConfigRepository
from frappe_powertools.config._types import UndefinedValueError


def _repo(**kwargs) -> FakeConfigRepository:
    return FakeConfigRepository(**kwargs)


class TestBasicLookup:
    def test_required_key_missing_raises(self):
        with pytest.raises(UndefinedValueError, match="missing_key"):
            config("missing_key", repo=_repo())

    def test_required_key_present(self):
        assert config("db_name", repo=_repo(site={"db_name": "mydb"})) == "mydb"

    def test_default_used_when_missing(self):
        assert config("nope", default="fallback", repo=_repo()) == "fallback"

    def test_default_none_is_valid(self):
        assert config("nope", default=None, repo=_repo()) is None


class TestCasting:
    def test_cast_int(self):
        result = config("port", cast=int, repo=_repo(site={"port": "8000"}))
        assert result == 8000
        assert isinstance(result, int)

    def test_cast_bool(self):
        assert config("debug", cast=bool, repo=_repo(site={"debug": "true"})) is True
        assert config("debug", cast=bool, repo=_repo(site={"debug": "0"})) is False

    def test_default_not_cast(self):
        """Default is returned as-is, NOT passed through cast."""
        result = config("missing", default=42, cast=str, repo=_repo())
        assert result == 42
        assert isinstance(result, int)

    def test_cast_csv(self):
        result = config("hosts", cast=Csv(), repo=_repo(site={"hosts": "a,b,c"}))
        assert result == ["a", "b", "c"]

    def test_cast_choices(self):
        result = config(
            "log_level",
            cast=Choices(["debug", "info"]),
            repo=_repo(site={"log_level": "info"}),
        )
        assert result == "info"

    def test_cast_choices_invalid(self):
        with pytest.raises(ValueError, match="not a valid choice"):
            config(
                "log_level",
                cast=Choices(["debug", "info"]),
                repo=_repo(site={"log_level": "critical"}),
            )


class TestPrecedence:
    def test_env_beats_site(self):
        repo = _repo(env={"MY_VAR": "from_env"}, site={"key": "from_site"})
        assert config("key", env="MY_VAR", repo=repo) == "from_env"

    def test_site_beats_common(self):
        repo = _repo(site={"key": "from_site"}, common={"key": "from_common"})
        assert config("key", repo=repo) == "from_site"

    def test_common_used_when_site_missing(self):
        assert config("key", repo=_repo(common={"key": "from_common"})) == "from_common"

    def test_env_parameter_maps_to_env_var_name(self):
        """The ``env=`` parameter specifies which env var name to check."""
        assert (
            config("some_key", env="CUSTOM_ENV_NAME", repo=_repo(env={"CUSTOM_ENV_NAME": "val"}))
            == "val"
        )

    def test_env_not_checked_when_env_param_not_given(self):
        """Without ``env=``, env vars are NOT checked."""
        repo = _repo(env={"some_key": "from_env"}, site={"some_key": "from_site"})
        assert config("some_key", repo=repo) == "from_site"


class TestDotPath:
    def test_nested_dict(self):
        repo = _repo(site={"fusion_config": {"tenant": "acme"}})
        assert config("fusion_config.tenant", repo=repo) == "acme"

    def test_deeply_nested(self):
        repo = _repo(site={"a": {"b": {"c": "deep"}}})
        assert config("a.b.c", repo=repo) == "deep"

    def test_missing_segment_uses_default(self):
        repo = _repo(site={"fusion_config": {"other": "val"}})
        assert config("fusion_config.tenant", default="none", repo=repo) == "none"

    def test_missing_segment_raises_when_required(self):
        repo = _repo(site={"fusion_config": {"other": "val"}})
        with pytest.raises(UndefinedValueError):
            config("fusion_config.tenant", repo=repo)

    def test_dot_path_with_cast(self):
        repo = _repo(site={"app": {"port": "3000"}})
        assert config("app.port", cast=int, repo=repo) == 3000

    def test_dot_path_in_common(self):
        repo = _repo(common={"app": {"debug": "true"}})
        assert config("app.debug", cast=bool, repo=repo) is True


class TestRepoParameter:
    def test_per_call_repo_overrides_module_level(self):
        """Passing repo= bypasses the module-level repository."""
        repo = _repo(site={"key": "from_explicit_repo"})
        assert config("key", repo=repo) == "from_explicit_repo"
