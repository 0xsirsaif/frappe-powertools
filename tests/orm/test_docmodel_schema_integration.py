"""Integration tests for DocModel with schema validation."""

from __future__ import annotations

import pytest

from frappe_powertools.doctype_schema import DocModel, PydanticValidationError, use_schema


class PersonSchema(DocModel):
    """Test DocModel for Person."""

    class Meta:
        doctype = "Person"

    name: str
    age: int


class DummyDocument:
    """Fake Document-like class for testing."""

    def __init__(self, **data):
        self._data = data.copy()
        self._validate_calls = 0
        for key, value in data.items():
            setattr(self, key, value)

    def as_dict(self):
        return self._data.copy()

    def validate(self):
        self._validate_calls += 1
        return "validated"


def test_use_schema_with_docmodel_runs_validation():
    """Test that use_schema with DocModel runs validation before validate method."""

    @use_schema(PersonSchema)
    class PersonDoc(DummyDocument):
        pass

    # Valid data should pass
    doc = PersonDoc(name="Alice", age=30)
    result = doc.validate()

    assert result == "validated"
    assert doc._validate_calls == 1
    assert hasattr(doc, "_schema_model")
    assert isinstance(doc._schema_model, PersonSchema)
    assert doc._schema_model.name == "Alice"
    assert doc._schema_model.age == 30


def test_use_schema_with_docmodel_normalizes_data():
    """Test that use_schema normalizes document fields when normalize=True (default)."""

    @use_schema(PersonSchema, normalize=True)
    class PersonDoc(DummyDocument):
        pass

    # Age as string should be normalized to int
    doc = PersonDoc(name="Bob", age="25")
    doc.validate()

    # After normalization, age should be int
    assert doc.age == 25
    assert isinstance(doc.age, int)
    assert doc._schema_model.age == 25


def test_use_schema_with_docmodel_raises_on_invalid_data():
    """Test that use_schema raises validation error for invalid data."""

    @use_schema(PersonSchema, on_error="raise")
    class PersonDoc(DummyDocument):
        pass

    # Invalid data: age is not an integer
    doc = PersonDoc(name="Charlie", age="not_a_number")

    with pytest.raises(PydanticValidationError) as exc_info:
        doc.validate()

    assert "age" in str(exc_info.value).lower() or "age" in str(exc_info.value.errors)


def test_use_schema_with_docmodel_handles_missing_required_fields():
    """Test that use_schema catches missing required fields."""

    @use_schema(PersonSchema, on_error="raise")
    class PersonDoc(DummyDocument):
        pass

    # Missing required field 'name'
    doc = PersonDoc(age=30)

    with pytest.raises(PydanticValidationError) as exc_info:
        doc.validate()

    assert "name" in str(exc_info.value).lower() or any(
        "name" in str(err) for err in exc_info.value.errors
    )


def test_use_schema_with_docmodel_stores_extras():
    """Test that use_schema preserves unknown fields in extras."""

    @use_schema(PersonSchema)
    class PersonDoc(DummyDocument):
        pass

    # Data with unknown fields
    doc = PersonDoc(name="David", age=35, email="david@example.com", city="NYC")
    doc.validate()

    # Unknown fields should be in extras
    assert doc._schema_model.extras.get("email") == "david@example.com"
    assert doc._schema_model.extras.get("city") == "NYC"


def test_use_schema_with_docmodel_runs_after_original_logic():
    """Test that use_schema can run validation after original validate method."""
    events = []

    @use_schema(PersonSchema, order="after")
    class PersonDoc(DummyDocument):
        def validate(self):
            events.append("validate")
            return super().validate()

    doc = PersonDoc(name="Eve", age=28)
    result = doc.validate()

    assert result == "validated"
    assert events == ["validate"]
    assert hasattr(doc, "_schema_model")


def test_use_schema_with_docmodel_uses_cached_adapter():
    """Test that use_schema uses DocModel's cached adapter."""
    # Get adapter before using schema
    adapter1 = PersonSchema.adapter()

    @use_schema(PersonSchema)
    class PersonDoc(DummyDocument):
        pass

    # Use the schema
    doc = PersonDoc(name="Frank", age=40)
    doc.validate()

    # Adapter should be the same cached instance
    adapter2 = PersonSchema.adapter()
    assert adapter1 is adapter2


def test_use_schema_with_docmodel_custom_stash_attr():
    """Test that use_schema respects custom stash_attr parameter."""

    @use_schema(PersonSchema, stash_attr="_my_model")
    class PersonDoc(DummyDocument):
        pass

    doc = PersonDoc(name="Grace", age=32)
    doc.validate()

    # Should use custom stash attribute
    assert hasattr(doc, "_my_model")
    assert isinstance(doc._my_model, PersonSchema)
    assert not hasattr(doc, "_schema_model")  # Default should not be used


def test_pydantic_schema_still_works_with_regular_basemodel():
    """Test that pydantic_schema still works with regular BaseModel (backwards compatibility)."""
    from pydantic import BaseModel
    from frappe_powertools.doctype_schema import pydantic_schema

    class RegularSchema(BaseModel):
        name: str
        age: int

    @pydantic_schema(RegularSchema)
    class RegularDoc(DummyDocument):
        pass

    # Should work exactly as before
    doc = RegularDoc(name="Henry", age=45)
    result = doc.validate()

    assert result == "validated"
    assert doc._validate_calls == 1
    assert hasattr(doc, "_pydantic_model")
    assert isinstance(doc._pydantic_model, RegularSchema)
