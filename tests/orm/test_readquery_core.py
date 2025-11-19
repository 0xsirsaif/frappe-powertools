"""Core tests for ReadQuery class."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import ReadQuery


class TrainingBatchSchema(DocModel):
    """Dummy DocModel for testing."""

    class Meta:
        doctype = "Training Batch"

    name: str
    status: str
    start_date: str
    program: str
    score: int | None = None


def test_readquery_chaining_builds_internal_state():
    """Test that chaining methods builds up the correct internal state."""
    query = ReadQuery(TrainingBatchSchema)

    # Chain multiple methods
    query = (
        query.filter(status="Completed")
        .filter(program="PROG-001")
        .order_by("-start_date")
        .order_by("name")
        .limit(10)
        .prefetch("participants")
        .prefetch("items")
        .select_related("program")
        .select_related("instructor")
    )

    # Verify filters
    assert len(query.filters) == 2
    assert query.filters[0] == {"status": "Completed"}
    assert query.filters[1] == {"program": "PROG-001"}

    # Verify order_by_fields
    assert len(query.order_by_fields) == 2
    assert query.order_by_fields[0] == "-start_date"
    assert query.order_by_fields[1] == "name"

    # Verify limit_value
    assert query.limit_value == 10

    # Verify prefetch_fields
    assert len(query.prefetch_fields) == 2
    assert "participants" in query.prefetch_fields
    assert "items" in query.prefetch_fields

    # Verify select_related_fields
    assert len(query.select_related_fields) == 2
    assert "program" in query.select_related_fields
    assert "instructor" in query.select_related_fields


def test_readquery_filter_returns_self():
    """Test that filter() returns self for chaining."""
    query = ReadQuery(TrainingBatchSchema)
    result = query.filter(status="Active")

    assert result is query


def test_readquery_order_by_returns_self():
    """Test that order_by() returns self for chaining."""
    query = ReadQuery(TrainingBatchSchema)
    result = query.order_by("name")

    assert result is query


def test_readquery_limit_returns_self():
    """Test that limit() returns self for chaining."""
    query = ReadQuery(TrainingBatchSchema)
    result = query.limit(5)

    assert result is query


def test_readquery_prefetch_returns_self():
    """Test that prefetch() returns self for chaining."""
    query = ReadQuery(TrainingBatchSchema)
    result = query.prefetch("participants")

    assert result is query


def test_readquery_select_related_returns_self():
    """Test that select_related() returns self for chaining."""
    query = ReadQuery(TrainingBatchSchema)
    result = query.select_related("program")

    assert result is query


def test_readquery_all_raises_import_error_without_frappe():
    """Test that all() raises ImportError when Frappe is not available."""
    from unittest.mock import patch

    query = ReadQuery(TrainingBatchSchema)

    # Mock the import inside _build_frappe_query to raise ImportError
    original_import = __import__

    def mock_import(name, *args, **kwargs):
        if name == "frappe":
            raise ImportError("No module named 'frappe'")
        return original_import(name, *args, **kwargs)

    with patch("builtins.__import__", side_effect=mock_import):
        with pytest.raises(ImportError, match="Frappe is required"):
            query.all()


def test_readquery_first_calls_all_and_returns_first_or_none():
    """Test that first() calls all() and returns first element or None."""
    query = ReadQuery(TrainingBatchSchema)

    # Test with non-empty results
    with patch.object(query, "all", return_value=["first", "second", "third"]):
        result = query.first()
        assert result == "first"
        query.all.assert_called_once()

    # Test with empty results
    query2 = ReadQuery(TrainingBatchSchema)
    with patch.object(query2, "all", return_value=[]):
        result = query2.first()
        assert result is None
        query2.all.assert_called_once()


def test_readquery_first_sets_limit_to_one():
    """Test that first() sets limit_value to 1."""
    query = ReadQuery(TrainingBatchSchema)

    # Initially no limit
    assert query.limit_value is None

    # Mock all() to avoid NotImplementedError
    with patch.object(query, "all", return_value=[]):
        query.first()

    # Limit should be set to 1
    assert query.limit_value == 1


def test_readquery_multiple_filters_accumulate():
    """Test that multiple filter() calls accumulate filters."""
    query = ReadQuery(TrainingBatchSchema)

    query.filter(status="Active").filter(program="PROG-001").filter(year=2024)

    assert len(query.filters) == 3
    assert query.filters[0] == {"status": "Active"}
    assert query.filters[1] == {"program": "PROG-001"}
    assert query.filters[2] == {"year": 2024}


def test_readquery_multiple_order_by_accumulate():
    """Test that multiple order_by() calls accumulate fields."""
    query = ReadQuery(TrainingBatchSchema)

    query.order_by("-start_date").order_by("name").order_by("-created")

    assert len(query.order_by_fields) == 3
    assert query.order_by_fields == ["-start_date", "name", "-created"]


def test_readquery_multiple_prefetch_accumulate():
    """Test that multiple prefetch() calls accumulate fields."""
    query = ReadQuery(TrainingBatchSchema)

    query.prefetch("participants").prefetch("items").prefetch("attachments")

    assert len(query.prefetch_fields) == 3
    assert "participants" in query.prefetch_fields
    assert "items" in query.prefetch_fields
    assert "attachments" in query.prefetch_fields


def test_readquery_multiple_select_related_accumulate():
    """Test that multiple select_related() calls accumulate fields."""
    query = ReadQuery(TrainingBatchSchema)

    query.select_related("program").select_related("instructor").select_related("venue")

    assert len(query.select_related_fields) == 3
    assert "program" in query.select_related_fields
    assert "instructor" in query.select_related_fields
    assert "venue" in query.select_related_fields


def test_readquery_limit_overwrites_previous():
    """Test that limit() overwrites the previous limit value."""
    query = ReadQuery(TrainingBatchSchema)

    query.limit(10)
    assert query.limit_value == 10

    query.limit(20)
    assert query.limit_value == 20

    # Should not accumulate, just overwrite
    assert query.limit_value == 20


def test_query_for_creates_readquery():
    """Test that query_for() creates a ReadQuery instance."""
    from frappe_powertools.orm import query_for

    query = query_for(TrainingBatchSchema)

    assert isinstance(query, ReadQuery)
    assert query.schema is TrainingBatchSchema


def test_query_for_allows_chaining():
    """Test that query_for() returns a ReadQuery that can be chained."""
    from frappe_powertools.orm import query_for

    query = query_for(TrainingBatchSchema)
    query = query.filter(status="Active").order_by("name").limit(5)

    assert len(query.filters) == 1
    assert query.filters[0] == {"status": "Active"}
    assert query.order_by_fields == ["name"]
    assert query.limit_value == 5


def test_attach_manager_attaches_objects_descriptor():
    """Test that attach_manager() attaches a ManagerDescriptor to the schema."""
    from frappe_powertools.orm import attach_manager

    @attach_manager
    class MySchema(DocModel):
        class Meta:
            doctype = "My Schema"

        name: str

    # Should have objects attribute
    assert hasattr(MySchema, "objects")

    # Accessing .objects should return a ReadQuery
    query1 = MySchema.objects
    assert isinstance(query1, ReadQuery)
    assert query1.schema is MySchema

    # Each access should return a new ReadQuery instance
    query2 = MySchema.objects
    assert query1 is not query2  # Different instances
    assert query1.schema is query2.schema  # But same schema


def test_attach_manager_returns_schema_class():
    """Test that attach_manager() returns the schema class for chaining."""
    from frappe_powertools.orm import attach_manager

    @attach_manager
    class MySchema(DocModel):
        class Meta:
            doctype = "My Schema 2"

        name: str

    # Should be able to use the class normally
    assert MySchema.Meta.doctype == "My Schema 2"
    assert hasattr(MySchema, "objects")


def test_readquery_single_filter_with_multiple_kwargs():
    """Test that multiple keyword args in a single filter() call combine with AND."""
    query = ReadQuery(TrainingBatchSchema).filter(status="Active", program="PROG-001")

    assert len(query.filters) == 1
    assert query.filters[0] == {"status": "Active", "program": "PROG-001"}


def test_readquery_mixed_single_and_multiple_filter_calls():
    """Test that mixing single and multiple filter calls works correctly."""
    query = (
        ReadQuery(TrainingBatchSchema)
        .filter(status="Active", program="PROG-001")
        .filter(name="BATCH-001")
    )

    assert len(query.filters) == 2
    assert query.filters[0] == {"status": "Active", "program": "PROG-001"}
    assert query.filters[1] == {"name": "BATCH-001"}


def test_readquery_filter_with_double_underscore_field_name():
    """Test that fields with double underscores are treated as literal field names."""
    query = ReadQuery(TrainingBatchSchema).filter(**{"field__name": "value"})

    assert len(query.filters) == 1
    assert "field__name" in query.filters[0]
    assert query.filters[0]["field__name"] == "value"


def test_readquery_filters_use_equality_semantics():
    """Test that filters use equality semantics (baseline behavior)."""
    query = ReadQuery(TrainingBatchSchema).filter(status="Active").filter(program="PROG-001")

    # Verify filters are stored correctly (equality semantics - no lookup suffixes)
    assert len(query.filters) == 2
    assert query.filters[0] == {"status": "Active"}
    assert query.filters[1] == {"program": "PROG-001"}


def test_readquery_empty_filters():
    """Test that queries with no filters have empty filter list."""
    query = ReadQuery(TrainingBatchSchema)

    # Verify no filters are stored
    assert len(query.filters) == 0
    assert query.filters == []


def test_readquery_filter_exact_lookup_still_works():
    """Test that filter without lookup suffix still works (exact lookup)."""
    query = ReadQuery(TrainingBatchSchema).filter(status="Active")

    assert len(query.filters) == 1
    assert query.filters[0] == {"status": "Active"}


def test_readquery_filter_comparison_lookups():
    """Test that comparison lookups (gt, gte, lt, lte) work correctly."""
    query = (
        ReadQuery(TrainingBatchSchema)
        .filter(score__gt=80)
        .filter(score__gte=50)
        .filter(score__lt=100)
        .filter(score__lte=90)
    )

    assert len(query.filters) == 4
    assert query.filters[0] == {"score__gt": 80}
    assert query.filters[1] == {"score__gte": 50}
    assert query.filters[2] == {"score__lt": 100}
    assert query.filters[3] == {"score__lte": 90}


def test_readquery_filter_range_lookup():
    """Test that range lookup works correctly."""
    from datetime import date

    query = ReadQuery(TrainingBatchSchema).filter(
        start_date__range=(date(2025, 1, 1), date(2025, 3, 31))
    )

    assert len(query.filters) == 1
    assert "start_date__range" in query.filters[0]
    range_value = query.filters[0]["start_date__range"]
    assert isinstance(range_value, tuple)
    assert len(range_value) == 2
    assert range_value[0] == date(2025, 1, 1)
    assert range_value[1] == date(2025, 3, 31)


def test_readquery_filter_comparison_lookups_build_conditions():
    """Test that comparison lookups build correct PyPika conditions."""
    from frappe_powertools.orm.query import ParsedLookup

    query = ReadQuery(TrainingBatchSchema)
    mock_table = MagicMock()

    # Create mock field that supports comparison operators
    def create_mock_field():
        mock_field = MagicMock()
        # Make comparison operators return mock conditions
        mock_field.__gt__ = MagicMock(return_value=MagicMock())
        mock_field.__ge__ = MagicMock(return_value=MagicMock())
        mock_field.__lt__ = MagicMock(return_value=MagicMock())
        mock_field.__le__ = MagicMock(return_value=MagicMock())
        mock_field.__eq__ = MagicMock(return_value=MagicMock())
        mock_field.between = MagicMock(return_value=MagicMock())
        return mock_field

    mock_table.__getitem__ = MagicMock(side_effect=lambda key: create_mock_field())

    # Test gt lookup
    parsed_gt = ParsedLookup(field_name="score", lookup="gt", value=80)
    condition_gt = query._build_condition(mock_table, parsed_gt)
    assert condition_gt is not None

    # Test lte lookup
    parsed_lte = ParsedLookup(field_name="score", lookup="lte", value=100)
    condition_lte = query._build_condition(mock_table, parsed_lte)
    assert condition_lte is not None

    # Test exact lookup
    parsed_exact = ParsedLookup(field_name="status", lookup="exact", value="Active")
    condition_exact = query._build_condition(mock_table, parsed_exact)
    assert condition_exact is not None

    # Test range lookup
    parsed_range = ParsedLookup(field_name="score", lookup="range", value=(10, 20))
    condition_range = query._build_condition(mock_table, parsed_range)
    assert condition_range is not None


def test_readquery_filter_unknown_lookup_raises_error():
    """Test that unknown lookup raises ValueError."""
    from frappe_powertools.orm.query import ParsedLookup

    query = ReadQuery(TrainingBatchSchema)
    mock_table = MagicMock()
    mock_field = MagicMock()
    mock_table.__getitem__.return_value = mock_field

    parsed = ParsedLookup(field_name="score", lookup="foo", value=10)

    with pytest.raises(ValueError, match="Unsupported lookup 'foo' on field 'score'"):
        query._build_condition(mock_table, parsed)


def test_readquery_filter_range_invalid_value_raises_error():
    """Test that range lookup with invalid value raises ValueError."""
    from frappe_powertools.orm.query import ParsedLookup

    query = ReadQuery(TrainingBatchSchema)
    mock_table = MagicMock()
    mock_field = MagicMock()
    mock_table.__getitem__.return_value = mock_field

    parsed = ParsedLookup(field_name="score", lookup="range", value=(10,))

    with pytest.raises(ValueError, match="range lookup requires a tuple or list of 2 values"):
        query._build_condition(mock_table, parsed)


def test_readquery_filter_mixed_exact_and_comparison_lookups():
    """Test that exact and comparison lookups can be mixed."""
    query = (
        ReadQuery(TrainingBatchSchema)
        .filter(status="Active")
        .filter(score__gt=50)
        .filter(program="PROG-001")
        .filter(score__lte=100)
    )

    assert len(query.filters) == 4
    assert query.filters[0] == {"status": "Active"}
    assert query.filters[1] == {"score__gt": 50}
    assert query.filters[2] == {"program": "PROG-001"}
    assert query.filters[3] == {"score__lte": 100}
