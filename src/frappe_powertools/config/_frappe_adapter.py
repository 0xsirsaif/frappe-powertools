"""Thin adapter that reads config from the live Frappe runtime."""

from __future__ import annotations

import os
from typing import Any

try:
    import frappe
except ImportError:  # pragma: no cover
    frappe = None


class FrappeConfigRepository:
    """Reads config from ``os.environ``, ``frappe.conf``, and common site config."""

    def get_env(self, key: str) -> str | None:
        return os.environ.get(key)

    def get_site_config(self, key: str) -> Any:
        if frappe is None:
            return None
        conf = getattr(frappe, "conf", None)
        if conf is None:
            return None
        return conf.get(key)

    def get_common_config(self, key: str) -> Any:
        if frappe is None:
            return None
        try:
            return frappe.get_common_site_config().get(key)
        except Exception:
            return None
