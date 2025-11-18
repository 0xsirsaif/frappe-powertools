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
    assert _fieldtype_to_python_type("Currency") == "float | None"
    assert _fieldtype_to_python_type("Check") == "bool"
    assert _fieldtype_to_python_type("Date") == "date | None"
    assert _fieldtype_to_python_type("Datetime") == "datetime | None"
    assert _fieldtype_to_python_type("Time") == "time | None"
    assert _fieldtype_to_python_type("Link") == "str | None"
    assert _fieldtype_to_python_type("Table") == "Any"
    assert _fieldtype_to_python_type("Unknown") == "Any"


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
