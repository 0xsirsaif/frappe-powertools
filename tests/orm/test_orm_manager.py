"""Tests for ORM manager (.objects) functionality."""

from __future__ import annotations

from unittest.mock import MagicMock, patch


from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import ReadQuery, attach_manager, query_for


class SimpleSchema(DocModel):
    """Simple DocModel for testing."""

    class Meta:
        doctype = "Simple DocType"

    name: str
    status: str
    title: str | None = None


def test_attach_manager_exposes_objects_property():
    """Test that attach_manager exposes .objects property on DocModel."""
    # Attach manager to the schema
    schema_with_manager = attach_manager(SimpleSchema)

    # Verify .objects is accessible
    assert hasattr(schema_with_manager, "objects")

    # Access .objects should return a ReadQuery instance
    query = schema_with_manager.objects
    assert isinstance(query, ReadQuery)
    assert query.schema == SimpleSchema


def test_attach_manager_returns_fresh_query_each_time():
    """Test that each access to .objects returns a fresh ReadQuery instance."""
    schema_with_manager = attach_manager(SimpleSchema)

    query1 = schema_with_manager.objects
    query2 = schema_with_manager.objects

    # Should be different instances
    assert query1 is not query2
    # But both should be bound to the same schema
    assert query1.schema == query2.schema == SimpleSchema


def test_attach_manager_works_as_decorator():
    """Test that attach_manager works as a class decorator."""

    @attach_manager
    class DecoratedSchema(DocModel):
        class Meta:
            doctype = "Decorated DocType"

        name: str
        status: str

    # Verify .objects is accessible
    assert hasattr(DecoratedSchema, "objects")
    query = DecoratedSchema.objects
    assert isinstance(query, ReadQuery)
    assert query.schema == DecoratedSchema


def test_attach_manager_allows_chaining():
    """Test that .objects allows method chaining."""
    schema_with_manager = attach_manager(SimpleSchema)

    query = schema_with_manager.objects.filter(status="Active").order_by("-name").limit(10)

    assert isinstance(query, ReadQuery)
    assert len(query.filters) == 1
    assert query.filters[0] == {"status": "Active"}
    assert query.order_by_fields == ["-name"]
    assert query.limit_value == 10


def test_attach_manager_with_prefetch_and_select_related():
    """Test that .objects works with prefetch and select_related."""

    class SchemaWithRelations(DocModel):
        class Meta:
            doctype = "Schema With Relations"
            children = {"items": SimpleSchema}
            links = {
                "customer_name": ("customer", "Customer", "customer_name"),
            }

        name: str
        customer: str
        customer_name: str | None = None

    schema_with_manager = attach_manager(SchemaWithRelations)

    query = schema_with_manager.objects.prefetch("items").select_related("customer")

    assert isinstance(query, ReadQuery)
    assert "items" in query.prefetch_fields
    assert "customer" in query.select_related_fields


def test_query_for_helper_function():
    """Test that query_for helper creates ReadQuery instances."""
    query = query_for(SimpleSchema)

    assert isinstance(query, ReadQuery)
    assert query.schema == SimpleSchema


def test_query_for_returns_fresh_instance():
    """Test that query_for returns a fresh instance each time."""
    query1 = query_for(SimpleSchema)
    query2 = query_for(SimpleSchema)

    # Should be different instances
    assert query1 is not query2
    # But both should be bound to the same schema
    assert query1.schema == query2.schema == SimpleSchema


def test_objects_manager_executes_queries():
    """Test that .objects manager can execute queries."""
    schema_with_manager = attach_manager(SimpleSchema)

    rows = [
        {"name": "DOC-001", "status": "Active", "title": "Test 1"},
        {"name": "DOC-002", "status": "Active", "title": "Test 2"},
    ]

    # Get the query object and patch its _build_frappe_query method
    query = schema_with_manager.objects.filter(status="Active")
    with patch.object(query, "_build_frappe_query") as mock_build:
        mock_frappe_query = MagicMock()
        mock_frappe_query.run.return_value = rows
        mock_build.return_value = mock_frappe_query

        results = query.all()

        assert len(results) == 2
        assert all(isinstance(r, SimpleSchema) for r in results)
        assert results[0].name == "DOC-001"
        assert results[1].name == "DOC-002"


def test_objects_manager_first_method():
    """Test that .objects manager supports .first() method."""
    schema_with_manager = attach_manager(SimpleSchema)

    # Mock the all() method directly since first() calls it
    query = schema_with_manager.objects
    with patch.object(query, "all", return_value=[SimpleSchema(name="DOC-001", status="Active")]):
        result = query.first()

        assert result is not None
        assert isinstance(result, SimpleSchema)
        assert result.name == "DOC-001"


def test_attach_manager_preserves_class_identity():
    """Test that attach_manager preserves the class identity."""
    original_schema = SimpleSchema

    schema_with_manager = attach_manager(SimpleSchema)

    # Should be the same class
    assert schema_with_manager is SimpleSchema
    assert schema_with_manager is original_schema


def test_multiple_schemas_with_managers():
    """Test that multiple schemas can have managers independently."""

    @attach_manager
    class Schema1(DocModel):
        class Meta:
            doctype = "Schema 1"

        name: str

    @attach_manager
    class Schema2(DocModel):
        class Meta:
            doctype = "Schema 2"

        name: str

    # Each should have its own .objects manager
    query1 = Schema1.objects
    query2 = Schema2.objects

    assert query1.schema == Schema1
    assert query2.schema == Schema2
    assert query1.schema != query2.schema
