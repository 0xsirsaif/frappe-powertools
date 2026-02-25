"""Tests for _app_config.py — AppConfig base class."""

import pytest
from pydantic import ValidationError

from frappe_powertools.config._app_config import AppConfig
from frappe_powertools.config._repository import FakeConfigRepository
from frappe_powertools.config._types import Secret


def _repo(**kwargs) -> FakeConfigRepository:
    return FakeConfigRepository(**kwargs)


class TestPrefixMapping:
    def test_basic_prefix(self):
        class AwsConfig(AppConfig):
            class Meta:
                prefix = "aws"

            enabled: bool = False
            s3_bucket: str = "default"

        cfg = AwsConfig.load(repo=_repo(site={"aws_enabled": True, "aws_s3_bucket": "my-bucket"}))
        assert cfg.enabled is True
        assert cfg.s3_bucket == "my-bucket"

    def test_no_prefix(self):
        class SimpleConfig(AppConfig):
            debug: bool = False

        cfg = SimpleConfig.load(repo=_repo(site={"debug": True}))
        assert cfg.debug is True


class TestEnvPrefix:
    def test_env_prefix(self):
        class AwsConfig(AppConfig):
            class Meta:
                prefix = "aws"
                env_prefix = "AWS"

            enabled: bool = False

        cfg = AwsConfig.load(repo=_repo(env={"AWS_ENABLED": "true"}))
        assert cfg.enabled is True

    def test_env_beats_site(self):
        class AwsConfig(AppConfig):
            class Meta:
                prefix = "aws"
                env_prefix = "AWS"

            region: str = "us-east-1"

        cfg = AwsConfig.load(
            repo=_repo(
                env={"AWS_REGION": "eu-west-1"},
                site={"aws_region": "ap-south-1"},
            )
        )
        assert cfg.region == "eu-west-1"


class TestNestedKey:
    def test_reads_nested_dict(self):
        class FusionConfig(AppConfig):
            class Meta:
                key = "fusion_config"

            tenant: str
            api_url: str = "https://default.example.com"

        cfg = FusionConfig.load(
            repo=_repo(
                site={"fusion_config": {"tenant": "acme", "api_url": "https://acme.example.com"}}
            )
        )
        assert cfg.tenant == "acme"
        assert cfg.api_url == "https://acme.example.com"

    def test_nested_from_common(self):
        class FusionConfig(AppConfig):
            class Meta:
                key = "fusion_config"

            tenant: str

        cfg = FusionConfig.load(repo=_repo(common={"fusion_config": {"tenant": "shared"}}))
        assert cfg.tenant == "shared"

    def test_env_overrides_nested(self):
        class FusionConfig(AppConfig):
            class Meta:
                key = "fusion_config"
                env_prefix = "FUSION"

            tenant: str

        cfg = FusionConfig.load(
            repo=_repo(
                env={"FUSION_TENANT": "from-env"},
                site={"fusion_config": {"tenant": "from-json"}},
            )
        )
        assert cfg.tenant == "from-env"


class TestDefaultsAndValidation:
    def test_uses_field_defaults(self):
        class MyConfig(AppConfig):
            port: int = 8000

        cfg = MyConfig.load(repo=_repo())
        assert cfg.port == 8000

    def test_missing_required_field_raises(self):
        class MyConfig(AppConfig):
            required_key: str

        with pytest.raises(ValidationError):
            MyConfig.load(repo=_repo())

    def test_type_coercion_string_to_bool(self):
        """Pydantic coerces '1'/'true' strings to bool for bool-typed fields."""

        class MyConfig(AppConfig):
            class Meta:
                env_prefix = "APP"

            debug: bool = False

        cfg = MyConfig.load(repo=_repo(env={"APP_DEBUG": "1"}))
        assert cfg.debug is True


class _AwsSecretConfig(AppConfig):
    """Shared config class for Secret field tests."""

    class Meta:
        prefix = "aws"

    secret_key: Secret[str]


class TestSecretFields:
    def test_secret_field_loaded(self):
        cfg = _AwsSecretConfig.load(repo=_repo(site={"aws_secret_key": "s3cr3t"}))
        assert isinstance(cfg.secret_key, Secret)
        assert cfg.secret_key.secret_value == "s3cr3t"

    def test_secret_repr_redacted(self):
        cfg = _AwsSecretConfig.load(repo=_repo(site={"aws_secret_key": "s3cr3t"}))
        assert "s3cr3t" not in repr(cfg)

    def test_secret_required_missing_raises(self):
        class MyConfig(AppConfig):
            secret_key: Secret[str]

        with pytest.raises(ValidationError):
            MyConfig.load(repo=_repo())

    def test_secret_model_dump_redacted(self):
        cfg = _AwsSecretConfig.load(repo=_repo(site={"aws_secret_key": "s3cr3t"}))
        assert cfg.model_dump()["secret_key"] == "***"


class TestMultipleConfigs:
    def test_different_prefixes_isolated(self):
        class AwsConfig(AppConfig):
            class Meta:
                prefix = "aws"

            region: str = "us-east-1"

        class GcpConfig(AppConfig):
            class Meta:
                prefix = "gcp"

            project: str = "default"

        repo = _repo(site={"aws_region": "eu-west-1", "gcp_project": "my-project"})
        aws = AwsConfig.load(repo=repo)
        gcp = GcpConfig.load(repo=repo)

        assert aws.region == "eu-west-1"
        assert gcp.project == "my-project"
