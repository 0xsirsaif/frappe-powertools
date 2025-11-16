from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Dict, List, Tuple


WrapperFunc = Callable[[Any, Callable[..., Any], tuple, dict], Any]


def attach_method_wrapper(cls, method_name: str, key: str, wrapper: Callable) -> None:
	wrappers: Dict[str, List[Tuple[str, Callable]]] = getattr(cls, "_powertools_method_wrappers", {})
	method_wrappers = wrappers.setdefault(method_name, [])

	if any(existing_key == key for existing_key, _ in method_wrappers):
		return

	method_wrappers.append((key, wrapper))
	setattr(cls, "_powertools_method_wrappers", wrappers)

	_rebuild_method_chain(cls, method_name)


def _rebuild_method_chain(cls, method_name: str) -> None:
	wrappers: Dict[str, List[Tuple[str, Callable]]] = getattr(cls, "_powertools_method_wrappers", {})
	method_wrappers = wrappers.get(method_name, [])

	original_methods: Dict[str, Callable] = getattr(cls, "_powertools_original_methods", {})

	if method_name not in original_methods:
		original_methods[method_name] = getattr(cls, method_name)
		setattr(cls, "_powertools_original_methods", original_methods)

	base = original_methods[method_name]

	composed = base
	for _, wrapper in reversed(method_wrappers):
		composed = _compose_wrapper(wrapper, composed)

	setattr(cls, method_name, composed)


def _compose_wrapper(wrapper: Callable, next_method: Callable) -> Callable:
	@wraps(next_method)
	def inner(self, *args, **kwargs):
		return wrapper(self, next_method, args, kwargs)

	return inner
