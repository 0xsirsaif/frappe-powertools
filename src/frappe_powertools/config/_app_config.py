"""Typed config groups using Pydantic BaseModel.

Subclass ``AppConfig`` and declare fields + a ``Meta`` inner class to map
config keys automatically::

    class AwsConfig(AppConfig):
        class Meta:
            prefix = "aws"
            env_prefix = "AWS"

        enabled: bool = False
        s3_bucket: str = "default-bucket"
        secret_key: Secret[str]

    cfg = AwsConfig.load()
    cfg.s3_bucket       # read from aws_s3_bucket in site_config / AWS_S3_BUCKET env
    cfg.secret_key      # Secret instance — repr shows '***'
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict

from ._repository import ConfigRepository
from ._types import UNDEFINED, _Undefined


class AppConfig(BaseModel):
    """Base class for declarative, typed config groups."""

    model_config = ConfigDict(arbitrary_types_allowed=True)

    class Meta:
        prefix: str = ""
        env_prefix: str = ""
        key: str = ""

    @classmethod
    def load(cls, repo: ConfigRepository | None = None) -> "AppConfig":
        """Load config values and return a validated instance.

        Resolution per field:
        1. Environment variable (``{ENV_PREFIX}_{FIELD_NAME}`` uppercased)
        2. Site config key
        3. Common config key
        4. Omit — let Pydantic use the field default or raise ``ValidationError``
        """
        from ._reader import _auto_repository

        active_repo = repo or _auto_repository()

        meta = cls.Meta
        prefix = getattr(meta, "prefix", "")
        env_prefix = getattr(meta, "env_prefix", "")
        nested_key = getattr(meta, "key", "")

        # If Meta.key is set, read the entire nested dict once.
        nested_dict: dict[str, Any] = {}
        if nested_key:
            site_val = active_repo.get_site_config(nested_key)
            if isinstance(site_val, dict):
                nested_dict = site_val
            else:
                common_val = active_repo.get_common_config(nested_key)
                if isinstance(common_val, dict):
                    nested_dict = common_val

        raw_data: dict[str, Any] = {}

        for field_name in cls.model_fields:
            value: Any = UNDEFINED

            # --- Env var lookup ---
            if env_prefix:
                env_key = f"{env_prefix}_{field_name}".upper()
                env_val = active_repo.get_env(env_key)
                if env_val is not None:
                    value = env_val

            # --- Site / common config lookup ---
            if isinstance(value, _Undefined):
                if nested_key:
                    # Read from nested dict using field name directly.
                    dict_val = nested_dict.get(field_name, UNDEFINED)
                    if not isinstance(dict_val, _Undefined):
                        value = dict_val
                else:
                    # Build prefixed key.
                    config_key = f"{prefix}_{field_name}" if prefix else field_name

                    site_val = active_repo.get_site_config(config_key)
                    if site_val is not None:
                        value = site_val
                    else:
                        common_val = active_repo.get_common_config(config_key)
                        if common_val is not None:
                            value = common_val

            if not isinstance(value, _Undefined):
                raw_data[field_name] = value

        return cls.model_validate(raw_data)
