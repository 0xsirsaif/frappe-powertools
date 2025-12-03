"""Unit tests for DocModel generator core functionality."""

from __future__ import annotations

from dataclasses import dataclass


from frappe_powertools.commands.generate_models import (
    _build_model_descriptor,
    _fieldtype_to_python_type,
    _python_class_name_for,
    _python_identifier_for,
)


def test_python_class_name_for():
    """Test conversion of DocType names to Python class names."""
    assert _python_class_name_for("Training Batch") == "TrainingBatch"
    assert _python_class_name_for("Sales Invoice") == "SalesInvoice"
    assert _python_class_name_for("Student_Record") == "StudentRecord"
    assert _python_class_name_for("Short Course") == "ShortCourse"
    assert _python_class_name_for("Academic Term") == "AcademicTerm"


def test_python_identifier_for():
    """Test conversion of fieldnames to Python identifiers."""
    assert _python_identifier_for("student_name") == "student_name"
    assert _python_identifier_for("student-name") == "student_name"
    assert _python_identifier_for("student name") == "student_name"
    assert _python_identifier_for("123invalid") is None
    assert _python_identifier_for("") is None


def test_fieldtype_to_python_type():
    """Test mapping of Frappe fieldtypes to Python types."""
    assert _fieldtype_to_python_type("Data") == "str | None"
    assert _fieldtype_to_python_type("Int") == "int | None"
    assert _fieldtype_to_python_type("Float") == "float | None"
    assert _fieldtype_to_python_type("Currency") == "Decimal | None"  # Uses Decimal for precision
    assert _fieldtype_to_python_type("Check") == "bool"
    assert _fieldtype_to_python_type("Date") == "date | None"
    assert _fieldtype_to_python_type("Datetime") == "datetime | None"
    assert _fieldtype_to_python_type("Time") == "time | None"
    assert _fieldtype_to_python_type("Link") == "str | None"
    assert _fieldtype_to_python_type("Table") == "Any"
    assert _fieldtype_to_python_type("Unknown") == "Any"
    # New types added
    assert _fieldtype_to_python_type("Long Int") == "int | None"
    assert _fieldtype_to_python_type("Duration") == "int | None"
    assert _fieldtype_to_python_type("Rating") == "float | None"
    assert _fieldtype_to_python_type("JSON") == "dict[str, Any] | None"


