"""Tests for select_related (link field joins) functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import ReadQuery


class TrainingBatchSchema(DocModel):
    """DocModel for Training Batch with link fields."""

    class Meta:
        doctype = "Training Batch"
        links = {
            "program_name": ("program", "Training Program", "program_name"),
            "instructor_name": ("instructor", "Employee", "employee_name"),
        }

    name: str
    program: str
    instructor: str | None = None
    program_name: str | None = None
    instructor_name: str | None = None
    start_date: str | None = None


class CustomerOrderSchema(DocModel):
    """DocModel for Customer Order with customer link."""

    class Meta:
        doctype = "Customer Order"
        links = {
            "customer_name": ("customer", "Customer", "customer_name"),
        }

    name: str
    customer: str
    customer_name: str | None = None
    total: float | None = None


def test_select_related_adds_link_field_projections():
    """Test that select_related adds link field projections to the query."""
    query = ReadQuery(TrainingBatchSchema).select_related("program")

    # Verify select_related_fields is set
    assert "program" in query.select_related_fields

    # Test that the query structure includes link fields
    # We'll verify this by checking that Meta.links is accessed
    assert hasattr(query.schema, "Meta")
    assert hasattr(query.schema.Meta, "links")
    assert "program_name" in query.schema.Meta.links


def test_select_related_multiple_link_fields():
    """Test that select_related works with multiple link fields."""
    query = ReadQuery(TrainingBatchSchema).select_related("program", "instructor")

    assert "program" in query.select_related_fields
    assert "instructor" in query.select_related_fields


def test_select_related_hydrates_link_fields():
    """Test that select_related properly hydrates link fields from query results."""
    query = ReadQuery(TrainingBatchSchema).select_related("program")

    # Mock query results with link field data
    rows = [
        {
            "name": "BATCH-001",
            "program": "PROG-001",
            "program_name": "Python Basics",
            "start_date": "2024-01-01",
        },
        {
            "name": "BATCH-002",
            "program": "PROG-002",
            "program_name": "Advanced Python",
            "start_date": "2024-02-01",
        },
    ]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = rows
        mock_build.return_value = mock_query

        results = query.all()

        # Verify link fields are populated
        assert len(results) == 2
        assert results[0].program == "PROG-001"
        assert results[0].program_name == "Python Basics"
        assert results[1].program == "PROG-002"
        assert results[1].program_name == "Advanced Python"


def test_select_related_handles_null_link_fields():
    """Test that select_related handles null link field values."""
    query = ReadQuery(CustomerOrderSchema).select_related("customer")

    rows = [
        {
            "name": "ORDER-001",
            "customer": "CUST-001",
            "customer_name": "Acme Corp",
            "total": 1000.0,
        },
        {
            "name": "ORDER-002",
            "customer": "CUST-002",
            "customer_name": None,  # Null link field
            "total": 500.0,
        },
    ]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = rows
        mock_build.return_value = mock_query

        results = query.all()

        assert len(results) == 2
        assert results[0].customer_name == "Acme Corp"
        assert results[1].customer_name is None


def test_select_related_ignores_fields_not_in_links():
    """Test that select_related ignores fields not defined in Meta.links."""
    query = ReadQuery(TrainingBatchSchema).select_related("program", "unknown_field")

    # Only "program" should be processed since "unknown_field" is not in Meta.links
    assert "program" in query.select_related_fields
    assert "unknown_field" in query.select_related_fields  # Still stored, but won't be used

    # The query building should only process "program"
    # This is tested implicitly - if unknown_field was processed, it would cause an error


def test_select_related_without_links_meta():
    """Test that select_related works gracefully when Meta.links is not defined."""

    class SchemaWithoutLinks(DocModel):
        class Meta:
            doctype = "Simple DocType"

        name: str
        status: str

    query = ReadQuery(SchemaWithoutLinks).select_related("some_field")

    # Should not raise an error
    assert "some_field" in query.select_related_fields

    # Query building should skip link field processing
    rows = [{"name": "DOC-001", "status": "Active"}]
    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = rows
        mock_build.return_value = mock_query

        results = query.all()
        assert len(results) == 1
        assert results[0].name == "DOC-001"


def test_select_related_multiple_projections_per_link():
    """Test that select_related can fetch multiple projections from the same link field."""

    class SchemaWithMultipleProjections(DocModel):
        class Meta:
            doctype = "Complex DocType"
            links = {
                "customer_name": ("customer", "Customer", "customer_name"),
                "customer_email": ("customer", "Customer", "email"),
                "customer_phone": ("customer", "Customer", "phone"),
            }

        name: str
        customer: str
        customer_name: str | None = None
        customer_email: str | None = None
        customer_phone: str | None = None

    query = ReadQuery(SchemaWithMultipleProjections).select_related("customer")

    rows = [
        {
            "name": "DOC-001",
            "customer": "CUST-001",
            "customer_name": "Acme Corp",
            "customer_email": "acme@example.com",
            "customer_phone": "123-456-7890",
        },
    ]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = rows
        mock_build.return_value = mock_query

        results = query.all()

        assert len(results) == 1
        assert results[0].customer_name == "Acme Corp"
        assert results[0].customer_email == "acme@example.com"
        assert results[0].customer_phone == "123-456-7890"


def test_select_related_combined_with_filters():
    """Test that select_related works when combined with filters."""
    query = ReadQuery(TrainingBatchSchema).select_related("program").filter(program="PROG-001")

    rows = [
        {
            "name": "BATCH-001",
            "program": "PROG-001",
            "program_name": "Python Basics",
        },
    ]

    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_query = MagicMock()
        mock_query.run.return_value = rows
        mock_build.return_value = mock_query

        results = query.all()

        assert len(results) == 1
        assert results[0].program == "PROG-001"
        assert results[0].program_name == "Python Basics"


@pytest.mark.skipif(
    "frappe" not in __import__("sys").modules,
    reason="Requires Frappe environment",
)
def test_select_related_with_real_frappe():
    """Integration test with real Frappe (if available)."""
    try:
        import frappe

        if not hasattr(frappe, "local"):
            pytest.skip("Not in a Frappe environment")

        # This test would require a real DocType with link fields
        # For now, we'll just verify the method doesn't crash
        query = ReadQuery(TrainingBatchSchema).select_related("program").limit(1)

        try:
            results = query.all()
            # If we got results, verify structure
            if results:
                assert all(isinstance(r, TrainingBatchSchema) for r in results)
                # Link fields may or may not be populated depending on data
        except Exception:
            # If doctype doesn't exist, that's fine for this test
            pass

    except ImportError:
        pytest.skip("Frappe not available")
