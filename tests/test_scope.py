import pytest

from efd_contribuicoes_csv.scope import ScopeMonth, month_from_efd_period, parse_scope_month


@pytest.mark.parametrize("value", [
    "01/08/2026 a 31/02/2026",
    "01082026 a 31022026",
    "31082026 a 01082026",
    "01082026 a 30092026",
    "01082026 a 31082027",
    "texto 01082026 a 31082026",
])
def test_rejects_invalid_or_non_monthly_period(value: str) -> None:
    with pytest.raises(ValueError, match="período da EFD inválido"):
        month_from_efd_period(value)


@pytest.mark.parametrize("value", ["01082026 a 31082026", "01/08/2026 a 31/08/2026", "15/08/2026 a 31/08/2026"])
def test_accepts_valid_monthly_period(value: str) -> None:
    assert month_from_efd_period(value) == ScopeMonth(2026, 8)


def test_rejects_year_zero() -> None:
    with pytest.raises(ValueError):
        parse_scope_month("01/0000")
