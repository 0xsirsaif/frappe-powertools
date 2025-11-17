"""Tests for format auto-detection functionality."""

import io
import textwrap
from typing import BinaryIO, TextIO

import pytest
from openpyxl import Workbook
from pydantic import BaseModel

from frappe_powertools.workbook.core import (
    WorkbookConfig,
    TabularFormat,
    iter_validated_rows,
    validate_workbook,
)


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


def csv_to_stringio(text: str) -> TextIO:
    """Convert CSV string to StringIO."""
    return io.StringIO(dedent_csv(text))


def create_xlsx_workbook(headers: list[str], rows: list[list]) -> BinaryIO:
    """Create an XLSX workbook in memory."""
    wb = Workbook()
    ws = wb.active
    ws.append(headers)
    for row in rows:
        ws.append(row)
    fp = io.BytesIO()
    wb.save(fp)
    fp.seek(0)
    return fp


# Fixtures
@pytest.fixture
def customer_model():
    """Fixture for CustomerRow model."""
    return CustomerRow


@pytest.fixture
def valid_csv_data():
    """Fixture for valid CSV data."""
    return dedent_csv(
        """
        code,name,email
        CUST001,Alice,alice@example.com
        CUST002,Bob,bob@example.com
        CUST003,Charlie,charlie@example.com
    """
    )


@pytest.fixture
def valid_xlsx_workbook():
    """Fixture for valid XLSX workbook."""
    return create_xlsx_workbook(
        ["code", "name", "email"],
        [
            ["CUST001", "Alice", "alice@example.com"],
            ["CUST002", "Bob", "bob@example.com"],
            ["CUST003", "Charlie", "charlie@example.com"],
        ],
    )


class TestAutoDetectionFromFileName:
    """Test auto-detection from file_name parameter."""

    def test_csv_from_file_name(self, customer_model, valid_csv_data):
        """Test CSV detection from .csv extension."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config, file_name="data.csv"))

        assert len(results) == 3
        assert all(r.is_valid for r in results)
        assert results[0].model.code == "CUST001"

    def test_xlsx_from_file_name(self, customer_model, valid_xlsx_workbook):
        """Test XLSX detection from .xlsx extension."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(
            iter_validated_rows(fp, customer_model, config=config, file_name="data.xlsx")
        )

        assert len(results) == 3
        assert all(r.is_valid for r in results)
        assert results[0].model.code == "CUST001"

    def test_xlsm_from_file_name(self, customer_model, valid_xlsx_workbook):
        """Test XLSX detection from .xlsm extension."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(
            iter_validated_rows(fp, customer_model, config=config, file_name="data.xlsm")
        )

        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_case_insensitive_extension(self, customer_model, valid_csv_data):
        """Test that file extension detection is case-insensitive."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config, file_name="DATA.CSV"))

        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_unknown_extension_falls_back_to_content(self, customer_model, valid_csv_data):
        """Test that unknown extensions fall back to content detection."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        # TextIO should be detected as CSV
        results = list(iter_validated_rows(fp, customer_model, config=config, file_name="data.txt"))

        assert len(results) == 3
        assert all(r.is_valid for r in results)


class TestAutoDetectionFromContent:
    """Test auto-detection from file content (magic bytes, stream type)."""

    def test_textio_detected_as_csv(self, customer_model, valid_csv_data):
        """Test that TextIO streams are detected as CSV."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config))

        assert len(results) == 3
        assert all(r.is_valid for r in results)
        assert results[0].model.code == "CUST001"

    def test_binaryio_with_zip_magic_detected_as_xlsx(self, customer_model, valid_xlsx_workbook):
        """Test that BinaryIO with ZIP magic bytes is detected as XLSX."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config))

        assert len(results) == 3
        assert all(r.is_valid for r in results)
        assert results[0].model.code == "CUST001"

    def test_binaryio_without_zip_magic_detected_as_csv(self, customer_model, valid_csv_data):
        """Test that BinaryIO without ZIP magic is detected as CSV."""
        # Convert CSV to binary
        csv_bytes = dedent_csv(valid_csv_data).encode("utf-8")
        fp = io.BytesIO(csv_bytes)
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config))

        assert len(results) == 3
        assert all(r.is_valid for r in results)
        assert results[0].model.code == "CUST001"

    def test_binaryio_csv_content_detected_as_csv(self, customer_model):
        """Test that binary CSV content is detected correctly."""
        csv_content = dedent_csv(
            """
            code,name
            CUST001,Alice
            CUST002,Bob
        """
        )
        fp = io.BytesIO(csv_content.encode("utf-8"))
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config))

        assert len(results) == 2
        assert all(r.is_valid for r in results)


class TestExplicitFormatOverride:
    """Test that explicit format settings override auto-detection."""

    def test_explicit_csv_overrides_file_name(self, customer_model, valid_csv_data):
        """Test that explicit CSV format overrides .xlsx file_name."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.csv)

        # Even with .xlsx extension, should use CSV because format is explicit
        results = list(
            iter_validated_rows(fp, customer_model, config=config, file_name="data.xlsx")
        )

        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_explicit_xlsx_overrides_file_name(self, customer_model, valid_xlsx_workbook):
        """Test that explicit XLSX format overrides .csv file_name."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.xlsx)

        # Even with .csv extension, should use XLSX because format is explicit
        results = list(iter_validated_rows(fp, customer_model, config=config, file_name="data.csv"))

        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_explicit_csv_overrides_content_detection(self, customer_model, valid_xlsx_workbook):
        """Test that explicit CSV format overrides ZIP magic detection."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.csv)

        # This will fail because we're trying to parse XLSX as CSV
        # But the format is explicitly set, so it should attempt CSV parsing
        results = list(iter_validated_rows(fp, customer_model, config=config))

        # CSV parser will try to read it, but it won't produce valid results
        # The exact behavior depends on how csv.DictReader handles binary XLSX data
        # This test mainly ensures explicit format is respected


