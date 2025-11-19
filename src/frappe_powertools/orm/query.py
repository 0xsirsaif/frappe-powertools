from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Type, TypeVar

from ..doctype_schema import DocModel

TDoc = TypeVar("TDoc", bound=DocModel)


@dataclass
class ParsedLookup:
    """Parsed lookup from filter key.

    Attributes:
        field_name: The field name (without lookup suffix)
        lookup: The lookup type ("exact", "gt", "gte", "lt", "lte", "range", "in", "not_in", "isnull", "blank")
        value: The filter value
    """

    field_name: str
    lookup: str
    value: Any


def _parse_lookup(key: str, value: Any) -> ParsedLookup:
    """Parse a filter key into field name and lookup type.

    Args:
        key: Filter key (e.g., "status", "score__gt", "field__name")
        value: Filter value

    Returns:
        ParsedLookup with field_name, lookup, and value

    Examples:
        >>> _parse_lookup("status", "Active")
        ParsedLookup(field_name='status', lookup='exact', value='Active')
        >>> _parse_lookup("score__gt", 80)
        ParsedLookup(field_name='score', lookup='gt', value=80)
        >>> _parse_lookup("field__name", "value")
        ParsedLookup(field_name='field', lookup='name', value='value')
    """
    if "__" in key:
        field_name, lookup = key.rsplit("__", 1)
    else:
        field_name, lookup = key, "exact"
    return ParsedLookup(field_name=field_name, lookup=lookup, value=value)


