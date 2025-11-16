from __future__ import annotations

from typing import Iterable, Tuple


def collect_listener_names(cls) -> Tuple[str, ...]:
	names = []

	for base in reversed(cls.__mro__[1:]):
		base_names: Iterable[str] = getattr(base, "_powertools_listener_names", ())
		for name in base_names:
			if name not in names:
				names.append(name)

	for name, attr in cls.__dict__.items():
		if getattr(attr, "_powertools_listener_marker", False):
			if name not in names:
				names.append(name)

	return tuple(names)


def run_registered_listeners(instance) -> None:
	for name in getattr(instance, "_powertools_listener_names", ()):
		listener = getattr(instance, name, None)
		if callable(listener):
			listener()
