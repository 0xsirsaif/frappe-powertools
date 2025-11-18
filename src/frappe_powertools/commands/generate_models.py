"""Generate DocModel classes from Frappe DocType metadata."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

try:
    import frappe
except ImportError:
    frappe = None  # type: ignore


@dataclass
class FieldDescriptor:
    """Descriptor for a single field in a DocModel."""

    name: str
    python_type: str
    default_expr: str = ""
    is_required: bool = False


@dataclass
class ModelDescriptor:
    """Descriptor for a complete DocModel class."""

    class_name: str
    doctype: str
    fields: list[FieldDescriptor] = field(default_factory=list)
    children: dict[str, str] = field(default_factory=dict)  # fieldname -> child_class_name
    links: dict[str, tuple[str, str, str]] = field(
        default_factory=dict
    )  # local_field -> (link_field, target_doctype, target_field)
    is_child: bool = False
    docstring: str = ""


def _python_class_name_for(doctype: str) -> str:
    """Convert a DocType name to a valid Python class name.

    Examples:
        "Training Batch" -> "TrainingBatch"
        "Sales Invoice" -> "SalesInvoice"
        "Student_Record" -> "StudentRecord"
        "Test DocType" -> "TestDocType"
    """
    # Split on whitespace, underscores, dashes, and capitalize each part
    import re

    # Split on non-alphanumeric characters, but preserve the parts
    parts = re.split(r"[\s_\-]+", doctype)
    # Filter out empty parts
    parts = [part for part in parts if part]

    if not parts:
        # Fallback: use the original name with replacements
        cleaned = doctype.replace(" ", "").replace("_", "").replace("-", "")
        return cleaned.capitalize() if cleaned else "DocType"

    # Capitalize each part, preserving existing capitalization within words
    # This handles cases like "DocType" -> "DocType" (not "Doctype")
    capitalized_parts = []
    for part in parts:
        if part:
            # If the part already has mixed case (like "DocType"), preserve it
            if part != part.lower() and part != part.upper():
                capitalized_parts.append(part)
            else:
                # Otherwise, capitalize the first letter
                capitalized_parts.append(part.capitalize())

    return "".join(capitalized_parts)


def _python_identifier_for(fieldname: str) -> str | None:
    """Convert a fieldname to a valid Python identifier.

    Returns None if the fieldname cannot be converted to a valid identifier.
    """
    if not fieldname:
        return None

    # Check if it's already a valid identifier
    if fieldname.isidentifier():
        return fieldname

    # Try to make it valid by replacing invalid chars
    cleaned = ""
    for char in fieldname:
        if char.isalnum() or char == "_":
            cleaned += char
        elif char in (" ", "-", "."):
            cleaned += "_"
        else:
            # Invalid character, cannot convert
            return None

    if cleaned and cleaned[0].isdigit():
        # Cannot start with digit
        return None

    return cleaned if cleaned else None


def _fieldtype_to_python_type(fieldtype: str) -> str:
    """Map Frappe fieldtype to Python type string.

    Returns a type annotation string like "str | None" or "bool".
    """
    mapping: dict[str, str] = {
        "Data": "str | None",
        "Small Text": "str | None",
        "Long Text": "str | None",
        "Text": "str | None",
        "Text Editor": "str | None",
        "Read Only": "str | None",
        "Select": "str | None",
        "Link": "str | None",
        "Dynamic Link": "str | None",
        "Int": "int | None",
        "Float": "float | None",
        "Currency": "float | None",
        "Percent": "float | None",
        "Check": "bool",
        "Date": "date | None",
        "Datetime": "datetime | None",
        "Time": "time | None",
        "Attach": "str | None",
        "Attach Image": "str | None",
        "HTML": "str | None",
        "Table": "Any",  # Handled separately
        "Table MultiSelect": "Any",  # Handled separately
    }

    return mapping.get(fieldtype, "Any")


def _collect_doctype_meta(doctype: str) -> dict[str, Any]:
    """Collect metadata for a DocType using Frappe's API.

    Returns a dictionary with metadata about the DocType.
    """
    if frappe is None:
        raise ImportError(
            "Frappe is required for DocType introspection. Run this in a Frappe environment."
        )

    try:
        meta = frappe.get_meta(doctype)
    except Exception as e:
        raise ValueError(f"DocType '{doctype}' does not exist or cannot be accessed: {e}") from e

    return {
        "name": doctype,
        "meta": meta,
        "is_child": meta.istable,
        "fields": list(meta.fields),
    }


def _build_model_descriptor(
    doctype: str,
    meta_info: dict[str, Any],
    *,
    with_children: bool = True,
    with_links: bool = True,
    child_class_names: dict[str, str] | None = None,
) -> ModelDescriptor:
    """Build a ModelDescriptor from DocType metadata.

    Args:
        doctype: The DocType name
        meta_info: Metadata dictionary from _collect_doctype_meta
        with_children: Whether to include child table mappings
        with_links: Whether to infer Meta.links from fetch_from
        child_class_names: Mapping of child doctype names to their class names

    Returns:
        A ModelDescriptor for the DocType
    """
    meta = meta_info["meta"]
    fields_list = meta_info["fields"]
    is_child = meta_info["is_child"]

    class_name = _python_class_name_for(doctype)
    descriptor = ModelDescriptor(
        class_name=class_name,
        doctype=doctype,
        is_child=is_child,
        docstring=f'Generated DocModel for {"child " if is_child else ""}DocType: {doctype}.',
    )

    if child_class_names is None:
        child_class_names = {}

    # Track link fields for link projection inference
    link_fields: dict[str, str] = {}  # fieldname -> target_doctype

    # Process fields
    field_descriptors: list[FieldDescriptor] = []
    processed_fieldnames: set[str] = set()

    # Always include name field first
    if not is_child:
        field_descriptors.append(
            FieldDescriptor(name="name", python_type="str | None", default_expr="None")
        )
        processed_fieldnames.add("name")

    # For child tables, include standard parent fields
    if is_child:
        for parent_field in ["name", "parent", "parenttype", "parentfield", "idx"]:
            field_descriptors.append(
                FieldDescriptor(
                    name=parent_field,
                    python_type="str | None" if parent_field != "idx" else "int | None",
                    default_expr="None",
                )
            )
            processed_fieldnames.add(parent_field)

    # Process all fields
    for field_obj in fields_list:
        fieldname = field_obj.fieldname
        fieldtype = field_obj.fieldtype

        # Skip if already processed or invalid identifier
        if fieldname in processed_fieldnames:
            continue

        python_identifier = _python_identifier_for(fieldname)
        if python_identifier is None:
            # Skip invalid identifiers
            continue

        # Handle Table fields (child tables)
        if fieldtype == "Table" and with_children:
            child_doctype = field_obj.options
            if child_doctype:
                child_class_name = child_class_names.get(
                    child_doctype, _python_class_name_for(child_doctype)
                )
                descriptor.children[fieldname] = child_class_name
            # Don't add Table fields as regular fields
            continue

        # Handle Link fields - track for link projection inference
        if fieldtype == "Link":
            target_doctype = field_obj.options
            if target_doctype:
                link_fields[fieldname] = target_doctype

        # Map fieldtype to Python type
        python_type = _fieldtype_to_python_type(fieldtype)

        # Determine default value
        default_expr = ""
        is_required = bool(field_obj.reqd)

        if fieldtype == "Check":
            default_expr = "False"
        elif not is_required:
            if python_type.endswith(" | None"):
                default_expr = "None"
            else:
                default_expr = "None"

        # Add field descriptor
        field_descriptors.append(
            FieldDescriptor(
                name=python_identifier,
                python_type=python_type,
                default_expr=default_expr,
                is_required=is_required,
            )
        )
        processed_fieldnames.add(fieldname)

    # Infer Meta.links from fetch_from fields
    if with_links:
        for field_obj in fields_list:
            fieldname = field_obj.fieldname
            fetch_from = getattr(field_obj, "fetch_from", None)

            if not fetch_from:
                continue

            # Parse fetch_from pattern: "link_field.target_field"
            # Example: "student.full_name" -> link_field="student", target_field="full_name"
            if "." in fetch_from:
                parts = fetch_from.split(".", 1)
                if len(parts) == 2:
                    link_fieldname, target_fieldname = parts

                    # Check if the link field exists and is a Link field
                    if link_fieldname in link_fields:
                        target_doctype = link_fields[link_fieldname]

                        # Only add if the fieldname is a valid identifier
                        python_identifier = _python_identifier_for(fieldname)
                        if python_identifier:
                            descriptor.links[python_identifier] = (
                                link_fieldname,
                                target_doctype,
                                target_fieldname,
                            )

                            # Add the projection field to the model only if not already added
                            if fieldname not in processed_fieldnames:
                                field_descriptors.append(
                                    FieldDescriptor(
                                        name=python_identifier,
                                        python_type="str | None",
                                        default_expr="None",
                                    )
                                )
                                processed_fieldnames.add(fieldname)

    descriptor.fields = field_descriptors
    return descriptor


def _render_models(descriptors: list[ModelDescriptor]) -> str:
    """Render a list of ModelDescriptors to Python source code.

    Args:
        descriptors: List of ModelDescriptors to render

    Returns:
        Python source code as a string
    """
    lines: list[str] = []

    # Imports
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from datetime import date, datetime, time")
    lines.append("from typing import Any")
    lines.append("")
    lines.append("from frappe_powertools.orm import DocModel")
    lines.append("")
    lines.append("")

    # Render each model
    for i, desc in enumerate(descriptors):
        if i > 0:
            lines.append("")
            lines.append("")

        # Class docstring
        lines.append(f"class {desc.class_name}(DocModel):")
        lines.append(f'    """{desc.docstring}"""')
        lines.append("")

        # Meta class
        lines.append("    class Meta:")
        lines.append(f'        doctype = "{desc.doctype}"')

        # Children
        if desc.children:
            children_items = sorted(desc.children.items())
            lines.append("        children: dict[str, type[DocModel]] = {")
            for fieldname, child_class in children_items:
                lines.append(f'            "{fieldname}": {child_class},')
            lines.append("        }")
        else:
            lines.append("        children: dict[str, type[DocModel]] = {}")

        # Links
        if desc.links:
            links_items = sorted(desc.links.items())
            lines.append("        links: dict[str, tuple[str, str, str]] = {")
            for local_field, (link_field, target_doctype, target_field) in links_items:
                lines.append(
                    f'            "{local_field}": ("{link_field}", "{target_doctype}", "{target_field}"),'
                )
            lines.append("        }")
        else:
            lines.append("        links: dict[str, tuple[str, str, str]] = {}")

        lines.append("")

        # Fields
        for field_desc in desc.fields:
            field_line = f"    {field_desc.name}: {field_desc.python_type}"
            if field_desc.default_expr:
                field_line += f" = {field_desc.default_expr}"
            lines.append(field_line)

        # Always include extras
        if "extras" not in [f.name for f in desc.fields]:
            lines.append("    extras: dict[str, Any] = {}")

    return "\n".join(lines)


def generate_docmodels(
    doctypes: list[str],
    *,
    with_children: bool = True,
    with_links: bool = True,
) -> str:
    """Generate Python source code for DocModel classes for the given DocTypes.

    This function does not write any files; it only returns a string.
    A CLI wrapper is responsible for printing the string to stdout.

    Args:
        doctypes: List of DocType names to generate models for
        with_children: Whether to include child table models
        with_links: Whether to infer Meta.links from fetch_from fields

    Returns:
        Python source code as a string

    Raises:
        ImportError: If Frappe is not available
        ValueError: If any DocType does not exist
    """
    if frappe is None:
        raise ImportError(
            "Frappe is required for DocType introspection. "
            "Run this command in a Frappe environment."
        )

    # Normalize and sort doctype names
    normalized_doctypes = sorted(set(doctypes))

    if not normalized_doctypes:
        raise ValueError("At least one DocType must be specified")

    # Collect metadata for all doctypes
    all_meta: dict[str, dict[str, Any]] = {}
    for doctype in normalized_doctypes:
        all_meta[doctype] = _collect_doctype_meta(doctype)

    # Build child class name mapping
    child_class_names: dict[str, str] = {}
    if with_children:
        for doctype, meta_info in all_meta.items():
            meta = meta_info["meta"]
            for field_obj in meta.fields:
                if field_obj.fieldtype == "Table":
                    child_doctype = field_obj.options
                    if child_doctype and child_doctype not in child_class_names:
                        child_class_names[child_doctype] = _python_class_name_for(child_doctype)

    # Collect child doctypes if with_children is True
    child_doctypes: list[str] = []
    if with_children:
        for doctype, meta_info in all_meta.items():
            meta = meta_info["meta"]
            for field_obj in meta.fields:
                if field_obj.fieldtype == "Table":
                    child_doctype = field_obj.options
                    if child_doctype and child_doctype not in normalized_doctypes:
                        child_doctypes.append(child_doctype)

        # Collect metadata for child doctypes
        for child_doctype in sorted(set(child_doctypes)):
            try:
                all_meta[child_doctype] = _collect_doctype_meta(child_doctype)
                child_class_names[child_doctype] = _python_class_name_for(child_doctype)
            except ValueError:
                # Child doctype doesn't exist, skip it
                pass

    # Build descriptors for all doctypes (children first, then parents)
    all_descriptors: list[ModelDescriptor] = []
    processed_doctypes: set[str] = set()

    # First pass: process child doctypes
    for doctype in sorted(all_meta.keys()):
        meta_info = all_meta[doctype]
        if meta_info["is_child"] and doctype not in processed_doctypes:
            descriptor = _build_model_descriptor(
                doctype,
                meta_info,
                with_children=with_children,
                with_links=with_links,
                child_class_names=child_class_names,
            )
            all_descriptors.append(descriptor)
            processed_doctypes.add(doctype)

    # Second pass: process parent doctypes
    for doctype in normalized_doctypes:
        if doctype not in processed_doctypes:
            meta_info = all_meta[doctype]
            descriptor = _build_model_descriptor(
                doctype,
                meta_info,
                with_children=with_children,
                with_links=with_links,
                child_class_names=child_class_names,
            )
            all_descriptors.append(descriptor)
            processed_doctypes.add(doctype)

    # Render to Python code
    return _render_models(all_descriptors)
