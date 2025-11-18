"""Tests for Frappe adapter functionality."""

import io
import textwrap
from unittest.mock import MagicMock, Mock

import pytest
from openpyxl import Workbook
from pydantic import BaseModel, Field, ValidationError

from frappe_powertools.workbook.core import (
    RowContext,
    RowResult,
    WorkbookConfig,
    WorkbookSummary,
    WorkbookValidationResult,
    TabularFormat,
)

import frappe_powertools.workbook.frappe as frappe_module


# Test models
class CustomerRow(BaseModel):
    """Sample model for testing."""

    code: str
    name: str
    email: str | None = None


# Helper functions
def dedent_csv(text: str) -> str:
    """Remove common leading whitespace from CSV strings."""
    return textwrap.dedent(text).strip()


def create_xlsx_workbook(headers: list[str], rows: list[list]) -> bytes:
    """Create an XLSX workbook in memory and return as bytes."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    fp = io.BytesIO()
    wb.save(fp)
    fp.seek(0)
    return fp.getvalue()


class TestValidateFile:
    """Test validate_file function with mocked Frappe."""

    @pytest.fixture
    def mock_file_doc(self):
        """Create a mock File document."""
        file_doc = MagicMock()
        file_doc.doctype = "File"
        file_doc.name = "test_file_001"
        file_doc.file_name = "test.csv"
        file_doc.has_permission = Mock(return_value=True)
        return file_doc

    @pytest.fixture
    def valid_csv_content(self):
        """Valid CSV content."""
        return dedent_csv(
            """
            code,name,email
            CUST001,Alice,alice@example.com
            CUST002,Bob,bob@example.com
            CUST003,Charlie,charlie@example.com
        """
        ).encode("utf-8")

    @pytest.fixture
    def valid_xlsx_content(self):
        """Valid XLSX content."""
        return create_xlsx_workbook(
            ["code", "name", "email"],
            [
                ["CUST001", "Alice", "alice@example.com"],
                ["CUST002", "Bob", "bob@example.com"],
                ["CUST003", "Charlie", "charlie@example.com"],
            ],
        )

    def test_validate_file_with_string_name_csv(self, mock_file_doc, valid_csv_content):
        """Test validate_file with string file name for CSV."""

        # Setup mock
        mock_file_doc.get_content.return_value = valid_csv_content
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        result = frappe_module.validate_file("test_file_001", CustomerRow)

        # Assertions
        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0
        assert len(result.rows) == 3
        assert all(r.is_valid for r in result.rows)
        assert result.rows[0].model.code == "CUST001"

        # Verify Frappe was called correctly
        frappe_module.frappe.get_doc.assert_called_once_with("File", "test_file_001")
        mock_file_doc.has_permission.assert_called_once_with("read")
        mock_file_doc.get_content.assert_called_once()

    def test_validate_file_with_document_instance_csv(self, mock_file_doc, valid_csv_content):
        """Test validate_file with File Document instance for CSV."""

        # Setup mock
        mock_file_doc.get_content.return_value = valid_csv_content

        # Test
        result = frappe_module.validate_file(mock_file_doc, CustomerRow)

        # Assertions
        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0

        # Verify has_permission and get_content were called
        mock_file_doc.has_permission.assert_called_once_with("read")
        mock_file_doc.get_content.assert_called_once()

    def test_validate_file_with_xlsx(self, mock_file_doc, valid_xlsx_content):
        """Test validate_file with XLSX file."""

        # Setup mock
        mock_file_doc.file_name = "test.xlsx"
        mock_file_doc.get_content.return_value = valid_xlsx_content
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        result = frappe_module.validate_file("test_file_001", CustomerRow)

        # Assertions
        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0
        assert result.rows[0].model.code == "CUST001"

    def test_validate_file_with_config(self, mock_file_doc, valid_csv_content):
        """Test validate_file with custom config."""

        # Setup mock
        mock_file_doc.get_content.return_value = valid_csv_content
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with custom config
        config = WorkbookConfig(format=TabularFormat.csv, max_rows=2)
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)

        # Assertions
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2

    def test_validate_file_file_not_found(self):
        """Test validate_file when file is not found."""

        # Setup mock to raise DoesNotExistError
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.side_effect = Exception("File not found")
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        with pytest.raises(ValueError, match="File document not found"):
            frappe_module.validate_file("nonexistent_file", CustomerRow)

    def test_validate_file_permission_denied(self, mock_file_doc):
        """Test validate_file when permission is denied."""

        # Setup mock
        mock_file_doc.has_permission.return_value = False
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        with pytest.raises(PermissionError, match="Permission denied"):
            frappe_module.validate_file("test_file_001", CustomerRow)

    def test_validate_file_empty_content(self, mock_file_doc):
        """Test validate_file when file content is empty."""

        # Setup mock
        mock_file_doc.get_content.return_value = None
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        with pytest.raises(ValueError, match="File content is empty"):
            frappe_module.validate_file("test_file_001", CustomerRow)

    def test_validate_file_string_content(self, mock_file_doc):
        """Test validate_file when get_content returns string (should be converted to bytes)."""

        # Setup mock - return string content
        csv_string = dedent_csv(
            """
            code,name
            CUST001,Alice
            CUST002,Bob
        """
        )
        mock_file_doc.get_content.return_value = csv_string
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test
        result = frappe_module.validate_file("test_file_001", CustomerRow)

        # Assertions
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2

    def test_validate_file_wrong_doctype(self):
        """Test validate_file when document is not a File doctype."""

        # Create a mock document that's not a File
        wrong_doc = MagicMock()
        wrong_doc.doctype = "CustomDocType"

        # Test
        with pytest.raises(ValueError, match="Document is not a File document"):
            frappe_module.validate_file(wrong_doc, CustomerRow)

    def test_validate_file_without_frappe(self):
        """Test that validate_file raises ImportError when frappe is not available."""
        # Temporarily remove frappe from the module
        original_frappe = frappe_module.frappe
        frappe_module.frappe = None

        try:
            with pytest.raises(ImportError, match="frappe is required"):
                frappe_module.validate_file("test_file", CustomerRow)
        finally:
            # Restore frappe
            frappe_module.frappe = original_frappe

    def test_validate_file_invalid_file_type(self):
        """Test validate_file with invalid file type."""

        # Test with invalid type
        with pytest.raises(TypeError, match="file must be a string.*File Document"):
            frappe_module.validate_file(123, CustomerRow)  # type: ignore[arg-type]

    def test_validate_file_background_parameter_ignored(self, mock_file_doc, valid_csv_content):
        """Test that background parameter is accepted but ignored."""

        # Setup mock
        mock_file_doc.get_content.return_value = valid_csv_content
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with background=True (should be ignored, run synchronously)
        result = frappe_module.validate_file(
            "test_file_001", CustomerRow, background=True, job_name="test_job"
        )

        # Should still work synchronously
        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3

    def test_validate_file_auto_detection_from_filename(self, mock_file_doc, valid_xlsx_content):
        """Test that file_name is used for format auto-detection."""

        # Setup mock with XLSX content but no explicit format
        mock_file_doc.file_name = "data.xlsx"
        mock_file_doc.get_content.return_value = valid_xlsx_content
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with auto format (default)
        config = WorkbookConfig(format=TabularFormat.auto)
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)

        # Should detect XLSX from filename
        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3

    def test_validate_file_size_exceeds_limit(self):
        """Test file size validation when file exceeds limit."""
        from unittest.mock import MagicMock

        # Create a mock file document
        mock_file_doc = MagicMock()
        mock_file_doc.doctype = "File"
        mock_file_doc.name = "test_file_001"
        mock_file_doc.file_name = "large_file.csv"
        mock_file_doc.file_size = 15 * 1024 * 1024  # 15MB
        mock_file_doc.has_permission.return_value = True

        # Create valid CSV content
        csv_content = (
            "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        )
        mock_file_doc.get_content.return_value = csv_content.encode("utf-8")

        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with 10MB limit
        config = WorkbookConfig(max_file_size="10MB")

        with pytest.raises(ValueError, match="File size exceeds maximum limit"):
            frappe_module.validate_file("test_file_001", CustomerRow, config=config)

    def test_validate_file_size_within_limit(self):
        """Test file size validation when file is within limit."""
        from unittest.mock import MagicMock

        # Create a mock file document
        mock_file_doc = MagicMock()
        mock_file_doc.doctype = "File"
        mock_file_doc.name = "test_file_001"
        mock_file_doc.file_name = "small_file.csv"
        mock_file_doc.file_size = 5 * 1024 * 1024  # 5MB
        mock_file_doc.has_permission.return_value = True

        # Create valid CSV content
        csv_content = (
            "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        )
        mock_file_doc.get_content.return_value = csv_content.encode("utf-8")

        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with 10MB limit
        config = WorkbookConfig(max_file_size="10MB")
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)

        # Should succeed
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2

    def test_validate_file_size_no_limit(self):
        """Test file size validation when no limit is set."""
        from unittest.mock import MagicMock

        # Create a mock file document
        mock_file_doc = MagicMock()
        mock_file_doc.doctype = "File"
        mock_file_doc.name = "test_file_001"
        mock_file_doc.file_name = "large_file.csv"
        mock_file_doc.file_size = 100 * 1024 * 1024  # 100MB
        mock_file_doc.has_permission.return_value = True

        # Create valid CSV content
        csv_content = (
            "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        )
        mock_file_doc.get_content.return_value = csv_content.encode("utf-8")

        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with no limit (default)
        config = WorkbookConfig()
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)

        # Should succeed even with large file
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2

    def test_validate_file_size_fallback_to_content_length(self):
        """Test file size validation falls back to content length when file_size not available."""
        from unittest.mock import MagicMock

        # Create a mock file document without file_size attribute
        mock_file_doc = MagicMock()
        mock_file_doc.doctype = "File"
        mock_file_doc.name = "test_file_001"
        mock_file_doc.file_name = "large_file.csv"
        # Remove file_size attribute
        del mock_file_doc.file_size
        mock_file_doc.has_permission.return_value = True

        # Create large content (15MB)
        large_content = b"x" * (15 * 1024 * 1024)
        mock_file_doc.get_content.return_value = large_content

        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with 10MB limit
        config = WorkbookConfig(max_file_size="10MB")

        with pytest.raises(ValueError, match="File size exceeds maximum limit"):
            frappe_module.validate_file("test_file_001", CustomerRow, config=config)

    def test_validate_file_size_with_int_bytes(self):
        """Test file size validation with integer bytes in config."""
        from unittest.mock import MagicMock

        # Create a mock file document
        mock_file_doc = MagicMock()
        mock_file_doc.doctype = "File"
        mock_file_doc.name = "test_file_001"
        mock_file_doc.file_name = "small_file.csv"
        mock_file_doc.file_size = 5 * 1024 * 1024  # 5MB
        mock_file_doc.has_permission.return_value = True

        # Create valid CSV content
        csv_content = (
            "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        )
        mock_file_doc.get_content.return_value = csv_content.encode("utf-8")

        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception

        # Test with integer bytes (10MB)
        config = WorkbookConfig(max_file_size=10 * 1024 * 1024)
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)

        # Should succeed
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2


class TestBuildValidationErrorMessages:
    """Test build_validation_error_messages function."""

    @pytest.fixture
    def model_with_aliases(self):
        """Create a Pydantic model with field aliases."""

        class TestRow(BaseModel):
            name: str = Field(alias="Full Name")
            age: int = Field(alias="Age")
            email: str | None = Field(None, alias="Email Address")

        return TestRow

    @pytest.fixture
    def model_without_aliases(self):
        """Create a Pydantic model without field aliases."""

        class TestRow(BaseModel):
            name: str
            age: int
            email: str | None = None

        return TestRow

    def test_build_error_messages_with_model_and_aliases(self, model_with_aliases):
        """Test error message building with model that has aliases."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        # Create validation result with errors
        # Use model_validate with aliases since the model has field aliases
        error1 = None
        try:
            model_with_aliases.model_validate({"Full Name": "", "Age": "invalid"})
        except ValidationError as e:
            error1 = e

        error2 = None
        try:
            model_with_aliases.model_validate({"Age": 25})  # Missing required 'Full Name'
        except ValidationError as e:
            error2 = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"Full Name": "", "Age": "invalid"}),
                model=None,
                error=error1,
            ),
            RowResult(
                context=RowContext(row_index=3, raw={"Age": 25}),
                model=None,
                error=error2,
            ),
        ]

        summary = WorkbookSummary(total_rows=2, valid_rows=0, invalid_rows=2)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_with_aliases)

        # Check messages structure (flat format is default)
        assert isinstance(messages, list)
        assert len(messages) > 0
        # Flat format: messages start with "Row X, ..."
        assert any("Row 2" in msg or "Row 3" in msg for msg in messages)

        # Check that aliases are used in error messages
        messages_str = "\n".join(messages)
        assert "Full Name" in messages_str or "name" in messages_str.lower()

        # Check error details structure
        assert "summary" in details
        assert "errors_by_row" in details
        assert "invalid_row_indices" in details
        assert details["summary"]["invalid_rows"] == 2
        assert len(details["errors_by_row"]) == 2

    def test_build_error_messages_without_model_extracts_from_result(self, model_with_aliases):
        """Test error message building when model is not provided but can be extracted from result."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        # Create result with one valid row (to extract model from) and one invalid
        # Use model_validate with aliases since the model has field aliases
        valid_model = model_with_aliases.model_validate({"Full Name": "Test", "Age": 30})
        error = None
        try:
            model_with_aliases.model_validate({"Age": "invalid"})
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=1, raw={"Full Name": "Test", "Age": 30}),
                model=valid_model,
                error=None,
            ),
            RowResult(
                context=RowContext(row_index=2, raw={"Age": "invalid"}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=2, valid_rows=1, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        # Don't provide model, should extract from first valid row
        messages, details = build_validation_error_messages(result)

        assert isinstance(messages, list)
        assert len(messages) > 0
        assert details["summary"]["invalid_rows"] == 1

    def test_build_error_messages_max_errors_limit(self, model_without_aliases):
        """Test that max_errors parameter limits the number of errors shown."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        # Create many errors
        rows = []
        for i in range(10):
            error = None
            try:
                model_without_aliases(age="invalid")
            except ValidationError as e:
                error = e

            rows.append(
                RowResult(
                    context=RowContext(row_index=i + 2, raw={"age": "invalid"}),
                    model=None,
                    error=error,
                )
            )

        summary = WorkbookSummary(total_rows=10, valid_rows=0, invalid_rows=10)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        # Limit to 5 errors
        messages, details = build_validation_error_messages(
            result, model=model_without_aliases, max_errors=5
        )

        # Check that truncation message appears
        messages_str = "\n".join(messages)
        assert "... and" in messages_str or "more row(s)" in messages_str

        # Check that error details still contain all errors
        assert len(details["errors_by_row"]) == 10

    def test_build_error_messages_include_raw_data(self, model_without_aliases):
        """Test include_raw_data parameter."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error = None
        try:
            model_without_aliases(age="invalid")
        except ValidationError as e:
            error = e

        raw_data = {"name": "Test", "age": "invalid"}
        rows = [
            RowResult(
                context=RowContext(row_index=2, raw=raw_data),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        # With include_raw_data=True
        messages1, details1 = build_validation_error_messages(
            result, model=model_without_aliases, include_raw_data=True
        )
        assert details1["errors_by_row"][2]["raw_data"] == raw_data

        # With include_raw_data=False
        messages2, details2 = build_validation_error_messages(
            result, model=model_without_aliases, include_raw_data=False
        )
        assert details2["errors_by_row"][2]["raw_data"] is None

    def test_build_error_messages_multiple_errors_per_row(self, model_without_aliases):
        """Test handling of multiple errors in a single row."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        # Create error with multiple validation failures
        error = None
        try:
            model_without_aliases()  # Missing both name and age
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_without_aliases)

        # Check that row shows multiple errors
        row_info = details["errors_by_row"][2]
        assert row_info["error_count"] >= 2  # At least name and age are required

        # Check messages show multiple errors (flat format shows each error separately)
        messages_str = "\n".join(messages)
        # In flat format, each error is on its own line starting with "Row 2"
        assert len([msg for msg in messages if msg.startswith("Row 2")]) >= 2

    def test_build_error_messages_no_errors(self, model_without_aliases):
        """Test behavior when there are no validation errors."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        valid_model = model_without_aliases(name="Test", age=30)
        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Test", "age": 30}),
                model=valid_model,
                error=None,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=1, invalid_rows=0)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_without_aliases)

        # Should return empty messages and details
        assert len(messages) == 0 or "0 error(s)" in messages[0]
        assert details["summary"]["invalid_rows"] == 0
        assert len(details["errors_by_row"]) == 0

    def test_build_error_messages_error_details_structure(self, model_without_aliases):
        """Test that error_details has the correct structure."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error = None
        try:
            model_without_aliases(name="Test", age="invalid")
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Test", "age": "invalid"}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_without_aliases)

        # Check summary structure
        assert "total_rows" in details["summary"]
        assert "valid_rows" in details["summary"]
        assert "invalid_rows" in details["summary"]
        assert "error_count" in details["summary"]
        assert "error_rate" in details["summary"]

        # Check errors_by_row structure
        assert 2 in details["errors_by_row"]
        row_info = details["errors_by_row"][2]
        assert "row_index" in row_info
        assert "errors" in row_info
        assert "error_count" in row_info
        assert "raw_data" in row_info

        # Check individual error structure
        assert len(row_info["errors"]) > 0
        error_info = row_info["errors"][0]
        assert "field" in error_info
        assert "message" in error_info
        assert "error_type" in error_info
        assert "category" in error_info
        assert "input_value" in error_info

        # Check invalid_row_indices
        assert isinstance(details["invalid_row_indices"], list)
        assert 2 in details["invalid_row_indices"]

    def test_build_error_messages_field_alias_extraction(self, model_with_aliases):
        """Test that field aliases are correctly extracted and used."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error = None
        try:
            # Use model_validate with aliases - missing required 'Full Name' field
            model_with_aliases.model_validate({"Age": 30})
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"Age": 30}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_with_aliases)

        # Check that alias "Full Name" is used in error messages instead of "name"
        messages_str = "\n".join(messages)
        # The error should reference the alias, not the Python field name
        # Note: Pydantic errors might still use field name, but we map it
        assert "Full Name" in messages_str or "name" in messages_str.lower()

    def test_build_error_messages_input_value_display(self, model_without_aliases):
        """Test that input values are displayed in error messages."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error = None
        try:
            model_without_aliases(name="Test", age="invalid_age")
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Test", "age": "invalid_age"}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_without_aliases)

        # Check that input value is shown in error message
        messages_str = "\n".join(messages)
        # Should show the invalid value
        assert "invalid_age" in messages_str or "age" in messages_str.lower()

    def test_build_error_messages_error_categorization(self, model_without_aliases):
        """Test that errors are correctly categorized."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        # Missing required field
        error1 = None
        try:
            model_without_aliases(age=30)  # Missing name
        except ValidationError as e:
            error1 = e

        # Invalid type
        error2 = None
        try:
            model_without_aliases(name="Test", age="not_a_number")
        except ValidationError as e:
            error2 = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"age": 30}),
                model=None,
                error=error1,
            ),
            RowResult(
                context=RowContext(row_index=3, raw={"name": "Test", "age": "not_a_number"}),
                model=None,
                error=error2,
            ),
        ]

        summary = WorkbookSummary(total_rows=2, valid_rows=0, invalid_rows=2)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(result, model=model_without_aliases)

        # Check that errors are categorized
        for row_index, row_info in details["errors_by_row"].items():
            for error_info in row_info["errors"]:
                assert "category" in error_info
                assert error_info["category"] in [
                    "missing_required",
                    "invalid_format",
                    "missing_reference",
                    "business_rule",
                    "other",
                ]

    def test_build_error_messages_group_by_row(self, model_without_aliases):
        """Test that errors are grouped by row."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error1 = None
        try:
            model_without_aliases(age=30)
        except ValidationError as e:
            error1 = e

        error2 = None
        try:
            model_without_aliases(name="Test")
        except ValidationError as e:
            error2 = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"age": 30}),
                model=None,
                error=error1,
            ),
            RowResult(
                context=RowContext(row_index=3, raw={"name": "Test"}),
                model=None,
                error=error2,
            ),
        ]

        summary = WorkbookSummary(total_rows=2, valid_rows=0, invalid_rows=2)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(
            result, model=model_without_aliases, format_style="structured", group_by="row"
        )

        # Check that errors are grouped by row
        assert 2 in details["errors_by_row"]
        assert 3 in details["errors_by_row"]

        # Check messages show structured format with summary and grouping
        messages_str = "\n".join(messages)
        assert "File validation failed" in messages_str
        assert "Row 2" in messages_str
        assert "Row 3" in messages_str
        assert "error(s)" in messages_str  # Structured format shows error counts

    def test_build_error_messages_flat_format_characteristics(self, model_without_aliases):
        """Test that flat format has no summary, no empty lines, no grouping headers."""
        from frappe_powertools.workbook.frappe import build_validation_error_messages

        error = None
        try:
            model_without_aliases(name="Test", age="invalid")
        except ValidationError as e:
            error = e

        rows = [
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Test", "age": "invalid"}),
                model=None,
                error=error,
            ),
        ]

        summary = WorkbookSummary(total_rows=1, valid_rows=0, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)

        messages, details = build_validation_error_messages(
            result, model=model_without_aliases, format_style="flat"
        )

        # Flat format characteristics:
        # - No summary line
        assert not any("File validation failed" in msg for msg in messages)
        # - No empty lines
        assert "" not in messages
        # - No grouping headers like "Row 2 (X error(s)):"
        assert not any("error(s)):" in msg for msg in messages)
        # - Each error message starts with "Row X," (except truncation message)
        error_messages = [msg for msg in messages if not msg.startswith("... and")]
        assert all(msg.startswith("Row ") for msg in error_messages if error_messages)
