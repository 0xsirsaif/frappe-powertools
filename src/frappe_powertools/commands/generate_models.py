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
    # Validation constraints
    max_length: int | None = None
    non_negative: bool = False
    # For Select fields with Literal types
    select_options: list[str] | None = None


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
    dynamic_links: dict[str, str] = field(default_factory=dict)  # fieldname -> type_field
    multiselect_children: dict[str, str] = field(default_factory=dict)  # fieldname -> child_class
    is_child: bool = False
    docstring: str = ""


# Display-only field types that don't store data (from frappe.model.display_fieldtypes)
SKIP_FIELDTYPES = frozenset(
    [
        "Section Break",
        "Column Break",
        "Tab Break",
        "HTML",
        "Button",
        "Image",
        "Fold",
        "Heading",
    ]
)

# Field types that support length constraints
TEXT_FIELDTYPES_WITH_LENGTH = frozenset(
    [
        "Data",
        "Small Text",
        "Password",
        "Link",
        "Phone",
        "Autocomplete",
    ]
)

# Numeric field types that can have non_negative constraint
NUMERIC_FIELDTYPES = frozenset(
    [
        "Currency",
        "Int",
        "Long Int",
        "Float",
        "Percent",
    ]
)


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
    Uses Decimal for Currency (financial precision) by default.
    """
    mapping: dict[str, str] = {
        # Text fields
        "Data": "str | None",
        "Small Text": "str | None",
        "Long Text": "str | None",
        "Text": "str | None",
        "Text Editor": "str | None",
        "Markdown Editor": "str | None",
        "HTML Editor": "str | None",
        "Code": "str | None",
        "Read Only": "str | None",
        "Phone": "str | None",
        "Autocomplete": "str | None",
        # Select - will be overridden with Literal if options available
        "Select": "str | None",
        # Link fields
        "Link": "str | None",
        "Dynamic Link": "str | None",
        # Numeric fields - use Decimal for Currency (financial precision)
        "Int": "int | None",
        "Long Int": "int | None",
        "Float": "float | None",
        "Currency": "Decimal | None",
        "Percent": "float | None",
        "Rating": "float | None",
        # Boolean
        "Check": "bool",
        # Date/Time fields
        "Date": "date | None",
        "Datetime": "datetime | None",
        "Time": "time | None",
        "Duration": "int | None",  # Stored as seconds
        # Attachment fields
        "Attach": "str | None",
        "Attach Image": "str | None",
        "Signature": "str | None",
        # Special fields
        "Color": "str | None",
        "Icon": "str | None",
        "Barcode": "str | None",
        "Geolocation": "str | None",
        "JSON": "dict[str, Any] | None",
        "Password": "str | None",
        # Table fields - handled separately
        "Table": "Any",
        "Table MultiSelect": "Any",
    }

    return mapping.get(fieldtype, "Any")


def _build_select_literal_type(options: str | None) -> tuple[str, list[str] | None]:
    """Build a Literal type from Select field options.

    Args:
        options: Newline-separated options string from the field

    Returns:
        Tuple of (type_string, option_list) where option_list is None if no valid options
    """
    if not options:
        return "str | None", None

    option_list = [opt.strip() for opt in options.split("\n") if opt.strip()]

    if not option_list:
        return "str | None", None

    # Escape quotes in option values
    escaped = []
    for opt in option_list:
        # Escape backslashes first, then double quotes
        escaped_opt = opt.replace("\\", "\\\\").replace('"', '\\"')
        escaped.append(f'"{escaped_opt}"')

    return f"Literal[{', '.join(escaped)}] | None", option_list


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
        docstring=f"Generated DocModel for {'child ' if is_child else ''}DocType: {doctype}.",
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

        # Skip display-only fields that don't store data
        if fieldtype in SKIP_FIELDTYPES:
            continue

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

        # Handle Table MultiSelect fields
        if fieldtype == "Table MultiSelect" and with_children:
            child_doctype = field_obj.options
            if child_doctype:
                child_class_name = child_class_names.get(
                    child_doctype, _python_class_name_for(child_doctype)
                )
                descriptor.multiselect_children[fieldname] = child_class_name
            continue

        # Handle Dynamic Link fields - track the type field relationship
        if fieldtype == "Dynamic Link":
            type_field = field_obj.options  # The field that specifies the DocType
            if type_field:
                descriptor.dynamic_links[fieldname] = type_field

        # Handle Link fields - track for link projection inference
        if fieldtype == "Link":
            target_doctype = field_obj.options
            if target_doctype:
                link_fields[fieldname] = target_doctype

        # Map fieldtype to Python type
        python_type = _fieldtype_to_python_type(fieldtype)
        select_options: list[str] | None = None

        # For Select fields, generate Literal type from options
        if fieldtype == "Select":
            options_str = getattr(field_obj, "options", None)
            python_type, select_options = _build_select_literal_type(options_str)

        # Extract validation constraints
        max_length: int | None = None
        non_negative: bool = False

        # Length constraint (for text-like fields)
        if fieldtype in TEXT_FIELDTYPES_WITH_LENGTH:
            length = getattr(field_obj, "length", None)
            if length and int(length) > 0:
                max_length = int(length)

        # Non-negative constraint (for numeric fields)
        if fieldtype in NUMERIC_FIELDTYPES:
            if getattr(field_obj, "non_negative", False):
                non_negative = True

        # Determine if field is required
        is_required = bool(getattr(field_obj, "reqd", False))

        # Determine default value
        default_expr = ""
        frappe_default = getattr(field_obj, "default", None)

        if fieldtype == "Check":
            # Check fields: use Frappe default or False
            if frappe_default in (1, "1", True):
                default_expr = "True"
            else:
                default_expr = "False"
        elif is_required:
            # Required fields: no default (truly required)
            default_expr = ""
        elif frappe_default is not None and frappe_default != "":
            # Has explicit Frappe default
            if fieldtype in ("Int", "Long Int"):
                try:
                    default_expr = str(int(frappe_default))
                except (ValueError, TypeError):
                    default_expr = "None"
            elif fieldtype in ("Float", "Currency", "Percent", "Rating"):
                try:
                    if fieldtype == "Currency":
                        default_expr = f"Decimal('{frappe_default}')"
                    else:
                        default_expr = str(float(frappe_default))
                except (ValueError, TypeError):
                    default_expr = "None"
            elif fieldtype == "Select" and select_options and frappe_default in select_options:
                default_expr = f'"{frappe_default}"'
            else:
                default_expr = "None"
        else:
            # Optional field without default
            default_expr = "None"

        # Add field descriptor
        field_descriptors.append(
            FieldDescriptor(
                name=python_identifier,
                python_type=python_type,
                default_expr=default_expr,
                is_required=is_required,
                max_length=max_length,
                non_negative=non_negative,
                select_options=select_options,
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

    # Analyze what imports are needed
    needs_decimal = False
    needs_literal = False
    needs_annotated = False

    for desc in descriptors:
        for field_desc in desc.fields:
            if "Decimal" in field_desc.python_type:
                needs_decimal = True
            if "Literal[" in field_desc.python_type:
                needs_literal = True
            if field_desc.max_length is not None or field_desc.non_negative:
                needs_annotated = True

    # Imports
    lines.append("from __future__ import annotations")
    lines.append("")
    lines.append("from datetime import date, datetime, time")

    if needs_decimal:
        lines.append("from decimal import Decimal")

    # Build typing imports
    typing_imports = ["Any"]
    if needs_annotated:
        typing_imports.insert(0, "Annotated")
    if needs_literal:
        typing_imports.append("Literal")
    lines.append(f"from typing import {', '.join(typing_imports)}")

    if needs_annotated:
        lines.append("")
        lines.append("from pydantic import Field")

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

        # Dynamic Links
        if desc.dynamic_links:
            dynamic_links_items = sorted(desc.dynamic_links.items())
            lines.append("        dynamic_links: dict[str, str] = {")
            for fieldname, type_field in dynamic_links_items:
                lines.append(f'            "{fieldname}": "{type_field}",')
            lines.append("        }")

        # Multiselect Children
        if desc.multiselect_children:
            multiselect_items = sorted(desc.multiselect_children.items())
            lines.append("        multiselect: dict[str, type[DocModel]] = {")
            for fieldname, child_class in multiselect_items:
                lines.append(f'            "{fieldname}": {child_class},')
            lines.append("        }")

        lines.append("")

        # Fields - render with proper constraints
        for field_desc in desc.fields:
            field_line = _render_field(field_desc)
            lines.append(field_line)

        # Always include extras
        if "extras" not in [f.name for f in desc.fields]:
            lines.append("    extras: dict[str, Any] = {}")

    # Add model_rebuild() calls for forward reference resolution
    lines.append("")
    lines.append("")
    lines.append("# Rebuild models to resolve forward references")
    for desc in descriptors:
        lines.append(f"{desc.class_name}.model_rebuild()")

    return "\n".join(lines)


def _render_field(field_desc: FieldDescriptor) -> str:
    """Render a single field with proper type annotations and constraints.

    Args:
        field_desc: The field descriptor to render

    Returns:
        A single line of Python code for the field
    """
    has_constraints = field_desc.max_length is not None or field_desc.non_negative

    if has_constraints:
        # Build Field() constraints
        constraints = []
        if field_desc.max_length is not None:
            constraints.append(f"max_length={field_desc.max_length}")
        if field_desc.non_negative:
            constraints.append("ge=0")

        field_call = f"Field({', '.join(constraints)})"

        # Extract base type (remove " | None" for Annotated wrapping)
        base_type = field_desc.python_type
        is_optional = base_type.endswith(" | None")
        if is_optional:
            base_type = base_type[:-7]  # Remove " | None"

        if field_desc.is_required:
            # Required with constraints: Annotated[type, Field(...)]
            annotated_type = f"Annotated[{base_type}, {field_call}]"
            return f"    {field_desc.name}: {annotated_type}"
        else:
            # Optional with constraints: Annotated[type, Field(...)] | None = default
            annotated_type = f"Annotated[{base_type}, {field_call}] | None"
            default = field_desc.default_expr or "None"
            return f"    {field_desc.name}: {annotated_type} = {default}"
    else:
        # No constraints - simple type annotation
        if field_desc.is_required:
            # Required field: no default
            return f"    {field_desc.name}: {field_desc.python_type.replace(' | None', '')}"
        else:
            # Optional field with default
            default = field_desc.default_expr or "None"
            return f"    {field_desc.name}: {field_desc.python_type} = {default}"


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
