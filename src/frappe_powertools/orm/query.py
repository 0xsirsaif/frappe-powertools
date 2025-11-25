from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Generic, List, Literal, Type, TypeVar, get_origin

from ..doctype_schema import DocModel

TDoc = TypeVar("TDoc", bound=DocModel)


class Q:
    """Query object for building complex boolean logic expressions.

    Q objects can be combined using & (AND), | (OR), and ~ (NOT) operators
    to create nested boolean logic trees.

    Examples:
        # Simple leaf node
        q = Q(status="Active")

        # AND combination
        q = Q(status="Active") & Q(owner="saif")

        # OR combination
        q = Q(status="Active") | Q(status="Pending")

        # Negation
        q = ~Q(status="Cancelled")

        # Nested combinations
        q = (Q(status="Active") | Q(status="Pending")) & Q(is_online=True)
    """

    def __init__(self, **kwargs: Any):
        """Create a Q object.

        Args:
            **kwargs: Field name to value mappings for filtering.
                     If provided, creates a leaf node with these conditions.
                     If empty, creates an empty Q object.
        """
        # children can be either dict[str, Any] (leaf) or Q instances (subtrees)
        self.children: list[Q | dict[str, Any]] = []
        if kwargs:
            self.children.append(kwargs)
        self.connector: Literal["AND", "OR"] = "AND"
        self.negated: bool = False

    def _combine(self, other: Q, connector: Literal["AND", "OR"]) -> Q:
        """Combine this Q with another Q using the specified connector.

        Args:
            other: Another Q object to combine with
            connector: Either "AND" or "OR"

        Returns:
            A new Q object with both Qs as children
        """
        q = Q()
        q.children = [self, other]
        q.connector = connector
        q.negated = False
        return q

    def __and__(self, other: Q) -> Q:
        """Combine two Q objects with AND logic.

        Args:
            other: Another Q object

        Returns:
            A new Q object with AND connector
        """
        return self._combine(other, "AND")

    def __or__(self, other: Q) -> Q:
        """Combine two Q objects with OR logic.

        Args:
            other: Another Q object

        Returns:
            A new Q object with OR connector
        """
        return self._combine(other, "OR")

    def __invert__(self) -> Q:
        """Negate this Q object.

        Returns:
            A new Q object with negated flag flipped
        """
        q = Q()
        q.children = [self]
        q.connector = "AND"
        q.negated = not self.negated
        return q

    def __repr__(self) -> str:
        """Return a string representation of the Q object."""
        connector_str = self.connector
        if self.negated:
            connector_str = f"NOT {connector_str}"
        children_str = ", ".join(
            repr(child) if isinstance(child, Q) else str(child) for child in self.children
        )
        return f"Q({connector_str}: [{children_str}])"