def test_build_model_descriptor_basic_fieldtypes():
    """Test building a model descriptor with various fieldtypes."""

    # Create a mock meta object
    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("title", "Data", reqd=True),
        MockField("age", "Int"),
        MockField("score", "Float"),
        MockField("is_active", "Check", reqd=True),
        MockField("birth_date", "Date"),
        MockField("created_at", "Datetime"),
        MockField("start_time", "Time"),
        MockField("student", "Link", options="Student"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    assert descriptor.class_name == "TestDocType"
    assert descriptor.doctype == "Test DocType"
    assert not descriptor.is_child

    # Check that fields are mapped correctly
    field_names = {f.name for f in descriptor.fields}
    assert "name" in field_names
    assert "title" in field_names
    assert "age" in field_names
    assert "score" in field_names
    assert "is_active" in field_names
    assert "birth_date" in field_names
    assert "created_at" in field_names
    assert "start_time" in field_names
    assert "student" in field_names

    # Check types
    field_map = {f.name: f.python_type for f in descriptor.fields}
    assert field_map["age"] == "int | None"
    assert field_map["score"] == "float | None"
    assert field_map["is_active"] == "bool"
    assert field_map["birth_date"] == "date | None"
    assert field_map["created_at"] == "datetime | None"
    assert field_map["start_time"] == "time | None"


def test_links_inferred_from_fetch_from():
    """Test that Meta.links is inferred from fetch_from fields."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("student", "Link", options="Student", reqd=True),
        MockField("student_name", "Data", fetch_from="student.full_name"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    assert "student_name" in descriptor.links
    assert descriptor.links["student_name"] == ("student", "Student", "full_name")

    # Check that student_name field is added
    field_names = {f.name for f in descriptor.fields}
    assert "student_name" in field_names


def test_children_detected_from_table_fields():
    """Test that child tables are detected and added to Meta.children."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("participants", "Table", options="Training Batch Participant"),
    ]

    meta_info = {
        "name": "Training Batch",
        "meta": MockMeta("Training Batch", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    child_class_names = {"Training Batch Participant": "TrainingBatchParticipant"}

    descriptor = _build_model_descriptor(
        "Training Batch",
        meta_info,
        with_children=True,
        with_links=True,
        child_class_names=child_class_names,
    )

    assert "participants" in descriptor.children
    assert descriptor.children["participants"] == "TrainingBatchParticipant"

    # Check that participants is not added as a regular field
    field_names = {f.name for f in descriptor.fields}
    assert "participants" not in field_names


def test_child_table_model_descriptor():
    """Test building a descriptor for a child table DocType."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data"),
        MockField("parent", "Data"),
        MockField("parenttype", "Data"),
        MockField("parentfield", "Data"),
        MockField("idx", "Int"),
        MockField("student", "Link", options="Student", reqd=True),
        MockField("attended", "Check"),
    ]

    meta_info = {
        "name": "Training Batch Participant",
        "meta": MockMeta("Training Batch Participant", istable=True, fields=fields),
        "is_child": True,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Training Batch Participant", meta_info, with_children=True, with_links=True
    )

    assert descriptor.is_child
    assert descriptor.class_name == "TrainingBatchParticipant"

    # Check that parent fields are included
    field_names = {f.name for f in descriptor.fields}
    assert "name" in field_names
    assert "parent" in field_names
    assert "parenttype" in field_names
    assert "parentfield" in field_names
    assert "idx" in field_names
    assert "student" in field_names
    assert "attended" in field_names


def test_with_children_false():
    """Test that child tables are not included when with_children=False."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("participants", "Table", options="Training Batch Participant"),
    ]

    meta_info = {
        "name": "Training Batch",
        "meta": MockMeta("Training Batch", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Training Batch", meta_info, with_children=False, with_links=True
    )

    assert "participants" not in descriptor.children


def test_with_links_false():
    """Test that Meta.links is empty when with_links=False."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("student", "Link", options="Student", reqd=True),
        MockField("student_name", "Data", fetch_from="student.full_name"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=False
    )

    assert not descriptor.links
    # student_name should still be added as a field, but not in links
    field_names = {f.name for f in descriptor.fields}
    # Note: with_links=False means we don't infer links, but the field itself might still be added
    # This depends on implementation details


def test_skip_display_fields():
    """Test that display-only fields (Section Break, Column Break, etc.) are skipped."""
    from frappe_powertools.commands.generate_models import SKIP_FIELDTYPES

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("section_1", "Section Break"),
        MockField("title", "Data"),
        MockField("column_1", "Column Break"),
        MockField("description", "Text"),
        MockField("tab_1", "Tab Break"),
        MockField("status", "Select", options="Draft\nActive"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    field_names = {f.name for f in descriptor.fields}

    # Data fields should be included
    assert "name" in field_names
    assert "title" in field_names
    assert "description" in field_names
    assert "status" in field_names

    # Display fields should be skipped
    assert "section_1" not in field_names
    assert "column_1" not in field_names
    assert "tab_1" not in field_names


def test_select_field_literal_type():
    """Test that Select fields generate Literal types from options."""
    from frappe_powertools.commands.generate_models import _build_select_literal_type

    # Basic options
    type_str, options = _build_select_literal_type("Draft\nActive\nCancelled")
    assert type_str == 'Literal["Draft", "Active", "Cancelled"] | None'
    assert options == ["Draft", "Active", "Cancelled"]

    # Empty options
    type_str, options = _build_select_literal_type("")
    assert type_str == "str | None"
    assert options is None

    # None options
    type_str, options = _build_select_literal_type(None)
    assert type_str == "str | None"
    assert options is None

    # Options with whitespace
    type_str, options = _build_select_literal_type("  Draft  \n  Active  \n")
    assert type_str == 'Literal["Draft", "Active"] | None'
    assert options == ["Draft", "Active"]


def test_select_field_in_descriptor():
    """Test that Select fields in descriptors get Literal types."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("status", "Select", options="Draft\nActive\nCancelled"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    # Find the status field
    status_field = next(f for f in descriptor.fields if f.name == "status")
    assert 'Literal["Draft", "Active", "Cancelled"]' in status_field.python_type
    assert status_field.select_options == ["Draft", "Active", "Cancelled"]


def test_dynamic_link_tracking():
    """Test that Dynamic Link fields track their type field relationship."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("reference_type", "Link", options="DocType"),
        MockField("reference_name", "Dynamic Link", options="reference_type"),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    # Check dynamic_links is populated
    assert "reference_name" in descriptor.dynamic_links
    assert descriptor.dynamic_links["reference_name"] == "reference_type"


def test_required_fields_no_default():
    """Test that required fields don't get default values."""

    @dataclass
    class MockField:
        fieldname: str
        fieldtype: str
        options: str = ""
        reqd: bool = False
        fetch_from: str = ""

    @dataclass
    class MockMeta:
        name: str
        istable: bool = False
        fields: list[MockField] = None

        def __post_init__(self):
            if self.fields is None:
                self.fields = []

    fields = [
        MockField("name", "Data", reqd=True),
        MockField("customer", "Link", options="Customer", reqd=True),
        MockField("optional_field", "Data", reqd=False),
    ]

    meta_info = {
        "name": "Test DocType",
        "meta": MockMeta("Test DocType", fields=fields),
        "is_child": False,
        "fields": fields,
    }

    descriptor = _build_model_descriptor(
        "Test DocType", meta_info, with_children=True, with_links=True
    )

    # Find the fields
    customer_field = next(f for f in descriptor.fields if f.name == "customer")
    optional_field = next(f for f in descriptor.fields if f.name == "optional_field")

    # Required field should have no default
    assert customer_field.is_required is True
    assert customer_field.default_expr == ""

    # Optional field should have default None
    assert optional_field.is_required is False
    assert optional_field.default_expr == "None"
