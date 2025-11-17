"""Tests for core workbook validation data structures and config."""

import pytest
from pydantic import BaseModel, ValidationError

from frappe_powertools.workbook.core import (
    RowContext,
    RowResult,
    TabularFormat,
    WorkbookConfig,
    WorkbookSummary,
    WorkbookValidationResult,
)


# Sample Pydantic model for testing
class SampleRow(BaseModel):
    name: str
    age: int
    email: str | None = None


class TestWorkbookConfig:
    """Test WorkbookConfig dataclass."""
    
    def test_workbook_config_defaults(self):
        """Test that WorkbookConfig has sensible defaults."""
        config = WorkbookConfig()
        
        assert config.format == TabularFormat.auto
        assert config.header_row == 1
        assert config.data_row_start == 2  # Should be header_row + 1
        assert config.delimiter == ","
        assert config.sheet_name is None
        assert config.extra == "ignore"
        assert config.stop_on_first_error is False
        assert config.max_rows is None
    
    def test_data_row_start_derived_correctly_when_none(self):
        """Test that data_row_start is correctly derived from header_row when None."""
        config = WorkbookConfig(header_row=3)
        assert config.data_row_start == 4  # header_row + 1
        
        # Explicit data_row_start should not be overridden
        config2 = WorkbookConfig(header_row=3, data_row_start=5)
        assert config2.data_row_start == 5
    
    def test_workbook_config_validation(self):
        """Test WorkbookConfig validation rules."""
        # header_row must be >= 1
        with pytest.raises(ValueError, match="header_row must be >= 1"):
            WorkbookConfig(header_row=0)
        
        # data_row_start must be >= header_row
        with pytest.raises(ValueError, match="data_row_start must be >= header_row"):
            WorkbookConfig(header_row=5, data_row_start=3)
        
        # max_rows must be >= 1
        with pytest.raises(ValueError, match="max_rows must be >= 1"):
            WorkbookConfig(max_rows=0)


class TestRowResult:
    """Test RowResult dataclass."""
    
    def test_row_result_valid(self):
        """Test RowResult for a valid row."""
        context = RowContext(row_index=2, raw={"name": "Alice", "age": 30})
        model = SampleRow(name="Alice", age=30)
        result = RowResult(context=context, model=model, error=None)
        
        assert result.is_valid
        assert result.model == model
        assert result.error is None
        assert result.context.row_index == 2
    
    def test_row_result_invalid(self):
        """Test RowResult for an invalid row."""
        context = RowContext(row_index=3, raw={"name": "Bob", "age": "invalid"})
        
        # Create a validation error
        error = None
        try:
            SampleRow(name="Bob", age="invalid")
        except ValidationError as e:
            error = e
        
        result = RowResult(context=context, model=None, error=error)
        
        assert not result.is_valid
        assert result.model is None
        assert result.error is not None
        assert isinstance(result.error, ValidationError)
    
    def test_row_result_is_valid_property(self):
        """Test the is_valid property logic."""
        context = RowContext(row_index=1, raw={})
        
        # Both model and no error = valid
        result1 = RowResult(context=context, model=SampleRow(name="Test", age=25), error=None)
        assert result1.is_valid
        
        # No model but error = invalid
        try:
            SampleRow(age="invalid")
        except ValidationError as e:
            result2 = RowResult(context=context, model=None, error=e)
        assert not result2.is_valid
        
        # Edge case: model but also error = invalid
        try:
            SampleRow(name="Test", age="bad")
        except ValidationError as e:
            result3 = RowResult(
                context=context, 
                model=SampleRow(name="Test", age=25), 
                error=e
            )
        assert not result3.is_valid


class TestWorkbookSummary:
    """Test WorkbookSummary dataclass."""
    
    def test_workbook_summary_error_rate(self):
        """Test error rate calculation."""
        # No errors
        summary1 = WorkbookSummary(total_rows=10, valid_rows=10, invalid_rows=0)
        assert summary1.error_rate == 0.0
        
        # 50% error rate
        summary2 = WorkbookSummary(total_rows=10, valid_rows=5, invalid_rows=5)
        assert summary2.error_rate == 50.0
        
        # All errors
        summary3 = WorkbookSummary(total_rows=10, valid_rows=0, invalid_rows=10)
        assert summary3.error_rate == 100.0
        
        # Empty workbook
        summary4 = WorkbookSummary(total_rows=0, valid_rows=0, invalid_rows=0)
        assert summary4.error_rate == 0.0


class TestWorkbookValidationResult:
    """Test WorkbookValidationResult dataclass."""
    
    def test_valid_models_property(self):
        """Test extraction of valid models."""
        # Create some test data
        rows = [
            RowResult(
                context=RowContext(row_index=1, raw={"name": "Alice", "age": 30}),
                model=SampleRow(name="Alice", age=30),
                error=None
            ),
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Bob", "age": "invalid"}),
                model=None,
                error=ValidationError.from_exception_data("test", [])
            ),
            RowResult(
                context=RowContext(row_index=3, raw={"name": "Charlie", "age": 25}),
                model=SampleRow(name="Charlie", age=25),
                error=None
            ),
        ]
        
        summary = WorkbookSummary(total_rows=3, valid_rows=2, invalid_rows=1)
        result = WorkbookValidationResult(summary=summary, rows=rows)
        
        valid_models = result.valid_models
        assert len(valid_models) == 2
        assert valid_models[0].name == "Alice"
        assert valid_models[1].name == "Charlie"
    
    def test_errors_property(self):
        """Test extraction of errors with row indices."""
        # Create test data with errors by actually triggering validation errors
        error1 = None
        try:
            SampleRow(name="Bob", age="invalid")
        except ValidationError as e:
            error1 = e
        
        error2 = None
        try:
            SampleRow(age=25)  # Missing required 'name' field
        except ValidationError as e:
            error2 = e
        
        rows = [
            RowResult(
                context=RowContext(row_index=1, raw={"name": "Alice", "age": 30}),
                model=SampleRow(name="Alice", age=30),
                error=None
            ),
            RowResult(
                context=RowContext(row_index=2, raw={"name": "Bob", "age": "invalid"}),
                model=None,
                error=error1
            ),
            RowResult(
                context=RowContext(row_index=3, raw={"age": 25}),
                model=None,
                error=error2
            ),
        ]
        
        summary = WorkbookSummary(total_rows=3, valid_rows=1, invalid_rows=2)
        result = WorkbookValidationResult(summary=summary, rows=rows)
        
        errors = result.errors
        assert len(errors) == 2
        assert errors[0][0] == 2  # Row index
        assert errors[0][1] == error1
        assert errors[1][0] == 3  # Row index
        assert errors[1][1] == error2


class TestTabularFormat:
    """Test TabularFormat enum."""
    
    def test_tabular_format_values(self):
        """Test enum values."""
        assert TabularFormat.auto.value == "auto"
        assert TabularFormat.csv.value == "csv"
        assert TabularFormat.xlsx.value == "xlsx"
    
    def test_tabular_format_string_enum(self):
        """Test that TabularFormat inherits from str."""
        assert isinstance(TabularFormat.csv, str)
        assert TabularFormat.csv == "csv"
