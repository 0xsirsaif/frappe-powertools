"""Tests for CSV workbook validation functionality."""

import io
import textwrap
from typing import BinaryIO, TextIO

import pytest
from pydantic import BaseModel, ConfigDict

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
    age: int | None = None


class StrictCustomerRow(BaseModel):
    """Model that forbids extra fields by default."""
    model_config = ConfigDict(extra="forbid")
    
    code: str
    name: str


# Fixtures
@pytest.fixture
def customer_model():
    """Fixture for CustomerRow model."""
    return CustomerRow


@pytest.fixture
def default_config():
    """Fixture for default CSV config."""
    return WorkbookConfig(format=TabularFormat.csv)


@pytest.fixture
def valid_csv_data():
    """Fixture for valid CSV data."""
    return """
        code,name,email,age
        CUST001,Alice Smith,alice@example.com,30
        CUST002,Bob Jones,bob@example.com,25
        CUST003,Charlie Brown,,40
    """


@pytest.fixture
def missing_field_csv_data():
    """Fixture for CSV with missing required fields."""
    return """
        code,email,age
        CUST001,alice@example.com,30
        CUST002,bob@example.com,25
    """


@pytest.fixture
def extra_field_csv_data():
    """Fixture for CSV with extra fields."""
    return """
        code,name,email,extra_field
        CUST001,Alice Smith,alice@example.com,extra_value
        CUST002,Bob Jones,bob@example.com,another_value
    """


@pytest.fixture
def mixed_validity_csv_data():
    """Fixture for CSV with mixed valid/invalid rows."""
    return """
        code,name,age
        CUST001,Alice,30
        CUST002,Bob,invalid_age
        CUST003,Charlie,25
        CUST004,,35
        CUST005,Eve,28
    """


@pytest.fixture
def empty_csv_data():
    """Fixture for CSV with only headers."""
    return """
        code,name,email
    """


# Helper functions
def dedent_csv(csv_data: str) -> str:
    """Remove common leading whitespace from CSV data for formatted strings.
    
    Allows writing CSV data with indentation. The function uses textwrap.dedent
    to remove common leading whitespace, making it easy to write formatted CSV
    strings in tests.
    
    Example:
        csv_data = '''
            code,name
            CUST001,Alice
            CUST002,Bob
        '''
        # After dedent_csv, becomes:
        # code,name
        # CUST001,Alice
        # CUST002,Bob
    
    Args:
        csv_data: CSV string that may have leading whitespace
        
    Returns:
        Dedented CSV string
    """
    return textwrap.dedent(csv_data).strip()


def csv_to_stringio(csv_data: str | bytes) -> TextIO | BinaryIO:
    """Convert CSV data string to StringIO or BytesIO.
    
    Automatically dedents string data to allow formatted CSV strings.
    
    Args:
        csv_data: CSV string (will be dedented) or bytes
        
    Returns:
        StringIO or BytesIO file-like object
    """
    if isinstance(csv_data, bytes):
        return io.BytesIO(csv_data)
    # Dedent to handle formatted strings with indentation
    return io.StringIO(dedent_csv(csv_data))


def assert_all_valid(results):
    """Assert all results are valid."""
    assert all(r.is_valid for r in results)
    assert all(r.model is not None for r in results)
    assert all(r.error is None for r in results)


def assert_all_invalid(results):
    """Assert all results are invalid."""
    assert all(not r.is_valid for r in results)
    assert all(r.model is None for r in results)
    assert all(r.error is not None for r in results)


