"""Frappe-specific adapter for workbook validation.

This module provides Frappe-aware helpers that work with Frappe File documents.
"""

from __future__ import annotations

import io
from typing import TYPE_CHECKING, Type

try:
    import frappe
    from frappe.model.document import Document
except ImportError:
    frappe = None  # type: ignore[assignment]
    Document = None  # type: ignore[assignment, misc]

from pydantic import BaseModel

from frappe_powertools.workbook.core import (
    WorkbookConfig,
    WorkbookValidationResult,
    validate_workbook,
)

if TYPE_CHECKING:
    from frappe.model.document import Document as FrappeDocument


def validate_file(
    file: str | "FrappeDocument",
    model: Type[BaseModel],
    *,
    config: WorkbookConfig | None = None,
    background: bool | None = None,
    job_name: str | None = None,
) -> WorkbookValidationResult:
    """Validate a workbook file stored in Frappe.

    This function accepts a Frappe File document (by name or as a Document instance)
    and validates its contents using Pydantic models.

    Args:
        file: File document name (string) or File Document instance
        model: Pydantic model class to validate each row against
        config: Optional configuration for parsing and validation
        background: If True, run validation in background (currently ignored)
        job_name: Optional name for background job (currently ignored)

    Returns:
        WorkbookValidationResult with summary and all row results

    Raises:
        ImportError: If frappe is not installed
        ValueError: If file is not found or cannot be read
        PermissionError: If user doesn't have permission to read the file

    Note:
        The `background` and `job_name` parameters are currently ignored.
        All validation runs synchronously. These parameters are included
        for future extensibility.
    """
    if frappe is None:
        raise ImportError(
            "frappe is required for validate_file. "
            "This function is only available in Frappe environments."
        )

    # Resolve the File document
    if isinstance(file, str):
        try:
            file_doc = frappe.get_doc("File", file)
        except frappe.DoesNotExistError:
            raise ValueError(f"File document not found: {file}")
    elif Document is not None and isinstance(file, Document):
        file_doc = file
        # Ensure it's a File document
        if file_doc.doctype != "File":
            raise ValueError(f"Document is not a File document: {file_doc.doctype}")
    elif hasattr(file, "doctype") and hasattr(file, "get_content"):
        # Fallback: check if it looks like a Document (for testing with mocks)
        file_doc = file
        if hasattr(file_doc, "doctype") and file_doc.doctype != "File":
            raise ValueError(f"Document is not a File document: {file_doc.doctype}")
    else:
        raise TypeError(
            f"file must be a string (File name) or File Document instance, "
            f"got {type(file).__name__}"
        )

    # Check permissions
    if not file_doc.has_permission("read"):
        raise PermissionError(
            f"Permission denied: You do not have read permission for file {file_doc.name}"
        )

    # Check file size if limit is specified in config
    if config and config.max_file_size_bytes is not None:
        file_size = getattr(file_doc, "file_size", None)
        if file_size is None:
            # Fallback: we'll check after reading content if file_size not available
            # This is less efficient but handles edge cases
            pass
        elif file_size > config.max_file_size_bytes:
            file_size_mb = file_size / (1024 * 1024)
            max_size_mb = config.max_file_size_bytes / (1024 * 1024)
            file_name = getattr(file_doc, "file_name", "Unknown")
            raise ValueError(
                f"File size exceeds maximum limit. "
                f"File '{file_name}' is {file_size_mb:.2f} MB, "
                f"but maximum allowed size is {max_size_mb:.2f} MB."
            )

    # Get file content
    try:
        content = file_doc.get_content()
    except Exception as e:
        raise ValueError(f"Failed to read file content: {e}") from e

    if content is None:
        raise ValueError("File content is empty or could not be read")

    # Ensure content is bytes
    if isinstance(content, str):
        content = content.encode("utf-8")

    # Check file size from content if file_size attribute was not available
    if config and config.max_file_size_bytes is not None:
        file_size = getattr(file_doc, "file_size", None)
        if file_size is None:
            # Use content length as fallback
            file_size = len(content)
            if file_size > config.max_file_size_bytes:
                file_size_mb = file_size / (1024 * 1024)
                max_size_mb = config.max_file_size_bytes / (1024 * 1024)
                file_name = getattr(file_doc, "file_name", "Unknown")
                raise ValueError(
                    f"File size exceeds maximum limit. "
                    f"File '{file_name}' is {file_size_mb:.2f} MB, "
                    f"but maximum allowed size is {max_size_mb:.2f} MB."
                )

    # Wrap content in BytesIO
    fp = io.BytesIO(content)

    # Get file name for format detection
    file_name = file_doc.file_name if hasattr(file_doc, "file_name") else None

    # Note: background and job_name are currently ignored
    # Future implementation could use frappe.enqueue() here

    # Validate the workbook
    return validate_workbook(
        fp,
        model,
        config=config,
        file_name=file_name,
    )


