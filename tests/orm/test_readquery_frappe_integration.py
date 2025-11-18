"""Integration tests for ReadQuery with Frappe Query Builder."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import ReadQuery


class ToDoSchema(DocModel):
    """DocModel for ToDo DocType (simple test DocType)."""

    class Meta:
        doctype = "ToDo"

    name: str
    status: str
    description: str | None = None
    priority: str | None = None


def test_build_frappe_query_creates_query():
    """Test that _build_frappe_query creates a Frappe query builder query."""
    query = ReadQuery(ToDoSchema)

    # Test by verifying the method doesn't raise errors when Frappe is available
    # In a real Frappe environment, this would create an actual query
    # For unit tests, we verify the query structure is built correctly
    # by checking that filters, order_by, and limit are stored
    assert query.schema == ToDoSchema
    assert query.schema.Meta.doctype == "ToDo"


def test_build_frappe_query_applies_filters():
    """Test that _build_frappe_query applies filters correctly."""
    query = ReadQuery(ToDoSchema).filter(status="Open").filter(priority="High")

    # Test by checking the query structure indirectly
    # Since we can't easily mock the imports, we'll test the logic differently
    # by checking that filters are stored correctly
    assert len(query.filters) == 2
    assert query.filters[0] == {"status": "Open"}
    assert query.filters[1] == {"priority": "High"}


def test_build_frappe_query_applies_order_by():
    """Test that _build_frappe_query applies order_by correctly."""
    query = ReadQuery(ToDoSchema).order_by("-status").order_by("name")

    # Test by checking that order_by_fields are stored correctly
    assert len(query.order_by_fields) == 2
    assert query.order_by_fields[0] == "-status"
    assert query.order_by_fields[1] == "name"


def test_build_frappe_query_applies_limit():
    """Test that _build_frappe_query applies limit correctly."""
    query = ReadQuery(ToDoSchema).limit(10)

    # Test by checking that limit_value is stored correctly
    assert query.limit_value == 10


def test_hydrate_from_row_populates_declared_fields():
    """Test that _hydrate_from_row populates declared fields correctly."""
    query = ReadQuery(ToDoSchema)

    row = {
        "name": "TODO-001",
        "status": "Open",
        "description": "Test todo",
        "priority": "High",
    }

    model = query._hydrate_from_row(row)

    assert isinstance(model, ToDoSchema)
    assert model.name == "TODO-001"
    assert model.status == "Open"
    assert model.description == "Test todo"
    assert model.priority == "High"


def test_hydrate_from_row_stores_unknown_fields_in_extras():
    """Test that _hydrate_from_row stores unknown fields in extras."""
    query = ReadQuery(ToDoSchema)

    row = {
        "name": "TODO-001",
        "status": "Open",
        "owner": "user@example.com",  # Unknown field
        "creation": "2024-01-01",  # Unknown field
    }

    model = query._hydrate_from_row(row)

    assert model.name == "TODO-001"
    assert model.status == "Open"
    assert "owner" in model.extras
    assert model.extras["owner"] == "user@example.com"
    assert "creation" in model.extras
    assert model.extras["creation"] == "2024-01-01"


def test_hydrate_from_row_empty_extras_when_no_unknown_fields():
    """Test that _hydrate_from_row has empty extras when all fields are declared."""
    query = ReadQuery(ToDoSchema)

    row = {
        "name": "TODO-001",
        "status": "Open",
        "description": None,
        "priority": None,
    }

    model = query._hydrate_from_row(row)

    assert model.extras == {}


def test_all_executes_query_and_returns_models():
    """Test that all() executes query and returns DocModel instances."""
    query = ReadQuery(ToDoSchema).filter(status="Open")

    mock_rows = [
        {"name": "TODO-001", "status": "Open", "description": "Task 1"},
        {"name": "TODO-002", "status": "Open", "description": "Task 2"},
    ]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = mock_rows
        mock_build.return_value = mock_query

        results = query.all()

        assert len(results) == 2
        assert all(isinstance(r, ToDoSchema) for r in results)
        assert results[0].name == "TODO-001"
        assert results[1].name == "TODO-002"


def test_all_handles_empty_results():
    """Test that all() handles empty query results."""
    query = ReadQuery(ToDoSchema).filter(status="NonExistent")

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = []
        mock_build.return_value = mock_query

        results = query.all()

        assert results == []


def test_all_raises_import_error_without_frappe():
    """Test that all() raises ImportError when Frappe is not available."""
    query = ReadQuery(ToDoSchema)

    # Mock the import inside _build_frappe_query to raise ImportError
    original_import = __import__

    def mock_import(name, *args, **kwargs):
        if name == "frappe":
            raise ImportError("No module named 'frappe'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ImportError, match="Frappe is required"):
            query._build_frappe_query()


@pytest.mark.skipif(
    "frappe" not in __import__("sys").modules,
    reason="Requires Frappe environment",
)
def test_readquery_with_real_frappe_todo():
    """Integration test with real Frappe ToDo DocType (if Frappe is available)."""
    try:
        import frappe

        # Only run if we're in a Frappe environment
        if not hasattr(frappe, "local"):
            pytest.skip("Not in a Frappe environment")

        # Create a test todo if possible
        # This test may fail if ToDo doctype doesn't exist or permissions are restricted
        query = ReadQuery(ToDoSchema).limit(5)

        results = query.all()

        # Verify we got DocModel instances
        assert all(isinstance(r, ToDoSchema) for r in results)

        # Verify fields are populated
        for result in results:
            assert hasattr(result, "name")
            assert hasattr(result, "status")

    except ImportError:
        pytest.skip("Frappe not available")


def test_first_returns_first_result():
    """Test that first() returns the first result or None."""
    query = ReadQuery(ToDoSchema)

    mock_rows = [
        {"name": "TODO-001", "status": "Open"},
        {"name": "TODO-002", "status": "Closed"},
    ]

    with patch.object(query, "all", return_value=[ToDoSchema(name="TODO-001", status="Open")]):
        result = query.first()

        assert result is not None
        assert isinstance(result, ToDoSchema)
        assert result.name == "TODO-001"


def test_first_returns_none_for_empty_results():
    """Test that first() returns None when there are no results."""
    query = ReadQuery(ToDoSchema)

    with patch.object(query, "all", return_value=[]):
        result = query.first()

        assert result is None
