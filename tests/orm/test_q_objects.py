"""Tests for Q objects and OR/nested logic support."""

from __future__ import annotations

import pytest

from frappe_powertools.doctype_schema import DocModel
from frappe_powertools.orm import Q, ReadQuery


class TestQCoreDataStructure:
    """Phase 6.B: Tests for Q object core data structure (pure Python, no DB)."""

    def test_q_leaf_creation(self):
        """Test that Q(**kwargs) creates a leaf node."""
        q = Q(status="Active")
        assert q.children == [{"status": "Active"}]
        assert q.connector == "AND"
        assert q.negated is False

    def test_q_and_creates_new_parent(self):
        """Test that & combines two Q objects with AND at a new parent node."""
        q1 = Q(status="Active")
        q2 = Q(owner="saif")
        q3 = q1 & q2

        assert q3 is not q1 and q3 is not q2
        assert q3.connector == "AND"
        assert q3.children == [q1, q2]
        assert q3.negated is False

        # Original Qs unchanged
        assert q1.connector == "AND" and q1.negated is False

    def test_q_or_creates_new_parent(self):
        """Test that | combines two Q objects with OR at a new parent node."""
        q = Q(status="Active") | Q(status="Pending")
        assert q.connector == "OR"
        assert len(q.children) == 2

    def test_q_invert_flips_negated_flag(self):
        """Test that ~Q negates the Q object."""
        q = ~Q(status="Active")
        assert q.negated is True
        assert len(q.children) == 1

    def test_q_combining_already_combined_nests_them(self):
        """Test that combining already-combined Qs nests them rather than mutating in place."""
        q1 = Q(status="Active") | Q(status="Pending")
        q2 = Q(owner="saif") | Q(owner="admin")
        q3 = q1 & q2

        # q3 should be a new Q with AND connector
        assert q3.connector == "AND"
        assert q3.children == [q1, q2]
        assert q3.negated is False

        # Original Qs unchanged
        assert q1.connector == "OR"
        assert q2.connector == "OR"

    def test_q_empty_creation(self):
        """Test that Q() with no kwargs creates an empty Q object."""
        q = Q()
        assert q.children == []
        assert q.connector == "AND"
        assert q.negated is False

    def test_q_multiple_kwargs_in_single_creation(self):
        """Test that Q(**kwargs) with multiple kwargs stores them in a single dict."""
        q = Q(status="Active", owner="saif")
        assert q.children == [{"status": "Active", "owner": "saif"}]
        assert q.connector == "AND"
        assert q.negated is False

    def test_q_double_negation(self):
        """Test that double negation (~(~Q)) returns to original state."""
        q1 = Q(status="Active")
        q2 = ~q1
        q3 = ~q2

        # q3 should have negated=False (double negation cancels)
        assert q3.negated is False
        assert len(q3.children) == 1

    def test_q_immutability_on_combination(self):
        """Test that combining Q objects doesn't mutate the original objects."""
        q1 = Q(status="Active")
        q2 = Q(owner="saif")
        original_q1_children = q1.children.copy()
        original_q2_children = q2.children.copy()

        q1 & q2

        # Original Qs should be unchanged
        assert q1.children == original_q1_children
        assert q2.children == original_q2_children
        assert q1.connector == "AND"
        assert q2.connector == "AND"


class DummyCondition:
    """Dummy condition class for testing _q_to_criterion without PyPika."""

    def __init__(self, label: str):
        self.label = label

    def __and__(self, other: "DummyCondition") -> "DummyCondition":
        return DummyCondition(f"({self.label} AND {other.label})")

    def __or__(self, other: "DummyCondition") -> "DummyCondition":
        return DummyCondition(f"({self.label} OR {other.label})")

    def __invert__(self) -> "DummyCondition":
        return DummyCondition(f"(NOT {self.label})")

    def __repr__(self) -> str:
        return f"DummyCondition({self.label!r})"


class DummyDocModel(DocModel):
    """Dummy DocModel for testing."""

    class Meta:
        doctype = "Dummy"

    status: str | None = None
    owner: str | None = None
    is_online: bool | None = None