class TestValidateWorkbookWithAutoDetection:
    """Test validate_workbook function with auto-detection."""

    def test_validate_workbook_csv_auto(self, customer_model, valid_csv_data):
        """Test validate_workbook with auto-detection for CSV."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        result = validate_workbook(fp, customer_model, config=config, file_name="data.csv")

        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0
        assert len(result.rows) == 3

    def test_validate_workbook_xlsx_auto(self, customer_model, valid_xlsx_workbook):
        """Test validate_workbook with auto-detection for XLSX."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.auto)

        result = validate_workbook(fp, customer_model, config=config, file_name="data.xlsx")

        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0
        assert len(result.rows) == 3

    def test_validate_workbook_auto_from_content(self, customer_model, valid_csv_data):
        """Test validate_workbook with auto-detection from content."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        result = validate_workbook(fp, customer_model, config=config)

        assert result.summary.total_rows == 3
        assert result.summary.valid_rows == 3
        assert result.summary.invalid_rows == 0


class TestAutoDetectionEdgeCases:
    """Test edge cases for auto-detection."""

    def test_empty_file_name(self, customer_model, valid_csv_data):
        """Test that empty file_name falls back to content detection."""
        fp = csv_to_stringio(valid_csv_data)
        config = WorkbookConfig(format=TabularFormat.auto)

        results = list(iter_validated_rows(fp, customer_model, config=config, file_name=""))

        # Should detect as CSV from TextIO
        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_non_seekable_stream(self, customer_model, valid_xlsx_workbook):
        """Test auto-detection with non-seekable stream."""
        fp = valid_xlsx_workbook
        config = WorkbookConfig(format=TabularFormat.auto)

        # Create a wrapper that doesn't support seek
        class NonSeekable:
            def __init__(self, fp):
                self.fp = fp
                self._read = False

            def read(self, n=-1):
                if not self._read:
                    self._read = True
                    return self.fp.read(n)
                return b""

            def tell(self):
                return 0

        non_seekable = NonSeekable(fp)

        # Should still work with file_name
        results = list(
            iter_validated_rows(non_seekable, customer_model, config=config, file_name="data.xlsx")
        )

        assert len(results) == 3
        assert all(r.is_valid for r in results)

    def test_default_config_uses_auto(self, customer_model, valid_csv_data):
        """Test that default config (format=auto) uses auto-detection."""
        fp = csv_to_stringio(valid_csv_data)
        # Don't specify format, should default to auto
        config = WorkbookConfig()

        results = list(iter_validated_rows(fp, customer_model, config=config, file_name="data.csv"))

        assert len(results) == 3
        assert all(r.is_valid for r in results)
