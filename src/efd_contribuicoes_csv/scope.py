from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, order=True)
class ScopeMonth:
    year: int
    month: int

    @property
    def label(self) -> str:
        last_day = calendar.monthrange(self.year, self.month)[1]
        return (
            f"01/{self.month:02d}/{self.year:04d} a "
            f"{last_day:02d}/{self.month:02d}/{self.year:04d}"
        )


def parse_scope_month(value: str) -> ScopeMonth:
    match = re.fullmatch(r"(0[1-9]|1[0-2])/(\d{4})", value.strip())
    if match is None:
        raise ValueError("o período deve estar no formato MM/AAAA")
    return ScopeMonth(int(match.group(2)), int(match.group(1)))


def month_from_efd_period(value: str) -> ScopeMonth:
    dates = re.findall(r"(\d{2})/?(\d{2})/?(\d{4})", value)
    if not dates:
        raise ValueError(f"período da EFD inválido: {value!r}")
    day, month, year = dates[0]
    try:
        parsed = date(int(year), int(month), int(day))
    except ValueError as exc:
        raise ValueError(f"período da EFD inválido: {value!r}") from exc
    return ScopeMonth(parsed.year, parsed.month)


def build_scope(
    start: str | None,
    end: str | None,
    *,
    fallback_period: str,
) -> tuple[ScopeMonth, ...]:
    if (start is None) != (end is None):
        raise ValueError(
            "informe --periodo-inicial e --periodo-final em conjunto"
        )
    if start is None:
        return (month_from_efd_period(fallback_period),)

    first = parse_scope_month(start)
    last = parse_scope_month(end or "")
    if first > last:
        raise ValueError("o período inicial não pode ser posterior ao período final")

    months: list[ScopeMonth] = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        months.append(ScopeMonth(year, month))
        month += 1
        if month == 13:
            year += 1
            month = 1
    return tuple(months)


def validate_period_in_scope(period: str, scope: tuple[ScopeMonth, ...]) -> None:
    month = month_from_efd_period(period)
    if month not in scope:
        raise ValueError(
            f"o período {month.month:02d}/{month.year} do arquivo está fora do escopo"
        )