@dataclass
class ReadQuery(Generic[TDoc]):
    """Query builder for read-only operations on DocType data.

    This class accumulates query parameters (filters, ordering, limits, etc.)
    and provides a chainable API similar to Django ORM or SQLAlchemy.

    Example:
        query = ReadQuery(TrainingBatchSchema)
        results = (
            query
            .filter(status="Active")
            .order_by("-start_date")
            .limit(10)
            .all()
        )
    """

    schema: Type[TDoc]
    filters: List[dict[str, Any]] = field(default_factory=list)
    order_by_fields: List[str] = field(default_factory=list)
    limit_value: int | None = None
    prefetch_fields: List[str] = field(default_factory=list)
    select_related_fields: List[str] = field(default_factory=list)

    def filter(self, **kwargs: Any) -> ReadQuery[TDoc]:
        """Add filter conditions to the query.

        Multiple calls to filter() are combined with AND logic.

        Args:
            **kwargs: Field name to value mappings for filtering

        Returns:
            Self for method chaining

        Example:
            query.filter(status="Active").filter(program="PROG-001")
        """
        self.filters.append(kwargs)
        return self

    def order_by(self, *fields: str) -> ReadQuery[TDoc]:
        """Specify ordering for the query results.

        Use "-field_name" for descending order.

        Args:
            *fields: Field names to order by (prefix with "-" for descending)

        Returns:
            Self for method chaining

        Example:
            query.order_by("-start_date", "name")
        """
        self.order_by_fields.extend(fields)
        return self

    def limit(self, n: int) -> ReadQuery[TDoc]:
        """Limit the number of results returned.

        Args:
            n: Maximum number of results to return

        Returns:
            Self for method chaining

        Example:
            query.limit(10)
        """
        self.limit_value = n
        return self

    def prefetch(self, *fields: str) -> ReadQuery[TDoc]:
        """Prefetch child table data for the specified fields.

        Args:
            *fields: Child table field names to prefetch

        Returns:
            Self for method chaining

        Example:
            query.prefetch("participants", "items")
        """
        self.prefetch_fields.extend(fields)
        return self

    def select_related(self, *fields: str) -> ReadQuery[TDoc]:
        """Select related data from linked DocTypes.

        Args:
            *fields: Link field names to join and fetch related data

        Returns:
            Self for method chaining

        Example:
            query.select_related("program", "instructor")
        """
        self.select_related_fields.extend(fields)
        return self

    def _build_condition(self, table, parsed: ParsedLookup):
        """Build a PyPika condition from a parsed lookup.

        Args:
            table: PyPika table object
            parsed: ParsedLookup instance

        Returns:
            PyPika condition expression

        Raises:
            ValueError: If lookup type is not supported
        """
        field = table[parsed.field_name]
        lookup = parsed.lookup
        value = parsed.value

        if lookup == "exact":
            return field == value
        elif lookup == "gt":
            return field > value
        elif lookup == "gte":
            return field >= value
        elif lookup == "lt":
            return field < value
        elif lookup == "lte":
            return field <= value
        elif lookup == "range":
            if not isinstance(value, (tuple, list)) or len(value) != 2:
                raise ValueError(
                    f"range lookup requires a tuple or list of 2 values, got {type(value).__name__}"
                )
            low, high = value
            return field.between(low, high)
        elif lookup == "in":
            if isinstance(value, str):
                raise ValueError(
                    f"in lookup requires an iterable (list, tuple, set), not a string. "
                    f"Use exact lookup for string equality: {parsed.field_name}='{value}'"
                )
            if not hasattr(value, "__iter__"):
                raise ValueError(
                    f"in lookup requires an iterable (list, tuple, set), got {type(value).__name__}"
                )
            value_list = list(value)
            if not value_list:
                # Empty list: condition is always false (field IN () is always false in SQL)
                # Return a condition that will never match by using an impossible condition
                return field != field
            return field.isin(value_list)
        elif lookup == "not_in":
            if isinstance(value, str):
                raise ValueError(
                    "not_in lookup requires an iterable (list, tuple, set), not a string. "
                    "Use exact lookup with negation or exclude() for string inequality"
                )
            if not hasattr(value, "__iter__"):
                raise ValueError(
                    f"not_in lookup requires an iterable (list, tuple, set), got {type(value).__name__}"
                )
            value_list = list(value)
            if not value_list:
                # Empty list: condition is always true (field NOT IN () is always true in SQL)
                # Return a condition that is always true
                return field == field
            return ~(field.isin(value_list))
        elif lookup == "isnull":
            if not isinstance(value, bool):
                raise ValueError(
                    f"isnull lookup requires a boolean value (True/False), got {type(value).__name__}"
                )
            if value:
                return field.isnull()
            else:
                return field.notnull()
        elif lookup == "blank":
            if not isinstance(value, bool):
                raise ValueError(
                    f"blank lookup requires a boolean value (True/False), got {type(value).__name__}"
                )
            if value:
                # blank=True: IS NULL OR = ""
                return (field.isnull()) | (field == "")
            else:
                # blank=False: NOT (IS NULL OR = "")
                return ~((field.isnull()) | (field == ""))
        else:
            raise ValueError(
                f"Unsupported lookup '{lookup}' on field '{parsed.field_name}'. "
                f"Supported lookups: exact, gt, gte, lt, lte, range, in, not_in, isnull, blank"
            )

    def _build_frappe_query(self):
        """Build a Frappe Query Builder query from accumulated parameters.

        Returns:
            A Frappe QueryBuilder instance ready to execute

        Note:
            Supports parent queries with optional link field joins via select_related.
        """
        try:
            import frappe
            from pypika import Order
            from frappe.database.query import LinkTableField
        except ImportError:
            raise ImportError(
                "Frappe is required for query execution. "
                "Install frappe or run in a Frappe environment."
            )

        doctype = self.schema.Meta.doctype
        table = frappe.qb.DocType(doctype)

        # Get declared field names from the schema (excluding 'extras')
        set(self.schema.model_fields.keys()) - {"extras"}

        # Build field list - select all fields using *
        # Frappe will handle column selection and permissions
        query = frappe.qb.from_(table).select("*")

        # Add link field projections if select_related is used
        if (
            self.select_related_fields
            and hasattr(self.schema, "Meta")
            and hasattr(self.schema.Meta, "links")
        ):
            links_map = self.schema.Meta.links
            if links_map:
                # For each select_related field, find matching projections
                for link_field_name in self.select_related_fields:
                    # Find all projections where the link_field matches
                    for local_field_name, (
                        link_field,
                        target_doctype,
                        target_field,
                    ) in links_map.items():
                        if link_field == link_field_name:
                            # Use Frappe's LinkTableField to handle the join and field selection
                            link_table_field = LinkTableField(
                                doctype=target_doctype,
                                fieldname=target_field,
                                parent_doctype=doctype,
                                link_fieldname=link_field,
                                alias=local_field_name,
                            )
                            # Apply the join and select the field
                            query = link_table_field.apply_select(query)

        # Apply filters
        for filter_dict in self.filters:
            for key, value in filter_dict.items():
                parsed = _parse_lookup(key, value)
                condition = self._build_condition(table, parsed)
                query = query.where(condition)

        # Apply order_by
        for field_spec in self.order_by_fields:
            # Handle descending order (prefix with "-")
            if field_spec.startswith("-"):
                field_name = field_spec[1:]
                query = query.orderby(table[field_name], order=Order.desc)
            else:
                query = query.orderby(table[field_name], order=Order.asc)

        # Apply limit
        if self.limit_value is not None:
            query = query.limit(self.limit_value)

        return query

    def _hydrate_from_row(self, row: dict[str, Any]) -> TDoc:
        """Convert a database row dictionary into a DocModel instance.

        Args:
            row: Dictionary from database query result

        Returns:
            A DocModel instance with fields populated from the row

        Note:
            The DocModel's _extract_extras validator will handle separating
            unknown fields into extras, so we can pass the row directly.
        """
        # Pass the row directly to the schema adapter
        # The DocModel's _extract_extras validator will handle
        # separating unknown fields into the extras dictionary
        return self.schema.adapter().validate_python(row)

    def _prefetch_children(self, parent_models: List[TDoc]) -> None:
        """Prefetch child table data for parent models.

        Args:
            parent_models: List of parent DocModel instances to attach children to

        Note:
            This method modifies the parent models in-place by attaching child lists.
        """
        if not parent_models:
            return

        # Get child table mappings from schema Meta
        if not hasattr(self.schema, "Meta") or not hasattr(self.schema.Meta, "children"):
            return

        children_map = self.schema.Meta.children
        if not children_map:
            return

        # Filter prefetch_fields to only those that exist in Meta.children
        prefetch_fields = [f for f in self.prefetch_fields if f in children_map]

        if not prefetch_fields:
            return

        try:
            import frappe
            from pypika import Order
        except ImportError:
            # If Frappe is not available, skip prefetch
            return

        parent_doctype = self.schema.Meta.doctype
        parent_names = [model.name for model in parent_models if hasattr(model, "name")]

        if not parent_names:
            return

        # Prefetch each child table field
        for child_field_name in prefetch_fields:
            child_schema = children_map[child_field_name]
            child_doctype = child_schema.Meta.doctype

            # Build query for child table
            child_table = frappe.qb.DocType(child_doctype)
            child_query = (
                frappe.qb.from_(child_table)
                .select("*")
                .where(
                    (child_table.parent.isin(parent_names))
                    & (child_table.parenttype == parent_doctype)
                    & (child_table.parentfield == child_field_name)
                )
                .orderby(child_table.idx, order=Order.asc)
            )

            # Execute query and get child rows
            child_rows = child_query.run(as_dict=True)

            # Group child rows by parent name
            children_by_parent: Dict[str, List[Any]] = {}
            for child_row in child_rows:
                parent_name = child_row.get("parent")
                if parent_name:
                    if parent_name not in children_by_parent:
                        children_by_parent[parent_name] = []
                    # Hydrate child row into DocModel instance
                    child_model = child_schema.adapter().validate_python(child_row)
                    children_by_parent[parent_name].append(child_model)

            # Attach child lists to parent models
            # Use object.__setattr__ to bypass Pydantic's field validation
            # since child table fields are not declared in the parent schema
            for parent_model in parent_models:
                parent_name = getattr(parent_model, "name", None)
                if parent_name in children_by_parent:
                    # Attach the child list to the parent model
                    object.__setattr__(
                        parent_model, child_field_name, children_by_parent[parent_name]
                    )
                else:
                    # If no children found, set empty list
                    object.__setattr__(parent_model, child_field_name, [])

    def all(self) -> List[TDoc]:
        """Execute the query and return all matching results.

        Returns:
            List of DocModel instances matching the query

        Example:
            results = query.all()
        """
        query = self._build_frappe_query()
        rows = query.run(as_dict=True)

        results: List[TDoc] = []
        for row in rows:
            model = self._hydrate_from_row(row)
            results.append(model)

        # Prefetch child tables if requested
        if self.prefetch_fields:
            self._prefetch_children(results)

        return results

    def first(self) -> TDoc | None:
        """Execute the query and return the first result, or None if no results.

        This automatically sets limit to 1 before calling all().

        Returns:
            First DocModel instance or None if no results

        Example:
            result = query.first()
        """
        self.limit_value = 1
        results = self.all()
        return results[0] if results else None


__all__ = ["ReadQuery", "TDoc"]
