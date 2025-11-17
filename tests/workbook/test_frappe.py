"""Tests for Frappe adapter functionality."""

import io
import textwrap
from unittest.mock import MagicMock, Mock

import pytest
from openpyxl import Workbook
from pydantic import BaseModel

from frappe_powertools.workbook.core import WorkbookConfig, TabularFormat

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
        return dedent_csv("""
            code,name,email
            CUST001,Alice,alice@example.com
            CUST002,Bob,bob@example.com
            CUST003,Charlie,charlie@example.com
        """).encode('utf-8')
    
    @pytest.fixture
    def valid_xlsx_content(self):
        """Valid XLSX content."""
        return create_xlsx_workbook(
            ["code", "name", "email"],
            [
                ["CUST001", "Alice", "alice@example.com"],
                ["CUST002", "Bob", "bob@example.com"],
                ["CUST003", "Charlie", "charlie@example.com"],
            ]
        )
    
    def test_validate_file_with_string_name_csv(
        self, mock_file_doc, valid_csv_content
    ):
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
    
    def test_validate_file_with_document_instance_csv(
        self, mock_file_doc, valid_csv_content
    ):
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
    
    def test_validate_file_with_xlsx(
        self, mock_file_doc, valid_xlsx_content
    ):
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
    
    def test_validate_file_with_config(
        self, mock_file_doc, valid_csv_content
    ):
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
        csv_string = dedent_csv("""
            code,name
            CUST001,Alice
            CUST002,Bob
        """)
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
    
    def test_validate_file_background_parameter_ignored(
        self, mock_file_doc, valid_csv_content
    ):
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
    
    def test_validate_file_auto_detection_from_filename(
        self, mock_file_doc, valid_xlsx_content
    ):
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
        csv_content = "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        mock_file_doc.get_content.return_value = csv_content.encode('utf-8')
        
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
        csv_content = "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        mock_file_doc.get_content.return_value = csv_content.encode('utf-8')
        
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
        csv_content = "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        mock_file_doc.get_content.return_value = csv_content.encode('utf-8')
        
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
        csv_content = "code,name,email\nCUST001,Alice,alice@example.com\nCUST002,Bob,bob@example.com"
        mock_file_doc.get_content.return_value = csv_content.encode('utf-8')
        
        frappe_module.frappe = MagicMock()
        frappe_module.frappe.get_doc.return_value = mock_file_doc
        frappe_module.frappe.DoesNotExistError = Exception
        
        # Test with integer bytes (10MB)
        config = WorkbookConfig(max_file_size=10 * 1024 * 1024)
        result = frappe_module.validate_file("test_file_001", CustomerRow, config=config)
        
        # Should succeed
        assert result.summary.total_rows == 2
        assert result.summary.valid_rows == 2

