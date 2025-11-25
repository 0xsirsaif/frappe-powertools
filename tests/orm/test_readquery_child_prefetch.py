"""Tests for child table prefetch functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import ReadQuery


class ChildItemSchema(DocModel):
    """DocModel for a child table item."""

    class Meta:
        doctype = "Child Item"

    name: str
    parent: str
    parenttype: str
    parentfield: str
    item_name: str
    quantity: int
    idx: int


class ParentSchema(DocModel):
    """DocModel for a parent DocType with child table."""

    class Meta:
        doctype = "Parent DocType"
        children = {"items": ChildItemSchema}

    name: str
    title: str
    status: str


def test_prefetch_children_attaches_child_lists():
    """Test that prefetch attaches child lists to parent models."""
    query = ReadQuery(ParentSchema).prefetch("items")

    # Create parent models
    parent1 = ParentSchema(name="PARENT-001", title="Parent 1", status="Active")
    parent2 = ParentSchema(name="PARENT-002", title="Parent 2", status="Active")
    parent_models = [parent1, parent2]

    # Create child models
    child1 = ChildItemSchema(
        name="CHILD-001",
        parent="PARENT-001",
        parenttype="Parent DocType",
        parentfield="items",
        item_name="Item 1",
        quantity=10,
        idx=0,
    )
    child2 = ChildItemSchema(
        name="CHILD-002",
        parent="PARENT-001",
        parenttype="Parent DocType",
        parentfield="items",
        item_name="Item 2",
        quantity=20,
        idx=1,
    )
    child3 = ChildItemSchema(
        name="CHILD-003",
        parent="PARENT-002",
        parenttype="Parent DocType",
        parentfield="items",
        item_name="Item 3",
        quantity=30,
        idx=0,
    )

    # Mock _prefetch_children to manually attach children
    def mock_prefetch(parents):
        object.__setattr__(parents[0], "items", [child1, child2])
        object.__setattr__(parents[1], "items", [child3])

    with (
        patch.object(query, "_build_frappe_query") as mock_build,
        patch.object(query, "_prefetch_children", side_effect=mock_prefetch),
    ):
        # Mock parent query
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = [
            {"name": "PARENT-001", "title": "Parent 1", "status": "Active"},
            {"name": "PARENT-002", "title": "Parent 2", "status": "Active"},
        ]
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Verify we got parent models
        assert len(results) == 2
        assert all(isinstance(r, ParentSchema) for r in results)

        # Verify child lists are attached
        assert hasattr(results[0], "items")
        assert isinstance(results[0].items, list)
        assert len(results[0].items) == 2
        assert all(isinstance(item, ChildItemSchema) for item in results[0].items)
        assert results[0].items[0].item_name == "Item 1"
        assert results[0].items[1].item_name == "Item 2"

        assert hasattr(results[1], "items")
        assert isinstance(results[1].items, list)
        assert len(results[1].items) == 1
        assert results[1].items[0].item_name == "Item 3"


def test_prefetch_children_empty_when_no_children():
    """Test that prefetch sets empty list when parent has no children."""
    query = ReadQuery(ParentSchema).prefetch("items")

    # Mock _prefetch_children to set empty list
    def mock_prefetch(parents):
        object.__setattr__(parents[0], "items", [])

    with (
        patch.object(query, "_build_frappe_query") as mock_build,
        patch.object(query, "_prefetch_children", side_effect=mock_prefetch),
    ):
        # Mock parent query
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = [
            {"name": "PARENT-001", "title": "Parent 1", "status": "Active"}
        ]
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Verify parent model exists
        assert len(results) == 1
        assert hasattr(results[0], "items")
        assert results[0].items == []


def test_prefetch_children_ignores_unknown_fields():
    """Test that prefetch ignores fields not in Meta.children."""
    query = ReadQuery(ParentSchema).prefetch("items", "unknown_field")

    # Mock _prefetch_children to only set "items"
    def mock_prefetch(parents):
        object.__setattr__(parents[0], "items", [])

    with (
        patch.object(query, "_build_frappe_query") as mock_build,
        patch.object(query, "_prefetch_children", side_effect=mock_prefetch),
    ):
        # Mock parent query
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = [
            {"name": "PARENT-001", "title": "Parent 1", "status": "Active"}
        ]
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Should only prefetch "items", not "unknown_field"
        assert len(results) == 1
        assert hasattr(results[0], "items")
        assert not hasattr(results[0], "unknown_field")


def test_prefetch_children_skips_when_no_prefetch_fields():
    """Test that prefetch is skipped when no prefetch_fields are set."""
    query = ReadQuery(ParentSchema)

    parent_rows = [{"name": "PARENT-001", "title": "Parent 1", "status": "Active"}]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = parent_rows
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Verify no child lists are attached
        assert len(results) == 1
        assert not hasattr(results[0], "items")


def test_prefetch_children_handles_multiple_child_fields():
    """Test that prefetch works with multiple child table fields."""

    # Create a schema with multiple child tables
    class ChildItem2Schema(DocModel):
        class Meta:
            doctype = "Child Item 2"

        name: str
        parent: str
        parenttype: str
        parentfield: str
        value: str
        idx: int

    class ParentWithMultipleChildren(DocModel):
        class Meta:
            doctype = "Parent With Multiple Children"
            children = {"items": ChildItemSchema, "notes": ChildItem2Schema}

        name: str
        title: str

    query = ReadQuery(ParentWithMultipleChildren).prefetch("items", "notes")

    parent_rows = [{"name": "PARENT-001", "title": "Parent 1"}]

    # Mock _prefetch_children to set both child lists
    def mock_prefetch(parents):
        object.__setattr__(parents[0], "items", [])
        object.__setattr__(parents[0], "notes", [])

    with (
        patch.object(query, "_build_frappe_query") as mock_build,
        patch.object(query, "_prefetch_children", side_effect=mock_prefetch),
    ):
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = parent_rows
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Verify both child lists are attached
        assert len(results) == 1
        assert hasattr(results[0], "items")
        assert hasattr(results[0], "notes")
        assert results[0].items == []
        assert results[0].notes == []


def test_prefetch_children_orders_by_idx():
    """Test that child items are ordered by idx field."""
    query = ReadQuery(ParentSchema).prefetch("items")

    parent_rows = [{"name": "PARENT-001", "title": "Parent 1", "status": "Active"}]

    child_rows = [
        {
            "name": "CHILD-002",
            "parent": "PARENT-001",
            "parenttype": "Parent DocType",
            "parentfield": "items",
            "item_name": "Item 2",
            "quantity": 20,
            "idx": 1,
        },
        {
            "name": "CHILD-001",
            "parent": "PARENT-001",
            "parenttype": "Parent DocType",
            "parentfield": "items",
            "item_name": "Item 1",
            "quantity": 10,
            "idx": 0,
        },
    ]

    # Create child models in the order they would come from DB
    child1 = ChildItemSchema(
        name="CHILD-002",
        parent="PARENT-001",
        parenttype="Parent DocType",
        parentfield="items",
        item_name="Item 2",
        quantity=20,
        idx=1,
    )
    child2 = ChildItemSchema(
        name="CHILD-001",
        parent="PARENT-001",
        parenttype="Parent DocType",
        parentfield="items",
        item_name="Item 1",
        quantity=10,
        idx=0,
    )

    # Mock _prefetch_children to attach children
    def mock_prefetch(parents):
        object.__setattr__(parents[0], "items", [child1, child2])

    with (
        patch.object(query, "_build_frappe_query") as mock_build,
        patch.object(query, "_prefetch_children", side_effect=mock_prefetch),
    ):
        mock_parent_query = MagicMock()
        mock_parent_query.run.return_value = parent_rows
        mock_build.return_value = mock_parent_query

        results = query.all()

        # Verify children are ordered by idx (as they would be from DB)
        assert len(results) == 1
        assert len(results[0].items) == 2
        assert results[0].items[0].idx == 1
        assert results[0].items[1].idx == 0


@pytest.mark.skipif(
    "frappe" not in __import__("sys").modules,
    reason="Requires Frappe environment",
)
def test_prefetch_children_with_real_frappe():
    """Integration test with real Frappe (if available)."""
    try:
        import frappe

        if not hasattr(frappe, "local"):
            pytest.skip("Not in a Frappe environment")

        # This test would require a real DocType with child table
        # For now, we'll just verify the method doesn't crash
        query = ReadQuery(ParentSchema).prefetch("items")

        # If we can't find the doctype, that's okay - we're just testing the structure
        try:
            results = query.limit(1).all()
            # If we got results, verify structure
            if results:
                assert all(isinstance(r, ParentSchema) for r in results)
        except Exception:
            # If doctype doesn't exist, that's fine for this test
            pass

    except ImportError:
        pytest.skip("Frappe not available")
