"""Basic tests for DocModel base class."""

from __future__ import annotations

import pytest
from pydantic.type_adapter import TypeAdapter

from frappe_powertools.doctype_schema import DocModel


class MyDoc(DocModel):
    """Simple test DocModel."""

    class Meta:
        doctype = "My Doc"

    name: str
    age: int


def test_docmodel_adapter_is_cached():
    """Test that DocModel.adapter() returns the same TypeAdapter instance on repeated calls."""
    # First call should create and cache the adapter
    adapter1 = MyDoc.adapter()
    assert isinstance(adapter1, TypeAdapter)

    # Second call should return the same instance
    adapter2 = MyDoc.adapter()
    assert adapter1 is adapter2

    # Third call should also return the same instance
    adapter3 = MyDoc.adapter()
    assert adapter1 is adapter3
    assert adapter2 is adapter3


def test_docmodel_extras_bucket():
    """Test that unknown fields are stored in the extras bucket."""
    # Create data with both known and unknown fields
    data = {"name": "Alice", "age": 30, "unknown": "value", "another_unknown": 42}

    # Validate using adapter
    model = MyDoc.adapter().validate_python(data)

    # Known fields should be populated
    assert model.name == "Alice"
    assert model.age == 30

    # Unknown fields should be in extras
    assert "unknown" in model.extras
    assert model.extras["unknown"] == "value"
    assert "another_unknown" in model.extras
    assert model.extras["another_unknown"] == 42


def test_docmodel_extras_empty_when_no_unknown_fields():
    """Test that extras is empty when all fields are declared."""
    data = {"name": "Bob", "age": 25}

    model = MyDoc.adapter().validate_python(data)

    assert model.name == "Bob"
    assert model.age == 25
    assert model.extras == {}


def test_docmodel_register():
    """Test that DocModel.register() registers the model in the registry."""
    from frappe_powertools.doctype_schema.schema import _registry

    # Clear registry first
    _registry.clear()

    # Register the model
    MyDoc.register()

    # Verify it's registered
    registered = _registry.get("My Doc")
    assert registered is MyDoc

    # Try to register again with same model (should not raise)
    MyDoc.register()
    assert _registry.get("My Doc") is MyDoc

    # Clean up
    _registry.clear()


def test_docmodel_register_requires_meta_doctype():
    """Test that register() raises an error if Meta.doctype is missing."""

    class InvalidDoc(DocModel):
        # Missing Meta class
        name: str

    with pytest.raises(ValueError, match="must define a Meta class"):
        InvalidDoc.register()


def test_docmodel_register_prevents_duplicate_doctype():
    """Test that register() prevents registering different models for the same doctype."""

    class AnotherDoc(DocModel):
        class Meta:
            doctype = "My Doc"  # Same as MyDoc

        name: str

    from frappe_powertools.doctype_schema.schema import _registry

    # Clear and register MyDoc first
    _registry.clear()
    MyDoc.register()

    # Try to register AnotherDoc with same doctype - should raise
    with pytest.raises(ValueError, match="already registered"):
        AnotherDoc.register()

    # Clean up
    _registry.clear()
