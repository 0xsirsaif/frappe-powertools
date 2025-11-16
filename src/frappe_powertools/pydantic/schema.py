from __future__ import annotations

from typing import Any, Callable, Literal, Mapping

from pydantic import BaseModel, ValidationError
from pydantic.type_adapter import TypeAdapter

from .._method_chain import attach_method_wrapper

OrderOption = Literal["before", "after"]
ErrorBehaviour = Literal["throw", "raise"]


class PydanticValidationError(Exception):
	"""Raised when Pydantic validation fails and Frappe throwing is disabled."""

	def __init__(self, message: str, errors: list[Mapping[str, Any]]):
		super().__init__(message)
		self.errors = errors


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
		attach_method_wrapper(cls, "validate", f"powertools:pydantic:{id(config)}", _build_wrapper(config))

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
	if isinstance(schema, TypeAdapter):
		return schema

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
		import frappe
	except ImportError:
		raise PydanticValidationError(message, err.errors())

	frappe.throw(message, title=title)