# Tests
class TestIterValidatedRowsCSV:
    """Test iter_validated_rows with CSV input."""
    
    def test_all_valid(self, customer_model, valid_csv_data, default_config):
        """Test with all valid CSV data."""
        fp = csv_to_stringio(valid_csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 3
        assert_all_valid(results)
        
        # Check row indices (header is row 1, first data row is 2)
        assert results[0].context.row_index == 2
        assert results[1].context.row_index == 3
        assert results[2].context.row_index == 4
        
        # Check model data
        assert results[0].model.code == "CUST001"
        assert results[0].model.name == "Alice Smith"
        assert results[0].model.email == "alice@example.com"
        assert results[0].model.age == 30
        
        # Third row has None email
        assert results[2].model.email is None
    
    def test_missing_required_fields(self, customer_model, missing_field_csv_data, default_config):
        """Test with missing required fields."""
        fp = csv_to_stringio(missing_field_csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 2
        assert_all_invalid(results)
        
        # Check error mentions missing 'name' field
        for result in results:
            error_dict = result.error.errors()[0]
            assert error_dict['loc'] == ('name',)
            assert error_dict['type'] == 'missing'
    
    @pytest.mark.parametrize("extra,expected_valid", [
        ("forbid", False),
        ("ignore", True),
        ("allow", True),
    ])
    def test_extra_columns(self, customer_model, extra_field_csv_data, extra, expected_valid):
        """Test extra columns with different extra settings."""
        fp = csv_to_stringio(extra_field_csv_data)
        config = WorkbookConfig(format=TabularFormat.csv, extra=extra)
        results = list(iter_validated_rows(fp, customer_model, config=config))
        
        assert len(results) == 2
        
        if expected_valid:
            assert_all_valid(results)
            if extra == "allow":
                # With allow, extra field should be in model
                assert hasattr(results[0].model, 'extra_field')
            else:
                # With ignore, extra field should not be in model
                assert not hasattr(results[0].model, 'extra_field')
        else:
            assert_all_invalid(results)
            # Check error mentions extra field
            error_dict = results[0].error.errors()[0]
            assert error_dict['type'] == 'extra_forbidden'
    
    @pytest.mark.parametrize("max_rows,expected_count", [
        (1, 1),
        (3, 3),
        (5, 5),
        (10, 5),  # More than available rows
    ])
    def test_max_rows(self, customer_model, default_config, max_rows, expected_count):
        """Test max_rows configuration."""
        csv_data = """
            code,name
            CUST001,Alice
            CUST002,Bob
            CUST003,Charlie
            CUST004,David
            CUST005,Eve
        """
        
        fp = csv_to_stringio(csv_data)
        config = WorkbookConfig(format=TabularFormat.csv, max_rows=max_rows)
        results = list(iter_validated_rows(fp, customer_model, config=config))
        
        assert len(results) == expected_count
        if results:
            assert results[0].model.code == "CUST001"
    
    def test_stop_on_first_error(self, customer_model, default_config):
        """Test stop_on_first_error configuration."""
        csv_data = """
            code,name,age
            CUST001,Alice,30
            CUST002,Bob,invalid
            CUST003,Charlie,25
            CUST004,David,35
        """
        
        fp = csv_to_stringio(csv_data)
        config = WorkbookConfig(format=TabularFormat.csv, stop_on_first_error=True)
        results = list(iter_validated_rows(fp, customer_model, config=config))
        
        # Should stop after second row (first error)
        assert len(results) == 2
        assert results[0].is_valid
        assert not results[1].is_valid
    
    @pytest.mark.parametrize("delimiter", [",", ";", "\t"])
    def test_custom_delimiter(self, customer_model, delimiter):
        """Test custom delimiter."""
        if delimiter == ";":
            csv_data = """
                code;name;email
                CUST001;Alice Smith;alice@example.com
                CUST002;Bob Jones;bob@example.com
            """
        elif delimiter == "\t":
            csv_data = """
                code\tname\temail
                CUST001\tAlice Smith\talice@example.com
                CUST002\tBob Jones\tbob@example.com
            """
        else:
            csv_data = """
                code,name,email
                CUST001,Alice Smith,alice@example.com
                CUST002,Bob Jones,bob@example.com
            """
        
        fp = csv_to_stringio(csv_data)
        config = WorkbookConfig(format=TabularFormat.csv, delimiter=delimiter)
        results = list(iter_validated_rows(fp, customer_model, config=config))
        
        assert len(results) == 2
        assert_all_valid(results)
        assert results[0].model.code == "CUST001"
        assert results[1].model.code == "CUST002"
    
    def test_empty_csv(self, customer_model, empty_csv_data, default_config):
        """Test with empty CSV (only headers)."""
        fp = csv_to_stringio(empty_csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 0
    
    def test_binary_stream(self, customer_model, default_config):
        """Test with binary stream (should decode as UTF-8)."""
        # Create bytes from formatted string
        csv_string = """
            code,name,email
            CUST001,Alice Smith,alice@example.com
            CUST002,Bob Jones,bob@example.com
        """
        csv_data = dedent_csv(csv_string).encode('utf-8')
        
        fp = csv_to_stringio(csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 2
        assert_all_valid(results)
    
    def test_formatted_csv_string(self, customer_model, default_config):
        """Test that formatted CSV strings with indentation work correctly."""
        # This is the formatted style that should now work
        csv_data = """
            code,name,email,age
            CUST001,Alice Smith,alice@example.com,30
            CUST002,Bob Jones,bob@example.com,25
            CUST003,Charlie Brown,,40
        """
        
        fp = csv_to_stringio(csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 3
        assert_all_valid(results)
        assert results[0].model.code == "CUST001"
        assert results[1].model.code == "CUST002"
        assert results[2].model.code == "CUST003"
    
    def test_csv_with_whitespace_in_values(self, customer_model, default_config):
        """Test that whitespace in CSV values is properly stripped."""
        csv_data = """
            code, name , email , age
            CUST001, Alice Smith , alice@example.com , 30
            CUST002, Bob Jones , bob@example.com , 25
        """
        
        fp = csv_to_stringio(csv_data)
        results = list(iter_validated_rows(fp, customer_model, config=default_config))
        
        assert len(results) == 2
        assert_all_valid(results)
        # Values should be stripped
        assert results[0].model.name == "Alice Smith"  # No leading/trailing spaces
        assert results[0].model.email == "alice@example.com"
        assert results[0].model.age == 30


class TestValidateWorkbookCSV:
    """Test validate_workbook with CSV input."""
    
    @pytest.mark.parametrize("csv_data,expected_total,expected_valid,expected_invalid,expected_error_rate", [
        (
            """
                code,name
                CUST001,Alice
                CUST002,Bob
                CUST003,Charlie
            """,
            3, 3, 0, 0.0
        ),
        (
            """
                code
                CUST001
                CUST002
                CUST003
            """,
            3, 0, 3, 100.0
        ),
        (
            """
                code,name
            """,
            0, 0, 0, 0.0
        ),
    ])
    def test_summary_statistics(
        self, 
        customer_model, 
        csv_data, 
        expected_total, 
        expected_valid, 
        expected_invalid, 
        expected_error_rate
    ):
        """Test summary statistics for different scenarios."""
        fp = csv_to_stringio(csv_data)
        result = validate_workbook(fp, customer_model)
        
        assert result.summary.total_rows == expected_total
        assert result.summary.valid_rows == expected_valid
        assert result.summary.invalid_rows == expected_invalid
        assert result.summary.error_rate == expected_error_rate
    
    def test_mixed_validity_summary(self, customer_model, mixed_validity_csv_data):
        """Test summary with mixed valid/invalid rows."""
        fp = csv_to_stringio(mixed_validity_csv_data)
        result = validate_workbook(fp, customer_model)
        
        assert result.summary.total_rows == 5
        assert result.summary.valid_rows == 3  # Rows 1, 3, 5
        assert result.summary.invalid_rows == 2  # Row 2 (invalid age), Row 4 (empty name)
        assert result.summary.error_rate == 40.0
        
        # Check valid models
        valid_models = result.valid_models
        assert len(valid_models) == 3
        assert valid_models[0].code == "CUST001"
        assert valid_models[1].code == "CUST003"
        assert valid_models[2].code == "CUST005"
        
        # Check errors
        errors = result.errors
        assert len(errors) == 2
        assert errors[0][0] == 3  # Row 3 (Bob with invalid age)
        assert errors[1][0] == 5  # Row 5 (missing name)
    
    def test_empty_workbook(self, customer_model, empty_csv_data):
        """Test with empty workbook."""
        fp = csv_to_stringio(empty_csv_data)
        result = validate_workbook(fp, customer_model)
        
        assert result.summary.total_rows == 0
        assert result.summary.valid_rows == 0
        assert result.summary.invalid_rows == 0
        assert result.summary.error_rate == 0.0
        assert len(result.valid_models) == 0
        assert len(result.errors) == 0