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
    elif hasattr(file, 'doctype') and hasattr(file, 'get_content'):
        # Fallback: check if it looks like a Document (for testing with mocks)
        file_doc = file
        if hasattr(file_doc, 'doctype') and file_doc.doctype != "File":
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
        file_size = getattr(file_doc, 'file_size', None)
        if file_size is None:
            # Fallback: we'll check after reading content if file_size not available
            # This is less efficient but handles edge cases
            pass
        elif file_size > config.max_file_size_bytes:
            file_size_mb = file_size / (1024 * 1024)
            max_size_mb = config.max_file_size_bytes / (1024 * 1024)
            file_name = getattr(file_doc, 'file_name', 'Unknown')
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
        content = content.encode('utf-8')
    
    # Check file size from content if file_size attribute was not available
    if config and config.max_file_size_bytes is not None:
        file_size = getattr(file_doc, 'file_size', None)
        if file_size is None:
            # Use content length as fallback
            file_size = len(content)
            if file_size > config.max_file_size_bytes:
                file_size_mb = file_size / (1024 * 1024)
                max_size_mb = config.max_file_size_bytes / (1024 * 1024)
                file_name = getattr(file_doc, 'file_name', 'Unknown')
                raise ValueError(
                    f"File size exceeds maximum limit. "
                    f"File '{file_name}' is {file_size_mb:.2f} MB, "
                    f"but maximum allowed size is {max_size_mb:.2f} MB."
                )
    
    # Wrap content in BytesIO
    fp = io.BytesIO(content)
    
    # Get file name for format detection
    file_name = file_doc.file_name if hasattr(file_doc, 'file_name') else None
    
    # Note: background and job_name are currently ignored
    # Future implementation could use frappe.enqueue() here
    
    # Validate the workbook
    return validate_workbook(
        fp,
        model,
        config=config,
        file_name=file_name,
    )

