"""Core workbook validation types and functions.

This module is Frappe-agnostic and contains pure Python implementations
for validating CSV/XLSX workbooks against Pydantic models.
"""

from __future__ import annotations

import csv
from collections.abc import Iterator
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, BinaryIO, Generic, Literal, Mapping, Optional, TextIO, Type, TypeVar

from pydantic import BaseModel, ConfigDict, ValidationError

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
    if config is None:
        config = WorkbookConfig()
    
    # For now, only handle CSV format
    if config.format == TabularFormat.xlsx:
        raise NotImplementedError("XLSX support will be implemented in Phase 3")
    
    # Default to CSV for auto detection (will refine in Phase 4)
    if config.format == TabularFormat.auto:
        format_to_use = TabularFormat.csv
    elif config.format == TabularFormat.csv:
        format_to_use = TabularFormat.csv
    else:
        # For now, assume CSV if not explicitly XLSX
        format_to_use = TabularFormat.csv
    
    if format_to_use == TabularFormat.csv:
        yield from _iter_csv_rows(fp, model, config)


def _iter_csv_rows(
    fp: BinaryIO | TextIO,
    model: Type[TModel],
    config: WorkbookConfig,
) -> Iterator[RowResult[TModel]]:
    """Internal helper to parse and validate CSV rows."""
    import io
    
    # Ensure we have a text stream
    # Check if it's a binary stream by trying to read a small sample
    if hasattr(fp, 'mode') and 'b' in fp.mode:
        # It's a binary file
        content = fp.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8')
        fp = io.StringIO(content)
    elif not hasattr(fp, 'mode'):
        # It might be BytesIO or similar - try to read and check
        original_position = fp.tell() if hasattr(fp, 'tell') else 0
        try:
            sample = fp.read(0)  # Try to read 0 bytes to check type
            fp.seek(original_position)
            if isinstance(sample, bytes):
                # It's binary
                content = fp.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8')
                fp = io.StringIO(content)
        except:
            # If anything fails, assume it's already text
            pass
    
    # Create CSV reader
    reader = csv.DictReader(fp, delimiter=config.delimiter)
    
    # Track row count (1-based, including header)
    current_row_index = 1  # Header is row 1
    rows_processed = 0
    
    # Configure Pydantic model validation based on config.extra
    model_config = {}
    if config.extra == "forbid":
        # Create a dynamic model class with forbid extra
        class StrictModel(model):
            model_config = ConfigDict(extra="forbid")
        model_to_use = StrictModel
    elif config.extra == "allow":
        # Create a dynamic model class with allow extra
        class AllowModel(model):
            model_config = ConfigDict(extra="allow")
        model_to_use = AllowModel
    else:
        # Use original model (which should have extra="ignore" by default)
        model_to_use = model
    
    # Iterate through data rows
    for row_dict in reader:
        current_row_index += 1
        
        # Check if we're at the data start row yet
        if current_row_index < config.data_row_start:
            continue
        
        # Normalize row data: strip whitespace and convert empty strings to None
        normalized_row = {}
        for key, value in row_dict.items():
            # Strip whitespace from both keys and values
            clean_key = key.strip() if key else key
            if isinstance(value, str):
                clean_value = value.strip()
                # Convert empty strings to None for better Pydantic handling
                normalized_row[clean_key] = None if clean_value == '' else clean_value
            else:
                normalized_row[clean_key] = value
        
        # Create row context with original data
        context = RowContext(row_index=current_row_index, raw=row_dict)
        
        # Try to validate the row with normalized data
        try:
            validated_model = model_to_use.model_validate(normalized_row)
            result = RowResult(context=context, model=validated_model, error=None)
        except ValidationError as e:
            result = RowResult(context=context, model=None, error=e)
        
        yield result
        
        rows_processed += 1
        
        # Check stopping conditions
        if config.stop_on_first_error and result.error is not None:
            break
        
        if config.max_rows is not None and rows_processed >= config.max_rows:
            break


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
    rows = list(iter_validated_rows(fp, model, config=config, file_name=file_name))
    
    # Calculate summary
    total_rows = len(rows)
    valid_rows = sum(1 for row in rows if row.is_valid)
    invalid_rows = total_rows - valid_rows
    
    summary = WorkbookSummary(
        total_rows=total_rows,
        valid_rows=valid_rows,
        invalid_rows=invalid_rows
    )
    
    return WorkbookValidationResult(summary=summary, rows=rows)
