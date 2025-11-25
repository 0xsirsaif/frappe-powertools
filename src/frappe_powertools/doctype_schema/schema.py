from __future__ import annotations

from typing import Any, Callable, ClassVar, Dict, Literal, Mapping, Type

from pydantic import BaseModel, ConfigDict, ValidationError, model_validator
from pydantic.type_adapter import TypeAdapter

from .._method_chain import attach_method_wrapper

OrderOption = Literal["before", "after"]
ErrorBehaviour = Literal["throw", "raise"]


class DocModelMeta:
    """Metadata for DocModel subclasses.

    Attributes:
        doctype: The Frappe DocType name this model represents
        children: Mapping of child table field names to their DocModel classes
        links: Mapping of local field names to (link_field, target_doctype, target_field) tuples
            Example: {"program_name": ("program", "Training Program", "program_name")}
    """

    doctype: str
    children: Dict[str, Type["DocModel"]] = {}
    links: Dict[str, tuple[str, str, str]] = {}


class DocModel(BaseModel):
    """Base class for Frappe DocType schemas.

    Intended to be subclassed once per DocType and reused for:
    - Document validation (via `pydantic_schema` decorator)
    - Read-only ORM/query layer
    - Other integrations (e.g., workbook validators)

    Example:
        class TrainingBatch(DocModel):
            class Meta:
                doctype = "Training Batch"
                children = {"participants": TrainingBatchParticipant}

            name: str
            program: str
            start_date: date
            extras: Dict[str, Any] = {}
    """

    model_config = ConfigDict(extra="ignore")

    # Bucket for fields not explicitly declared on the model
    extras: Dict[str, Any] = {}

    # Cached TypeAdapter instance per subclass
    _powertools_adapter: ClassVar[TypeAdapter | None] = None

    @model_validator(mode="before")
    @classmethod
    def _extract_extras(cls, data: Any) -> Any:
        """Extract unknown fields into extras before validation."""
        if not isinstance(data, dict):
            return data

        # Get declared field names (excluding 'extras' itself)
        declared_fields = set(cls.model_fields.keys()) - {"extras"}

        # Separate known and unknown fields
        known_data = {}
        extras_data = {}

        for key, value in data.items():
            if key in declared_fields:
                known_data[key] = value
            else:
                extras_data[key] = value

        # If there are extras, include them in the data
        if extras_data:
            known_data["extras"] = extras_data

        return known_data

    @classmethod
    def adapter(cls) -> TypeAdapter:
        """Get or create a cached TypeAdapter for this DocModel class."""
        if cls._powertools_adapter is None:
            cls._powertools_adapter = TypeAdapter(cls)
        return cls._powertools_adapter

    @classmethod
    def register(cls) -> Type["DocModel"]:
        """Register this model in the global registry keyed by Meta.doctype.

        Returns:
            The class itself for chaining
        """
        if not hasattr(cls, "Meta") or not hasattr(cls.Meta, "doctype"):
            raise ValueError(f"{cls.__name__} must define a Meta class with a 'doctype' attribute")
        _registry.register(cls.Meta.doctype, cls)
        return cls


class _ModelRegistry:
    """Simple registry for DocType name -> DocModel class mapping."""

    def __init__(self):
        self._models: Dict[str, Type[DocModel]] = {}

    def register(self, doctype: str, model: Type[DocModel]) -> None:
        """Register a DocModel for a DocType."""
        if doctype in self._models and self._models[doctype] is not model:
            raise ValueError(
                f"DocType '{doctype}' is already registered with model "
                f"'{self._models[doctype].__name__}'. Cannot register '{model.__name__}'."
            )
        self._models[doctype] = model

    def get(self, doctype: str) -> Type[DocModel] | None:
        """Get the DocModel class for a DocType, or None if not registered."""
        return self._models.get(doctype)

    def clear(self) -> None:
        """Clear all registered models (mainly for testing)."""
        self._models.clear()


_registry = _ModelRegistry()


class PydanticValidationError(Exception):
    """Raised when Pydantic validation fails and Frappe throwing is disabled."""

    def __init__(self, message: str, errors: list[Mapping[str, Any]]):
        super().__init__(message)
        self.errors = errors


