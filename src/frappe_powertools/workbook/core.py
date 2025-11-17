"""Core workbook validation types and functions.

This module is Frappe-agnostic and contains pure Python implementations
for validating CSV/XLSX workbooks against Pydantic models.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, BinaryIO, Generic, Literal, Mapping, Optional, TextIO, Type, TypeVar

from pydantic import BaseModel, ValidationError

# Type variable for Pydantic models
TModel = TypeVar("TModel", bound=BaseModel)


class TabularFormat(str, Enum):
    """Supported workbook formats."""
    
    auto = "auto"
    csv = "csv"
    xlsx = "xlsx"


@dataclass
class RowContext:
    """Metadata and raw data for a single workbook row."""
    
    row_index: int  # 1-based sheet row index (Excel/CSV row number)
    raw: Mapping[str, Any]  # header -> cell value (normalized)


@dataclass
class RowResult(Generic[TModel]):
    """Result of validating a single row.
    
    Attributes:
        context: Row metadata and raw data
        model: Validated Pydantic model instance (None if validation failed)
        error: Pydantic ValidationError (None if validation succeeded)
    """
    
    context: RowContext
    model: Optional[TModel]
    error: Optional[ValidationError]
    
    @property
    def is_valid(self) -> bool:
        """Check if the row validation succeeded."""
        return self.model is not None and self.error is None


@dataclass
class WorkbookSummary:
    """Summary statistics for workbook validation."""
    
    total_rows: int
    valid_rows: int
    invalid_rows: int
    
    @property
    def error_rate(self) -> float:
        """Calculate the error rate as a percentage."""
        if self.total_rows == 0:
            return 0.0
        return (self.invalid_rows / self.total_rows) * 100


@dataclass
class WorkbookValidationResult(Generic[TModel]):
    """Complete result of workbook validation.
    
    Attributes:
        summary: Validation statistics
        rows: List of individual row results
    """
    
    summary: WorkbookSummary
    rows: list[RowResult[TModel]]
    
    @property
    def valid_models(self) -> list[TModel]:
        """Get all successfully validated models."""
        return [row.model for row in self.rows if row.model is not None]
    
    @property
    def errors(self) -> list[tuple[int, ValidationError]]:
        """Get all validation errors with row indices."""
        return [(row.context.row_index, row.error) for row in self.rows if row.error is not None]


@dataclass
class WorkbookConfig:
    """Configuration for workbook parsing and validation."""
    
    format: TabularFormat = TabularFormat.auto
    header_row: int = 1  # 1-based row index for headers
    data_row_start: int | None = None  # default: header_row + 1 if None
    delimiter: str = ","  # CSV delimiter
    sheet_name: str | None = None  # default: first sheet for XLSX
    extra: Literal["ignore", "forbid", "allow"] = "ignore"
    stop_on_first_error: bool = False
    max_rows: int | None = None  # None means no explicit limit
    
    def __post_init__(self):
        """Set defaults for computed fields."""
        if self.data_row_start is None:
            self.data_row_start = self.header_row + 1
        
        # Validate configuration
        if self.header_row < 1:
            raise ValueError("header_row must be >= 1")
        if self.data_row_start < self.header_row:
            raise ValueError("data_row_start must be >= header_row")
        if self.max_rows is not None and self.max_rows < 1:
            raise ValueError("max_rows must be >= 1")


def iter_validated_rows(
    fp: BinaryIO | TextIO,
    model: Type[TModel],
    *,
    config: WorkbookConfig | None = None,
    file_name: str | None = None,
) -> Iterator[RowResult[TModel]]:
    """Stream rows from a CSV/XLSX file and validate each row with Pydantic.
    
    Args:
        fp: File-like object containing CSV or XLSX data
        model: Pydantic model class to validate each row against
        config: Configuration for parsing and validation
        file_name: Optional filename to help with format detection
    
    Yields:
        RowResult for each processed row
    
    Notes:
        - Uses config.format to choose CSV vs XLSX, or auto-detects when set to 'auto'
        - Yields RowResult for each row
        - Obeys stop_on_first_error and max_rows
    """
    # Implementation will be added in Phase 2/3
    raise NotImplementedError("This function will be implemented in Phase 2/3")


def validate_workbook(
    fp: BinaryIO | TextIO,
    model: Type[TModel],
    *,
    config: WorkbookConfig | None = None,
    file_name: str | None = None,
) -> WorkbookValidationResult[TModel]:
    """Convenience wrapper around iter_validated_rows that collects all results.
    
    Args:
        fp: File-like object containing CSV or XLSX data
        model: Pydantic model class to validate each row against
        config: Configuration for parsing and validation
        file_name: Optional filename to help with format detection
    
    Returns:
        WorkbookValidationResult with summary and all row results
    """
    # Implementation will be added in Phase 2/3
    raise NotImplementedError("This function will be implemented in Phase 2/3")