@dataclass
class ParsedLookup:
    """Parsed lookup from filter key.

    Attributes:
        field_name: The field name (without lookup suffix)
        lookup: The lookup type ("exact", "gt", "gte", "lt", "lte", "range", "in", "not_in", "isnull", "blank", "contains", "startswith", "endswith")
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
    exclude_filters: List[dict[str, Any]] = field(default_factory=list)
    filter_qs: List[Q] = field(default_factory=list)
    exclude_qs: List[Q] = field(default_factory=list)
    order_by_fields: List[str] = field(default_factory=list)
    limit_value: int | None = None
    prefetch_fields: List[str] = field(default_factory=list)
    select_related_fields: List[str] = field(default_factory=list)

    def filter(self, *conditions: Q, **kwargs: Any) -> ReadQuery[TDoc]:
        """Add filter conditions to the query.

        Multiple calls to filter() are combined with AND logic.
        Can accept Q objects as positional arguments and/or kwargs.

        Args:
            *conditions: Q objects to combine with AND logic
            **kwargs: Field name to value mappings for filtering

        Returns:
            Self for method chaining

        Example:
            query.filter(status="Active").filter(program="PROG-001")
            query.filter(Q(status="Active") | Q(status="Pending"), is_online=True)
        """
        # Store Q objects
        for condition in conditions:
            if not isinstance(condition, Q):
                raise TypeError(
                    f"filter() positional arguments must be Q objects, got {type(condition)}"
                )
            self.filter_qs.append(condition)

        # Store kwargs (backwards compatible)
        if kwargs:
            self.filters.append(kwargs)
        return self

    def exclude(self, *conditions: Q, **kwargs: Any) -> ReadQuery[TDoc]:
        """Exclude records matching the given conditions.

        Multiple calls to exclude() are combined with AND logic.
        Each exclude condition is negated (NOT condition).
        Can accept Q objects as positional arguments and/or kwargs.

        Args:
            *conditions: Q objects to combine with AND logic (will be negated)
            **kwargs: Field name to value mappings for exclusion

        Returns:
            Self for method chaining

        Example:
            query.filter(status="Active").exclude(owner="guest")
            query.exclude(status__in=["Cancelled", "Archived"])
            query.exclude(Q(status="Cancelled") | Q(status="Archived"))
        """
        # Store Q objects
        for condition in conditions:
            if not isinstance(condition, Q):
                raise TypeError(
                    f"exclude() positional arguments must be Q objects, got {type(condition)}"
                )
            self.exclude_qs.append(condition)

        # Store kwargs (backwards compatible)
        if kwargs:
            self.exclude_filters.append(kwargs)
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

    def _q_to_criterion(self, table, q: Q):
        """Convert a Q tree into a single criterion expression.

        - Leaves (dict[str, Any]) are converted via _parse_lookup + _build_condition.
        - Sub-Qs are recursively converted and combined using & / |.
        - Negation is applied via ~.
        - Double negation is optimized: ~(~Q) simplifies to Q.

        Args:
            table: PyPika table object
            q: Q object to convert

        Returns:
            PyPika condition expression

        Raises:
            ValueError: If Q object has no children
        """
        if not q.children:
            raise ValueError("Cannot convert empty Q object to criterion")

        # Optimize double negation: handle the specific ~(~Q(...)) pattern.
        # In this case both the parent and the single child are negated, so
        # the negations cancel out and we can unwrap to the inner Q.
        if len(q.children) == 1 and isinstance(q.children[0], Q):
            child_q = q.children[0]
            if q.negated and child_q.negated:
                unwrapped_q = Q()
                unwrapped_q.children = child_q.children
                unwrapped_q.connector = child_q.connector
                unwrapped_q.negated = False
                return self._q_to_criterion(table, unwrapped_q)

        child_conditions = []

        for child in q.children:
            if isinstance(child, dict):
                # Leaf node: parse each key/value and build conditions
                for key, value in child.items():
                    parsed = _parse_lookup(key, value)
                    condition = self._build_condition(table, parsed)
                    child_conditions.append(condition)
            elif isinstance(child, Q):
                # Sub-tree: recursively convert
                condition = self._q_to_criterion(table, child)
                child_conditions.append(condition)
            else:
                raise TypeError(f"Unexpected child type in Q: {type(child)}")

        # Combine child conditions with the connector
        if not child_conditions:
            raise ValueError("Q object has no valid conditions")

        # Start with the first condition
        combined = child_conditions[0]

        # Combine remaining conditions
        for condition in child_conditions[1:]:
            if q.connector == "AND":
                combined = combined & condition
            elif q.connector == "OR":
                combined = combined | condition
            else:
                raise ValueError(f"Unknown connector: {q.connector}")

        # Apply negation if needed
        if q.negated:
            combined = ~combined

        return combined

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

        # Convert Python boolean to int for Check fields (Frappe stores as 0/1)
        # Check if the field is typed as bool in the schema
        if parsed.field_name in self.schema.model_fields:
            field_info = self.schema.model_fields[parsed.field_name]
            annotation = field_info.annotation
            # Check if the field type is bool (Check field in Frappe)
            # Handle both direct bool and Optional[bool] (bool | None) types
            origin = get_origin(annotation)
            is_bool_field = (
                annotation is bool or (origin is None and annotation is bool) or origin is bool
            )
            if is_bool_field and isinstance(value, bool):
                # Convert True/False to 1/0 for exact lookups
                if lookup == "exact":
                    value = 1 if value else 0

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
        elif lookup == "contains":
            if not isinstance(value, str):
                raise ValueError(
                    f"contains lookup requires a string value, got {type(value).__name__}"
                )
            return field.like(f"%{value}%")
        elif lookup == "startswith":
            if not isinstance(value, str):
                raise ValueError(
                    f"startswith lookup requires a string value, got {type(value).__name__}"
                )
            return field.like(f"{value}%")
        elif lookup == "endswith":
            if not isinstance(value, str):
                raise ValueError(
                    f"endswith lookup requires a string value, got {type(value).__name__}"
                )
            return field.like(f"%{value}")
        else:
            raise ValueError(
                f"Unsupported lookup '{lookup}' on field '{parsed.field_name}'. "
                f"Supported lookups: exact, gt, gte, lt, lte, range, in, not_in, isnull, blank, contains, startswith, endswith"
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

        # Apply Q-based filters
        if self.filter_qs:
            # Combine all filter Qs with AND
            if len(self.filter_qs) == 1:
                combined_q = self.filter_qs[0]
            else:
                # Combine multiple Qs with AND
                combined_q = self.filter_qs[0]
                for q in self.filter_qs[1:]:
                    combined_q = combined_q & q
            criterion = self._q_to_criterion(table, combined_q)
            query = query.where(criterion)

        # Apply legacy dict-based filters
        for filter_dict in self.filters:
            for key, value in filter_dict.items():
                parsed = _parse_lookup(key, value)
                condition = self._build_condition(table, parsed)
                query = query.where(condition)

        # Apply Q-based exclude filters
        if self.exclude_qs:
            # Combine all exclude Qs with AND
            if len(self.exclude_qs) == 1:
                combined_q = self.exclude_qs[0]
            else:
                # Combine multiple Qs with AND
                combined_q = self.exclude_qs[0]
                for q in self.exclude_qs[1:]:
                    combined_q = combined_q & q
            criterion = self._q_to_criterion(table, combined_q)
            # Negate the criterion
            query = query.where(~criterion)

        # Apply legacy dict-based exclude filters (negated conditions)
        for exclude_dict in self.exclude_filters:
            for key, value in exclude_dict.items():
                parsed = _parse_lookup(key, value)
                condition = self._build_condition(table, parsed)
                # Negate the condition
                query = query.where(~condition)

        # Apply order_by
        for field_spec in self.order_by_fields:
            # Handle descending order (prefix with "-")
            # Extract field_name before the if/else to avoid UnboundLocalError
            if field_spec.startswith("-"):
                field_name = field_spec[1:]
                query = query.orderby(table[field_name], order=Order.desc)
            else:
                field_name = field_spec
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

    def count(self) -> int:
        """Execute the query and return the count of matching records.

        This is more efficient than len(query.all()) as it only counts records
        without fetching them into memory.

        Returns:
            Integer count of matching records

        Example:
            count = query.filter(status="Active").count()
        """
        try:
            import frappe
            from frappe.query_builder.functions import Count
        except ImportError:
            raise ImportError(
                "Frappe is required for query execution. "
                "Install frappe or run in a Frappe environment."
            )

        doctype = self.schema.Meta.doctype
        table = frappe.qb.DocType(doctype)

        # Build count query with same filters/excludes as the main query
        count_query = frappe.qb.from_(table).select(Count("*").as_("count"))

        # Apply Q-based filters
        if self.filter_qs:
            # Combine all filter Qs with AND
            if len(self.filter_qs) == 1:
                combined_q = self.filter_qs[0]
            else:
                # Combine multiple Qs with AND
                combined_q = self.filter_qs[0]
                for q in self.filter_qs[1:]:
                    combined_q = combined_q & q
            criterion = self._q_to_criterion(table, combined_q)
            count_query = count_query.where(criterion)

        # Apply legacy dict-based filters
        for filter_dict in self.filters:
            for key, value in filter_dict.items():
                parsed = _parse_lookup(key, value)
                condition = self._build_condition(table, parsed)
                count_query = count_query.where(condition)

        # Apply Q-based exclude filters
        if self.exclude_qs:
            # Combine all exclude Qs with AND
            if len(self.exclude_qs) == 1:
                combined_q = self.exclude_qs[0]
            else:
                # Combine multiple Qs with AND
                combined_q = self.exclude_qs[0]
                for q in self.exclude_qs[1:]:
                    combined_q = combined_q & q
            criterion = self._q_to_criterion(table, combined_q)
            # Negate the criterion
            count_query = count_query.where(~criterion)

        # Apply legacy dict-based exclude filters (negated conditions)
        for exclude_dict in self.exclude_filters:
            for key, value in exclude_dict.items():
                parsed = _parse_lookup(key, value)
                condition = self._build_condition(table, parsed)
                count_query = count_query.where(~condition)

        result = count_query.run(as_dict=True)
        return result[0]["count"] if result else 0


__all__ = ["ReadQuery", "TDoc"]