def use_schema(
    schema: Type[DocModel],
    *,
    normalize: bool = True,
    stash_attr: str | None = "_schema_model",
    on_error: ErrorBehaviour = "throw",
    order: OrderOption = "before",
) -> Callable[[type], type]:
    """Decorator to attach a DocModel-based validation pipeline to a Frappe Document class.

    This is a convenience wrapper around `pydantic_schema` that is specialized for
    `DocModel` subclasses. It provides sensible defaults for DocType validation.

    Args:
        schema: A DocModel subclass to use for validation
        normalize: Whether to normalize document fields from validated model (default: True)
        stash_attr: Attribute name to store the validated model on the document (default: "_schema_model")
        on_error: How to handle validation errors - "throw" (Frappe) or "raise" (exception)
        order: When to run validation - "before" or "after" the original validate method

    Example:
        @use_schema(TrainingBatchSchema)
        class TrainingBatch(Document):
            pass
    """
    return pydantic_schema(
        schema,
        normalize=normalize,
        stash_attr=stash_attr,
        on_error=on_error,
        order=order,
    )


def pydantic_schema(
    schema: type[BaseModel] | TypeAdapter[Any],
    *,
    normalize: bool = False,
    stash_attr: str | None = "_pydantic_model",
    order: OrderOption = "before",
    on_error: ErrorBehaviour = "throw",
    error_title: str | None = None,
) -> Callable[[type], type]:
    """Class decorator: validate DocType data with a Pydantic schema."""

    if order not in {"before", "after"}:
        raise ValueError("order must be 'before' or 'after'")

    config = {
        "schema": schema,
        "normalize": normalize,
        "stash_attr": stash_attr,
        "order": order,
        "on_error": on_error,
        "error_title": error_title,
    }

    def decorator(cls: type) -> type:
        # Add the config to the class
        configs = getattr(cls, "_powertools_pydantic_schemas", [])
        configs.append(config)
        setattr(cls, "_powertools_pydantic_schemas", configs)

        # Attach the wrapper to the validate method
        attach_method_wrapper(
            cls, "validate", f"powertools:pydantic:{id(config)}", _build_wrapper(config)
        )

        return cls

    return decorator


def _build_wrapper(config: Mapping[str, Any]) -> Callable:
    def wrapper(self, next_method, args, kwargs):
        if config["order"] == "before":
            model = _run_validation(self, config)
            result = next_method(self, *args, **kwargs)
        else:
            result = next_method(self, *args, **kwargs)
            model = _run_validation(self, config)

        if config["stash_attr"]:
            setattr(self, config["stash_attr"], model)

        return result

    return wrapper


def _run_validation(doc, config: Mapping[str, Any]):
    adapter = _ensure_adapter(config["schema"])
    data = _extract_data(doc)

    try:
        model = adapter.validate_python(data)
    except ValidationError as err:
        _handle_validation_error(err, config)

    if config["normalize"]:
        _apply_normalized(doc, model)

    return model


def _ensure_adapter(schema: type[BaseModel] | TypeAdapter[Any] | object) -> TypeAdapter[Any]:
    """Get a TypeAdapter for the schema, using DocModel.adapter() if available."""
    if isinstance(schema, TypeAdapter):
        return schema

    # If it's a DocModel subclass, use its cached adapter
    if isinstance(schema, type) and issubclass(schema, DocModel):
        return schema.adapter()

    # Fallback to creating a new TypeAdapter for other BaseModel subclasses
    if isinstance(schema, type) and issubclass(schema, BaseModel):
        return TypeAdapter(schema)

    return TypeAdapter(schema)


def _extract_data(doc) -> Mapping[str, Any]:
    if hasattr(doc, "as_dict"):
        return doc.as_dict()

    if hasattr(doc, "get_valid_dict"):
        return doc.get_valid_dict()

    return {k: v for k, v in doc.__dict__.items() if not k.startswith("_")}


def _apply_normalized(doc, model):
    if isinstance(model, BaseModel):
        data = model.model_dump(mode="python")
    else:
        return

    for field, value in data.items():
        try:
            setattr(doc, field, value)
        except AttributeError:
            pass


def _handle_validation_error(err: ValidationError, config: Mapping[str, Any]) -> None:
    lines = []
    for error in err.errors():
        location = ".".join(str(part) for part in error.get("loc", ()))
        if location:
            lines.append(f"• {location}: {error.get('msg')}")
        else:
            lines.append(f"• {error.get('msg')}")

    message = "\n".join(lines) if lines else str(err)
    title = config.get("error_title") or "Validation Error"

    if config["on_error"] == "raise":
        raise PydanticValidationError(message, err.errors())

    try:
        import frappe  # type: ignore[import-not-found]
    except ImportError:
        raise PydanticValidationError(message, err.errors())

    throw = getattr(frappe, "throw", None)

    if throw is None:
        raise PydanticValidationError(message, err.errors())

    throw(message, title=title)
