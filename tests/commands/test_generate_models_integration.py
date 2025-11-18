"""Integration tests for DocModel generator with real Frappe DocTypes."""

from __future__ import annotations

import sys
from dataclasses import dataclass
from unittest.mock import patch

import pytest

from frappe_powertools.commands.generate_models import generate_docmodels


@pytest.mark.skipif(
    "frappe" not in sys.modules,
    reason="Requires Frappe environment",
)
def test_generate_docmodels_syntax_valid():
    """Test that generated code is syntactically valid Python."""
    try:
        import frappe

        # Check if we're in a Frappe environment
        if not hasattr(frappe, "local"):
            pytest.skip("Not in a Frappe environment")

        # Try to generate models for a simple DocType (if it exists)
        # Use a common DocType that likely exists
        test_doctypes = ["User", "Role"]

        try:
            code = generate_docmodels(test_doctypes, with_children=True, with_links=True)

            # Verify the code is syntactically valid
            compile(code, "<generated>", "exec")

            # Verify it contains class definitions
            assert "class" in code
            assert "DocModel" in code
            assert "from frappe_powertools.orm import DocModel" in code

        except ValueError:
            # DocType doesn't exist, that's okay for this test
            pytest.skip("Test DocTypes do not exist in this environment")

    except ImportError:
        pytest.skip("Frappe not available")


def test_generate_docmodels_with_mock():
    """Test generate_docmodels with mocked Frappe metadata."""

    # Create mock meta objects
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

    # Mock child table
    child_fields = [
        MockField("name", "Data"),
        MockField("parent", "Data"),
        MockField("parenttype", "Data"),
        MockField("parentfield", "Data"),
        MockField("idx", "Int"),
        MockField("student", "Link", options="Student", reqd=True),
    ]

    child_meta = MockMeta("Training Batch Participant", istable=True, fields=child_fields)

    # Mock parent table
    parent_fields = [
        MockField("name", "Data", reqd=True),
        MockField("title", "Data", reqd=True),
        MockField("program", "Link", options="Training Program", reqd=True),
        MockField("program_name", "Data", fetch_from="program.program_name"),
        MockField("participants", "Table", options="Training Batch Participant"),
    ]

    parent_meta = MockMeta("Training Batch", istable=False, fields=parent_fields)

    def mock_get_meta(doctype: str):
        if doctype == "Training Batch":
            return parent_meta
        elif doctype == "Training Batch Participant":
            return child_meta
        else:
            raise ValueError(f"DocType '{doctype}' does not exist")

    with patch("frappe_powertools.commands.generate_models.frappe") as mock_frappe:
        mock_frappe.get_meta = mock_get_meta

        code = generate_docmodels(["Training Batch"], with_children=True, with_links=True)

        # Verify syntax
        namespace: dict[str, object] = {}
        exec(code, namespace)

        # Verify classes exist
        assert "TrainingBatch" in namespace
        assert "TrainingBatchParticipant" in namespace

        # Verify Meta attributes
        TrainingBatch = namespace["TrainingBatch"]
        assert hasattr(TrainingBatch, "Meta")
        assert TrainingBatch.Meta.doctype == "Training Batch"
        assert "participants" in TrainingBatch.Meta.children
        assert TrainingBatch.Meta.children["participants"] == namespace["TrainingBatchParticipant"]
        assert "program_name" in TrainingBatch.Meta.links

        # Verify child Meta
        TrainingBatchParticipant = namespace["TrainingBatchParticipant"]
        assert TrainingBatchParticipant.Meta.doctype == "Training Batch Participant"
        assert TrainingBatchParticipant.Meta.children == {}
        assert TrainingBatchParticipant.Meta.links == {}


def test_generate_docmodels_error_handling():
    """Test error handling for non-existent DocTypes."""
    with patch("frappe_powertools.commands.generate_models.frappe") as mock_frappe:
        mock_frappe.get_meta.side_effect = ValueError("DocType 'NonExistent' does not exist")

        with pytest.raises(ValueError, match="DocType 'NonExistent' does not exist"):
            generate_docmodels(["NonExistent"])


def test_generate_docmodels_no_frappe():
    """Test that generate_docmodels raises ImportError when Frappe is not available."""
    with patch("frappe_powertools.commands.generate_models.frappe", None):
        with pytest.raises(ImportError, match="Frappe is required"):
            generate_docmodels(["Test DocType"])


def test_generate_docmodels_empty_list():
    """Test that generate_docmodels raises ValueError for empty doctype list."""
    with patch("frappe_powertools.commands.generate_models.frappe") as mock_frappe:
        with pytest.raises(ValueError, match="At least one DocType must be specified"):
            generate_docmodels([])
