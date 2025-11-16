from __future__ import annotations

from functools import wraps
from typing import Any, Callable, Iterable

_SENTINEL = object()


def _get_old_doc_cached(doc) -> Any | None | bool:
    """Cache ``get_doc_before_save`` calls on the document instance.

    Returns:
        Document-like object if available, or ``False`` when the lookup already determined
        the old version is missing.
    """
    cached = getattr(doc, "_powertools_old_doc_cache", _SENTINEL)
    if cached is _SENTINEL:
        old = doc.get_doc_before_save()
        setattr(doc, "_powertools_old_doc_cache", old if old is not None else False)
        return getattr(doc, "_powertools_old_doc_cache")
    return cached


def validate_on_change(
    *fields: str,
    tables: Iterable[str] | None = None,
    always_on_new: bool = True,
    missing_old: str = "run",
) -> Callable:
    """Decorator: execute the wrapped validator only when tracked state changed.

    Usage:
        >>> from frappe_powertools import validate_on_change
        >>>
        >>> class A(Document):
        ...     def validate(self):
        ...         self.validate_1()
        ...         self.validate_2()
        ...
        ...     @validate_on_change(tables=("meetings",))
        ...     def validate_1(self):
        ...         ...
        ...
        ...     @validate_on_change("start_date", "end_date", tables=("meetings",))
        ...     def validate_2(self):
        ...         ...

    Semantics:
      - If ``always_on_new`` and ``doc.is_new()`` -> run.
      - If the previous state is missing:
          * ``missing_old="run"``  -> run (default)
          * ``missing_old="skip"`` -> skip
          * ``missing_old="raise"``-> raise ``RuntimeError``
      - If any field listed in ``fields`` changed (``has_value_changed``) -> run.
      - If any child table in ``tables`` changed (``is_child_table_same`` returns ``False``) -> run.
      - Otherwise the decorator returns ``None`` without invoking the function.
    """

    tables = tuple(tables or ())

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(self, *args, **kwargs):
            if always_on_new and getattr(self, "is_new")():
                return fn(self, *args, **kwargs)

            old_doc = _get_old_doc_cached(self)
            if old_doc is False:
                if missing_old == "skip":
                    return None
                if missing_old == "raise":
                    raise RuntimeError("Old document state missing; cannot compare.")
                return fn(self, *args, **kwargs)

            for field in fields:
                if self.has_value_changed(field):
                    return fn(self, *args, **kwargs)

            for table in tables:
                if not self.is_child_table_same(table):
                    return fn(self, *args, **kwargs)

            return None

        wrapper._powertools_listener_marker = True  # type: ignore[attr-defined]
        wrapper._powertools_listener_tables = tables  # type: ignore[attr-defined]
        wrapper._powertools_listener_fields = tuple(fields)  # type: ignore[attr-defined]
        return wrapper

    return decorator

