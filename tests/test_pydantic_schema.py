import pytest
from pydantic import BaseModel

from frappe_powertools.listeners import change_listeners, validate_on_change
from frappe_powertools.pydantic import PydanticValidationError, pydantic_schema


class PersonSchema(BaseModel):
	name: str
	age: int


class DummyDocument:
	def __init__(self, **data):
		self._data = data.copy()
		self._validate_calls = 0
		for key, value in data.items():
			setattr(self, key, value)

	def as_dict(self):
		return self._data.copy()

	def validate(self):
		self._validate_calls += 1
		return "validated"


def test_pydantic_runs_before_validate_and_stashes_model():
	@pydantic_schema(PersonSchema)
	class Doc(DummyDocument):
		pass

	doc = Doc(name="Alice", age="21")
	result = doc.validate()

	assert result == "validated"
	assert doc._validate_calls == 1
	assert hasattr(doc, "_pydantic_model")
	assert isinstance(doc._pydantic_model, PersonSchema)
	# Without normalization original value remains
	assert doc.age == "21"


def test_pydantic_normalization():
	@pydantic_schema(PersonSchema, normalize=True)
	class Doc(DummyDocument):
		pass

	doc = Doc(name="Bob", age="30")
	doc.validate()

	assert doc.age == 30
	assert doc._pydantic_model.age == 30


def test_pydantic_validation_after_original_logic():
	events = []

	@pydantic_schema(PersonSchema, order="after")
	class Doc(DummyDocument):
		def validate(self):
			events.append("validate")
			return super().validate()

	doc = Doc(name="Bob", age="41")
	doc.validate()

	assert events == ["validate"]


def test_pydantic_validation_error_raises_custom_exception():
	@pydantic_schema(PersonSchema)
	class Doc(DummyDocument):
		pass

	doc = Doc(name="Alice", age="invalid")

	with pytest.raises(PydanticValidationError) as exc:
		doc.validate()

	assert "age" in str(exc.value)


def test_pydantic_and_change_listeners_chain_together():
	class ListenerDocBase(DummyDocument):
		def __init__(self, **data):
			super().__init__(**data)
			self.listener_calls = 0
			self.sequence = []

		def is_new(self):
			return False

		def get_doc_before_save(self):
			return {}

		def has_value_changed(self, field):
			return True

		def is_child_table_same(self, table):
			return False

		def validate(self):
			self.sequence.append("validate")
			return super().validate()

	@change_listeners
	@pydantic_schema(PersonSchema, normalize=True)
	class Doc(ListenerDocBase):
		@validate_on_change("name")
		def _listener(self):
			self.listener_calls += 1
			self.sequence.append("listener")

	doc = Doc(name="Eve", age="22")
	doc.validate()

	assert doc.age == 22
	assert doc.listener_calls == 1
	assert doc.sequence == ["validate", "listener"]