def build_validation_error_messages(
    result: WorkbookValidationResult,
    model: Type[BaseModel] | None = None,
    *,
    max_errors: int = 50,
    group_by: str = "row",
    include_raw_data: bool = True,
    format_style: str = "flat",
) -> tuple[list[str], dict]:
    """Build user-friendly error messages from validation results.

    This function processes WorkbookValidationResult and formats errors
    for display to Frappe users, with structured error details for
    programmatic access.

    Args:
        result: WorkbookValidationResult from workbook package
        model: Pydantic model class to extract field aliases from (optional)
            If not provided, will try to extract from first valid row in result.
            If extraction fails, field names will be used as-is.
        max_errors: Maximum number of errors to show in messages (default: 50)
        group_by: How to group errors - "row" (default), "type", or "both"
            (only used when format_style="structured")
        include_raw_data: Whether to include raw row data in error_details
        format_style: "flat" (default) for simple list suitable for Frappe UI,
            or "structured" for grouped format with summary and headers

    Returns:
        Tuple of (formatted_messages, error_details):
        - formatted_messages: List of strings ready for frappe.throw(as_list=True)
        - error_details: Dict with structured error information for programmatic access

    Example:
        >>> result = validate_file(file_doc.name, MyModel, config=config)
        >>> if result.summary.invalid_rows > 0:
        ...     messages, details = build_validation_error_messages(
        ...         result, model=MyModel, max_errors=50, format_style="flat"
        ...     )
        ...     frappe.throw(messages, title="Validation Failed", as_list=True)
    """
    # Extract field name map from model
    if model is not None:
        field_name_map = _extract_field_aliases_from_model(model)
    else:
        # Try to extract from first valid row if available
        field_name_map = None
        for row_result in result.rows:
            if row_result.is_valid and row_result.model:
                field_name_map = _extract_field_aliases_from_model(type(row_result.model))
                break

        # Fallback: empty dict (will use field names as-is)
        if field_name_map is None:
            field_name_map = {}

    # Initialize error collections
    errors_by_row: dict[int, list[dict]] = {}
    error_count = 0

    # Process all invalid rows
    for row_result in result.rows:
        if not row_result.is_valid and row_result.error:
            row_index = row_result.context.row_index
            raw_data = row_result.context.raw

            # Extract errors from ValidationError
            row_errors = []
            for err in row_result.error.errors():
                field_path_parts = err.get("loc", [])

                # Map Python field names to Excel column names
                mapped_path = []
                for part in field_path_parts:
                    if isinstance(part, str) and part in field_name_map:
                        mapped_path.append(field_name_map[part])
                    else:
                        mapped_path.append(str(part))

                field_path = " -> ".join(mapped_path) if mapped_path else ""
                error_msg = err.get("msg", "Validation error")
                error_type = err.get("type", "unknown")
                input_value = err.get("input")

                # Categorize error type
                category = _categorize_error(error_type, error_msg)

                error_info = {
                    "field": field_path,
                    "message": error_msg,
                    "error_type": error_type,
                    "category": category,
                    "input_value": input_value,
                }

                row_errors.append(error_info)
                error_count += 1

            # Store errors for this row
            if row_errors:
                errors_by_row[row_index] = {
                    "row_index": row_index,
                    "errors": row_errors,
                    "error_count": len(row_errors),
                    "raw_data": raw_data if include_raw_data else None,
                }

    # Build formatted messages
    formatted_messages = []

    if format_style == "flat":
        # Flat format: simple list, no grouping, no summary, no empty lines
        errors_shown = 0
        for row_index in sorted(errors_by_row.keys()):
            if errors_shown >= max_errors:
                break

            row_info = errors_by_row[row_index]
            for error in row_info["errors"]:
                if errors_shown >= max_errors:
                    break

                field = error["field"]
                message = error["message"]
                input_val = error["input_value"]

                # Build flat error line: "Row X, Field Name: error message"
                if field:
                    if input_val is not None and input_val != "":
                        error_line = f"Row {row_index}, {field} = '{input_val}': {message}"
                    else:
                        error_line = f"Row {row_index}, {field}: {message}"
                else:
                    error_line = f"Row {row_index}: {message}"

                formatted_messages.append(error_line)
                errors_shown += 1

            if errors_shown >= max_errors:
                break

        # Add truncation message if needed
        if error_count > max_errors:
            remaining = error_count - max_errors
            formatted_messages.append(
                f"... and {remaining} more error(s). Please fix the errors above and try again."
            )

    else:
        # Structured format: with summary, grouping, and headers
        summary = (
            f"File validation failed: {result.summary.invalid_rows} row(s) "
            f"with {error_count} error(s) out of {result.summary.total_rows} total row(s)."
        )
        formatted_messages.append(summary)
        formatted_messages.append("")  # Empty line for readability

        # Group and format errors
        if group_by in ("row", "both"):
            # Group by row
            rows_shown = 0
            for row_index in sorted(errors_by_row.keys()):
                if rows_shown >= max_errors:
                    remaining_rows = len(errors_by_row) - rows_shown
                    formatted_messages.append(
                        f"... and {remaining_rows} more row(s) with errors. "
                        f"Please fix the errors above and try again."
                    )
                    break

                row_info = errors_by_row[row_index]
                formatted_messages.append(f"Row {row_index} ({row_info['error_count']} error(s)):")

                for error in row_info["errors"]:
                    field = error["field"]
                    message = error["message"]
                    input_val = error["input_value"]

                    # Build error line
                    if field:
                        if input_val is not None and input_val != "":
                            error_line = f"  • {field} = '{input_val}': {message}"
                        else:
                            error_line = f"  • {field}: {message}"
                    else:
                        error_line = f"  • {message}"

                    formatted_messages.append(error_line)

                formatted_messages.append("")  # Empty line between rows
                rows_shown += 1

    # Build error_details dict for programmatic access
    error_details = {
        "summary": {
            "total_rows": result.summary.total_rows,
            "valid_rows": result.summary.valid_rows,
            "invalid_rows": result.summary.invalid_rows,
            "error_count": error_count,
            "error_rate": result.summary.error_rate,
        },
        "errors_by_row": errors_by_row,
        "invalid_row_indices": sorted(errors_by_row.keys()),
    }

    return formatted_messages, error_details


def _categorize_error(error_type: str, error_msg: str) -> str:
    """Categorize error type for better grouping."""
    if error_type == "missing":
        return "missing_required"
    elif error_type in (
        "string_type",
        "date_parsing",
        "time_parsing",
        "float_parsing",
        "int_parsing",
    ):
        return "invalid_format"
    elif "does not exist" in error_msg.lower():
        return "missing_reference"
    elif error_type == "value_error" and any(
        keyword in error_msg.lower() for keyword in ["required", "empty", "cannot be zero"]
    ):
        return "missing_required"
    elif error_type == "value_error":
        return "business_rule"
    else:
        return "other"


def _extract_field_aliases_from_model(model: Type[BaseModel]) -> dict[str, str]:
    """Extract field name to alias mapping from Pydantic model.

    Args:
        model: Pydantic model class

    Returns:
        Dictionary mapping Python field names to their aliases (Excel column names)
    """
    field_name_map: dict[str, str] = {}

    # Access model_fields which contains field information
    if hasattr(model, "model_fields"):
        for field_name, field_info in model.model_fields.items():
            # Get alias if it exists, otherwise use field name
            alias = field_info.alias if field_info.alias else field_name
            field_name_map[field_name] = alias

    return field_name_map
