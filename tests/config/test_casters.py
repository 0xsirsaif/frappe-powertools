"""Tests for _casters.py — Csv, Choices, _cast_bool."""

import pytest

from frappe_powertools.config._casters import Choices, Csv, _cast_bool


class TestCastBool:
    @pytest.mark.parametrize("value", ["1", "true", "True", "TRUE", "yes", "on", "t", "y", "Y"])
    def test_truthy_strings(self, value):
        assert _cast_bool(value) is True

    @pytest.mark.parametrize("value", ["0", "false", "False", "FALSE", "no", "off", "f", "n", ""])
    def test_falsy_strings(self, value):
        assert _cast_bool(value) is False

    @pytest.mark.parametrize("value", [True, 1, 1.0])
    def test_non_string_truthy(self, value):
        assert _cast_bool(value) is True

    @pytest.mark.parametrize("value", [False, 0])
    def test_non_string_falsy(self, value):
        assert _cast_bool(value) is False

    def test_invalid_string_raises(self):
        with pytest.raises(ValueError, match="Cannot cast"):
            _cast_bool("maybe")

    def test_invalid_type_raises(self):
        with pytest.raises(ValueError, match="Cannot cast"):
            _cast_bool([1, 2])

    def test_whitespace_stripped(self):
        assert _cast_bool("  true  ") is True


class TestCsv:
    def test_basic_split(self):
        assert Csv()("a,b,c") == ["a", "b", "c"]

    def test_cast_int(self):
        assert Csv(cast=int)("1,2,3") == [1, 2, 3]

    def test_custom_delimiter(self):
        assert Csv(delimiter=";")("a;b;c") == ["a", "b", "c"]

    def test_strip_whitespace(self):
        assert Csv()("a , b , c") == ["a", "b", "c"]

    def test_no_strip(self):
        assert Csv(strip=False)("a , b") == ["a ", " b"]

    def test_skips_empty_strings(self):
        assert Csv()("a,,b,") == ["a", "b"]

    def test_passthrough_list(self):
        original = [1, 2, 3]
        assert Csv()(original) is original

    def test_passthrough_tuple(self):
        original = (1, 2, 3)
        assert Csv()(original) is original

    def test_post_process_tuple(self):
        result = Csv(post_process=tuple)("a,b,c")
        assert result == ("a", "b", "c")
        assert isinstance(result, tuple)


class TestChoices:
    def test_valid_choice(self):
        assert Choices(["debug", "info", "warning"])("info") == "info"

    def test_invalid_choice_raises(self):
        with pytest.raises(ValueError, match="not a valid choice"):
            Choices(["debug", "info"])("critical")

    def test_with_cast(self):
        assert Choices([1, 2, 3], cast=int)("2") == 2

    def test_invalid_after_cast(self):
        with pytest.raises(ValueError, match="not a valid choice"):
            Choices([1, 2, 3], cast=int)("5")
