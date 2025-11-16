from __future__ import annotations

from ._listener_utils import collect_listener_names, run_registered_listeners
from .._method_chain import attach_method_wrapper


def change_listeners(cls):
    """Class decorator: auto-run ``@validate_on_change`` listeners after ``validate``."""

    cls._powertools_listener_names = collect_listener_names(cls)
    attach_method_wrapper(cls, "validate", "powertools:change_listeners", _listener_wrapper)
    return cls


def _listener_wrapper(self, next_method, args, kwargs):
    result = next_method(self, *args, **kwargs)
    run_registered_listeners(self)
    return result
