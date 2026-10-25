"""Unit tests for named-parameter handling shared by all Db adapters (arch 03 §3.9, ADR-002)."""
from decimal import Decimal

import pytest

from tasklane.platform.db import DataApiRuleViolation, Json, to_pyformat, validate_params, validate_sql


class TestToPyformat:
    def test_named_params_become_pyformat(self) -> None:
        assert to_pyformat("select :a, :b_2") == "select %(a)s, %(b_2)s"

    def test_casts_are_not_params(self) -> None:
        assert to_pyformat("select :v::jsonb, x::text") == "select %(v)s::jsonb, x::text"

    def test_string_literals_are_untouched(self) -> None:
        assert to_pyformat("select ':not_a_param', :p") == "select ':not_a_param', %(p)s"

    def test_percent_is_escaped(self) -> None:
        assert to_pyformat("select 'a%' like :p") == "select 'a%%' like %(p)s"

    def test_quoted_identifiers_are_untouched(self) -> None:
        assert to_pyformat('select "col:x" from t where id = :id') == 'select "col:x" from t where id = %(id)s'


class TestValidateParams:
    @pytest.mark.parametrize("value", [None, True, 1, "s", Decimal("1.5"), Json({"a": [1]}), Json([1, 2])])
    def test_allowed_types(self, value: object) -> None:
        validate_params("select :p", {"p": value})

    @pytest.mark.parametrize("value", [[1, 2], (1,), {1}, {"a": 1}])
    def test_arrays_and_raw_containers_are_rejected(self, value: object) -> None:
        # Data API has no array parameters (AR-4); containers must be passed explicitly as Json(...)
        with pytest.raises(DataApiRuleViolation, match="array|container"):
            validate_params("select :p", {"p": value})

    def test_float_is_rejected_use_decimal(self) -> None:
        with pytest.raises(DataApiRuleViolation, match="float"):
            validate_params("select :p", {"p": 1.5})

    def test_missing_param_is_rejected(self) -> None:
        with pytest.raises(DataApiRuleViolation, match="missing"):
            validate_params("select :a, :b", {"a": 1})

    def test_unused_param_is_rejected(self) -> None:
        with pytest.raises(DataApiRuleViolation, match="unused"):
            validate_params("select :a", {"a": 1, "b": 2})


class TestValidateSql:
    @pytest.mark.parametrize("sql", ["select 1 where x = any(:ids)", "select 1 where x = ANY ( :ids )",
                                     "select 1 where x <> all(:ids)"])
    def test_any_all_over_parameter_is_rejected(self, sql: str) -> None:
        # PERF-18: use `in (select ... from jsonb_array_elements_text(:p::jsonb))` or containment
        with pytest.raises(DataApiRuleViolation, match="any|all"):
            validate_sql(sql)

    def test_any_over_subquery_is_fine(self) -> None:
        validate_sql("select 1 where x = any(array(select 1))")

    @pytest.mark.parametrize("sql", ["select 1 returning old.v", "update t set a=1 returning OLD.a"])
    def test_pg18_returning_old_is_rejected(self, sql: str) -> None:
        # Portability guard: keep the pre-image CTE pattern (arch 03 §3.5) instead of PG18-only syntax
        with pytest.raises(DataApiRuleViolation, match="old"):
            validate_sql(sql)
