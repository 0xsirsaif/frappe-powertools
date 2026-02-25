"""Tests for _testing.py — override_config context manager."""

import pytest

from frappe_powertools.config._app_config import AppConfig
from frappe_powertools.config._reader import config, get_repository, set_repository
from frappe_powertools.config._repository import FakeConfigRepository
from frappe_powertools.config._testing import override_config


@pytest.fixture(autouse=True)
def _reset_module_repo():
    """Reset module-level repo before and after each test."""
    set_repository(None)
    yield
    set_repository(None)


class TestOverrideConfig:
    def test_replaces_config_source(self):
        with override_config(site={"key": "overridden"}):
            assert config("key") == "overridden"

    def test_restores_original_repo(self):
        original = FakeConfigRepository(site={"key": "original"})
        set_repository(original)

        with override_config(site={"key": "temp"}):
            assert config("key") == "temp"

        assert get_repository() is original
        assert config("key") == "original"

    def test_app_config_respects_override(self):
        class MyConfig(AppConfig):
            class Meta:
                prefix = "app"

            debug: bool = False

        with override_config(site={"app_debug": True}):
            cfg = MyConfig.load()
            assert cfg.debug is True

    def test_nested_overrides(self):
        with override_config(site={"key": "outer"}):
            assert config("key") == "outer"
            with override_config(site={"key": "inner"}):
                assert config("key") == "inner"
            assert config("key") == "outer"

    def test_yields_fake_repo_for_mutation(self):
        with override_config(site={"key": "initial"}) as repo:
            assert config("key") == "initial"
            repo.set_site("key", "mutated")
            assert config("key") == "mutated"
