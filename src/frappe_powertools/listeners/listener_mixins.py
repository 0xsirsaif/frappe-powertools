from __future__ import annotations

from typing import Tuple

from ._listener_utils import collect_listener_names, run_registered_listeners
from .._method_chain import attach_method_wrapper


class ChangeListenerMixin:
	"""Auto-dispatch mixin for ``@validate_on_change`` listeners."""

	_powertools_listener_names: Tuple[str, ...] = ()

	def __init_subclass__(cls, **kwargs):
		super().__init_subclass__(**kwargs)
		cls._powertools_listener_names = collect_listener_names(cls)
		attach_method_wrapper(cls, "validate", "powertools:change_listeners", _listener_wrapper)

	def _run_powertools_listeners(self) -> None:
		run_registered_listeners(self)


def _listener_wrapper(self, next_method, args, kwargs):
	result = next_method(self, *args, **kwargs)
	run_registered_listeners(self)
	return result