class TestQToCriterion:
    """Phase 6.C: Tests for converting Q trees into PyPika criteria."""

    def test_q_leaf_to_criterion(self, monkeypatch):
        """Test that a leaf Q with single dict converts to criterion."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        q = Q(status="Active")
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert criterion.label == "status exact Active"

    def test_q_and_or_to_criterion(self, monkeypatch):
        """Test that AND/OR combinations convert correctly."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        q = Q(status="Active") | Q(status="Pending")
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert criterion.label == "(status exact Active OR status exact Pending)"

    def test_q_negation_to_criterion(self, monkeypatch):
        """Test that negation converts correctly."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        q = ~Q(status="Active")
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert criterion.label == "(NOT status exact Active)"

    def test_q_nested_and_with_kwargs(self, monkeypatch):
        """Test nested Q with kwargs and sub-Qs converts correctly."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        # q: (status='Active' OR status='Pending') AND is_online=True
        q = (Q(status="Active") | Q(status="Pending")) & Q(is_online=True)
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert (
            criterion.label
            == "((status exact Active OR status exact Pending) AND is_online exact True)"
        )

    def test_q_and_combination_to_criterion(self, monkeypatch):
        """Test that AND combination converts correctly."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        q = Q(status="Active") & Q(owner="saif")
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert criterion.label == "(status exact Active AND owner exact saif)"

    def test_q_multiple_kwargs_in_leaf_to_criterion(self, monkeypatch):
        """Test that Q with multiple kwargs in single dict converts correctly."""
        table = object()

        call_count = {"count": 0}
        conditions = []

        def fake_build_condition(self, table_arg, parsed):
            call_count["count"] += 1
            condition = DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")
            conditions.append(condition)
            return condition

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        q = Q(status="Active", owner="saif")
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        # Multiple kwargs should result in multiple conditions ANDed together
        assert call_count["count"] == 2
        assert "status exact Active" in criterion.label
        assert "owner exact saif" in criterion.label
        assert "AND" in criterion.label

    def test_q_empty_raises_error(self, monkeypatch):
        """Test that Q() with no children raises ValueError."""
        table = object()
        rq = ReadQuery(DummyDocModel)

        with pytest.raises(ValueError, match="Cannot convert empty Q object to criterion"):
            rq._q_to_criterion(table, Q())

    def test_q_complex_nested_negation(self, monkeypatch):
        """Test complex nested Q with negation converts correctly."""
        table = object()

        def fake_build_condition(self, table_arg, parsed):
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)

        # ~((status='Active' OR status='Pending') AND owner='saif')
        q = ~((Q(status="Active") | Q(status="Pending")) & Q(owner="saif"))
        rq = ReadQuery(DummyDocModel)
        criterion = rq._q_to_criterion(table, q)
        assert (
            criterion.label
            == "(NOT ((status exact Active OR status exact Pending) AND owner exact saif))"
        )


class DummyQuery:
    """Dummy query builder for testing without Frappe."""

    def __init__(self):
        self.where_calls = []

    def where(self, condition):
        """Record where() calls."""
        self.where_calls.append(condition)
        return self

    def select(self, *args):
        return self

    def from_(self, *args):
        return self

    def run(self, **kwargs):
        return []


class FakeFrappe:
    """Fake Frappe module for testing."""

    def __init__(self, query):
        self._query = query
        self.qb = self._FakeQB(query)

    class _FakeQB:
        def __init__(self, query):
            self._query = query

        def DocType(self, doctype):
            return object()

        def from_(self, table):
            return self._query


class TestQIntegration:
    """Phase 6.D: Tests for integrating Q objects with filter() and exclude()."""

    def test_filter_accepts_q_and_kwargs(self, monkeypatch):
        """Test that filter(Q(...), **kwargs) combines Q and kwargs correctly."""
        called = {"q": None, "kwargs_applied": False, "build_query_called": False}

        def fake_q_to_criterion(self, table, q):
            called["q"] = q
            return DummyCondition("q-condition")

        def fake_build_condition(self, table, parsed):
            called["kwargs_applied"] = True
            return DummyCondition(f"{parsed.field_name} {parsed.lookup} {parsed.value}")

        def fake_build_frappe_query(self):
            called["build_query_called"] = True
            # Verify Q objects are stored
            assert len(self.filter_qs) == 1
            assert self.filter_qs[0].connector == "OR"
            # Verify kwargs are stored
            assert len(self.filters) == 1
            assert "is_online" in self.filters[0]
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_q_to_criterion", fake_q_to_criterion, raising=True)
        monkeypatch.setattr(ReadQuery, "_build_condition", fake_build_condition, raising=True)
        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        rq = ReadQuery(DummyDocModel).filter(
            Q(status="Active") | Q(status="Pending"), is_online=True
        )
        rq.all()

        # Assert _build_frappe_query was called
        assert called["build_query_called"] is True

        # Assert Q object was stored correctly
        assert len(rq.filter_qs) == 1
        assert rq.filter_qs[0].connector == "OR"

        # Assert kwargs were stored
        assert len(rq.filters) == 1
        assert rq.filters[0]["is_online"] is True

    def test_filter_accepts_multiple_q_objects(self, monkeypatch):
        """Test that filter() can accept multiple Q objects."""

        def fake_build_frappe_query(self):
            # Verify both Q objects are stored
            assert len(self.filter_qs) == 2
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        q1 = Q(status="Active")
        q2 = Q(owner="saif")
        rq = ReadQuery(DummyDocModel).filter(q1, q2)
        rq.all()

        # Both Q objects should be stored
        assert len(rq.filter_qs) == 2
        assert rq.filter_qs[0] is q1
        assert rq.filter_qs[1] is q2

    def test_exclude_accepts_q(self, monkeypatch):
        """Test that exclude(Q(...)) stores Q objects correctly."""

        def fake_count(self):
            # Verify Q object is stored in exclude_qs
            assert len(self.exclude_qs) == 1
            assert self.exclude_qs[0].connector == "OR"
            return 0

        monkeypatch.setattr(ReadQuery, "count", fake_count, raising=True)

        rq = ReadQuery(DummyDocModel).exclude(Q(status="Cancelled") | Q(status="Archived"))
        rq.count()

        # Assert Q object was stored
        assert len(rq.exclude_qs) == 1
        assert rq.exclude_qs[0].connector == "OR"

    def test_exclude_accepts_q_and_kwargs(self, monkeypatch):
        """Test that exclude(Q(...), **kwargs) combines Q and kwargs correctly."""

        def fake_build_frappe_query(self):
            # Verify Q object is stored
            assert len(self.exclude_qs) == 1
            # Verify kwargs are stored
            assert len(self.exclude_filters) == 1
            assert "owner" in self.exclude_filters[0]
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        rq = ReadQuery(DummyDocModel).exclude(Q(status="Cancelled"), owner="guest")
        rq.all()

        # Assert both Q and kwargs were stored
        assert len(rq.exclude_qs) == 1
        assert len(rq.exclude_filters) == 1
        assert rq.exclude_filters[0]["owner"] == "guest"

    def test_filter_q_with_legacy_kwargs_backwards_compatible(self, monkeypatch):
        """Test that filter() with Q and kwargs maintains backwards compatibility."""

        def fake_build_frappe_query(self):
            # Legacy kwargs-only usage should still work
            assert len(self.filters) == 1
            assert "status" in self.filters[0]
            assert "owner" in self.filters[0]
            # No Q objects should be stored
            assert len(self.filter_qs) == 0
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        # Legacy kwargs-only usage should still work
        rq = ReadQuery(DummyDocModel).filter(status="Active", owner="saif")
        rq.all()

        # Should have stored the kwargs
        assert len(rq.filters) == 1
        assert rq.filters[0]["status"] == "Active"
        assert rq.filters[0]["owner"] == "saif"

    def test_filter_and_exclude_with_q_objects(self, monkeypatch):
        """Test that filter() and exclude() can both use Q objects together."""

        def fake_build_frappe_query(self):
            # Verify both filter and exclude Qs are stored
            assert len(self.filter_qs) == 1
            assert len(self.exclude_qs) == 1
            assert self.filter_qs[0].connector == "OR"
            assert self.exclude_qs[0].connector == "OR"
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        rq = (
            ReadQuery(DummyDocModel)
            .filter(Q(status="Active") | Q(status="Pending"))
            .exclude(Q(owner="guest") | Q(owner="anonymous"))
        )
        rq.all()

        # Both filter and exclude Qs should be stored
        assert len(rq.filter_qs) == 1
        assert len(rq.exclude_qs) == 1


class SupplierGroupAccount(DocModel):
    """DocModel for testing real-world OR scenario."""

    class Meta:
        doctype = "Supplier Group Account"

    name: str
    base_condition: str | None = None
    account: str | None = None
    advance_account: str | None = None


class TestQHighLevelIntegration:
    """Phase 6.E: High-level integration scenario - real-world OR case."""

    def test_real_world_or_scenario_with_base_condition(self, monkeypatch):
        """Test real-world scenario: base condition AND (account OR advance_account).

        This reproduces Frappe's filters + or_filters pattern using Q objects.
        """

        def fake_build_frappe_query(self):
            # Verify Q object is stored (OR condition)
            assert len(self.filter_qs) == 1
            assert self.filter_qs[0].connector == "OR"
            # Verify kwargs are stored (base condition)
            assert len(self.filters) == 1
            assert "base_condition" in self.filters[0]
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        # Real-world query: base_condition AND (account=acct OR advance_account=acct)
        acct = "ACC-001"
        base_value = "BASE-VALUE"

        rq = ReadQuery(SupplierGroupAccount).filter(
            Q(account=acct) | Q(advance_account=acct),
            base_condition=base_value,
        )
        rq.all()

        # Verify both Q and kwargs are stored
        assert len(rq.filter_qs) == 1
        assert rq.filter_qs[0].connector == "OR"
        assert len(rq.filters) == 1
        assert rq.filters[0]["base_condition"] == base_value

    def test_real_world_or_scenario_equivalent_to_frappe_or_filters(self, monkeypatch):
        """Test that Q-based OR query is equivalent to Frappe's filters + or_filters.

        Frappe pattern:
            filters = {"base_condition": value}
            or_filters = [{"account": acct}, {"advance_account": acct}]

        Our ORM pattern:
            filter(Q(account=acct) | Q(advance_account=acct), base_condition=value)
        """

        def fake_build_frappe_query(self):
            # Verify the Q structure: should be OR with two children
            assert len(self.filter_qs) == 1
            q = self.filter_qs[0]
            assert q.connector == "OR"
            assert len(q.children) == 2
            # Verify base condition is in kwargs
            assert len(self.filters) == 1
            assert self.filters[0]["base_condition"] == "BASE-VALUE"
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        acct = "ACC-001"
        base_value = "BASE-VALUE"

        rq = ReadQuery(SupplierGroupAccount).filter(
            Q(account=acct) | Q(advance_account=acct),
            base_condition=base_value,
        )
        rq.all()

        # Verify Q structure
        assert len(rq.filter_qs) == 1
        assert rq.filter_qs[0].connector == "OR"
        assert len(rq.filter_qs[0].children) == 2
        # Verify base condition
        assert rq.filters[0]["base_condition"] == base_value

    def test_complex_nested_q_with_multiple_base_conditions(self, monkeypatch):
        """Test complex nested Q with multiple base conditions."""

        def fake_build_frappe_query(self):
            # Verify Q object is stored (OR condition)
            assert len(self.filter_qs) == 1
            q = self.filter_qs[0]
            assert q.connector == "OR"
            assert len(q.children) == 2
            # Verify multiple kwargs are stored
            assert len(self.filters) == 1
            assert "is_online" in self.filters[0]
            assert "year" in self.filters[0]
            return DummyQuery()

        monkeypatch.setattr(ReadQuery, "_build_frappe_query", fake_build_frappe_query, raising=True)

        # Complex query: (status='Active' OR status='Pending') AND is_online=True AND year=2024
        rq = ReadQuery(DummyDocModel).filter(
            Q(status="Active") | Q(status="Pending"),
            is_online=True,
            year=2024,
        )
        rq.all()

        # Verify Q object structure
        assert len(rq.filter_qs) == 1
        assert rq.filter_qs[0].connector == "OR"
        assert len(rq.filter_qs[0].children) == 2
        # Verify kwargs
        assert rq.filters[0]["is_online"] is True
        assert rq.filters[0]["year"] == 2024
