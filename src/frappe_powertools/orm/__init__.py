from __future__ import annotations

from typing import Type

from ..doctype_schema import DocModel
from .query import ReadQuery

__all__ = ["DocModel", "ReadQuery", "query_for", "attach_manager"]


def query_for(schema: Type[DocModel]) -> ReadQuery[DocModel]:
    """Create a ReadQuery instance for the given DocModel schema.

    Args:
        schema: A DocModel subclass to query

    Returns:
        A ReadQuery instance bound to the schema

    Example:
        from frappe_powertools.orm import query_for

        query = query_for(TrainingBatchSchema)
        results = query.filter(status="Active").all()
    """
    return ReadQuery(schema)


def attach_manager(schema: Type[DocModel]) -> Type[DocModel]:
    """Attach a `.objects` manager to a DocModel class.

    This provides a Django ORM-like interface where you can use
    `MyDocModel.objects.filter(...).all()`.

    Args:
        schema: A DocModel subclass to attach the manager to

    Returns:
        The schema class itself for chaining

    Example:
        @attach_manager
        class TrainingBatch(DocModel):
            class Meta:
                doctype = "Training Batch"
            # ...

        # Usage:
        batches = TrainingBatch.objects.filter(status="Active").all()
    """

    # Attach a descriptor instead of a static ReadQuery instance
    # This ensures each access gets a fresh query object
    class ManagerDescriptor:
        def __get__(self, instance, owner):
            return ReadQuery(owner)

    setattr(schema, "objects", ManagerDescriptor())
    return schema
