from __future__ import annotations

import csv
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from .comparison import (
    COMPARISON_COLUMNS,
    STATUSES,
    ComparisonResult,
    EFDComparisonError,
    compare_efd_files,
    inspect_efd_file,
)
from .converter import COLUMNS, SUPPORTED_OUTPUTS, ConversionResult, convert_file
from .indicators import IndicatorResult, generate_indicator_csv
from .scope import ScopeMonth, build_scope, month_from_efd_period, validate_period_in_scope

SCOPE_COLUMNS = (
    "Período",
    "EFD Contribuições",
    "EFD ICMS/IPI",
    "Status",
)


@dataclass(frozen=True)
class WorkflowResult:
    output_directory: Path
    conversion: ConversionResult
    indicators: IndicatorResult
    comparison: ComparisonResult
    scope_path: Path
    missing_notes_path: Path
    missing_notes: int


@dataclass(frozen=True)
class AnnualEFDInventory:
    input_directory: Path
    year: int
    cnpj: str
    contributions: dict[ScopeMonth, Path]
    icms: dict[ScopeMonth, Path]
    missing_contributions: tuple[ScopeMonth, ...]
    missing_icms: tuple[ScopeMonth, ...]

    @property
    def has_missing_months(self) -> bool:
        return bool(self.missing_contributions or self.missing_icms)


class EFDInventoryError(ValueError):
    """Inconsistências que impedem identificar com segurança o escopo anual."""

    def __init__(self, issues: list[str]) -> None:
        self.issues = tuple(issues)
        super().__init__("\n".join(issues))


def _input_files(directory: Path) -> list[Path]:
    return sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.casefold() == ".txt"
    )


def discover_annual_efd_input(input_directory: str | Path) -> AnnualEFDInventory:
    """Valida as pastas e identifica um arquivo de cada EFD para cada mês."""

    root = Path(input_directory).expanduser().resolve()
    folders = {
        "contribution": root / "efd_contribuicoes",
        "icms": root / "efd_icms",
    }
    labels = {
        "contribution": "EFD Contribuições",
        "icms": "EFD ICMS/IPI",
    }
    issues: list[str] = []
    discovered: dict[str, list[tuple[ScopeMonth, Path, str]]] = {
        source: [] for source in folders
    }

    if not root.is_dir():
        raise EFDInventoryError([f"pasta de entrada não encontrada: {root}"])

    for source, directory in folders.items():
        if not directory.is_dir():
            issues.append(f"pasta obrigatória não encontrada: {directory}")
            continue
        files = _input_files(directory)
        if not files:
            issues.append(f"nenhum arquivo TXT encontrado em {directory}")
            continue
        for path in files:
            try:
                info = inspect_efd_file(path, source=source)
                month = month_from_efd_period(info.period)
            except (EFDComparisonError, OSError, ValueError) as exc:
                issues.append(f"{labels[source]} — {path.name}: {exc}")
                continue
            discovered[source].append((month, path, info.cnpj))

    all_files = [item for values in discovered.values() for item in values]
    years = sorted({month.year for month, _, _ in all_files})
    cnpjs = sorted({cnpj for _, _, cnpj in all_files})
    if len(years) > 1:
        issues.append(
            "foram encontrados arquivos de mais de um ano: "
            + ", ".join(str(year) for year in years)
        )
    if len(cnpjs) > 1:
        issues.append("foram encontrados CNPJs diferentes: " + ", ".join(cnpjs))

    indexed: dict[str, dict[ScopeMonth, Path]] = {source: {} for source in folders}
    for source, values in discovered.items():
        by_month: dict[ScopeMonth, list[Path]] = {}
        for month, path, _ in values:
            by_month.setdefault(month, []).append(path)
        for month, paths in sorted(by_month.items()):
            if len(paths) > 1:
                filenames = ", ".join(path.name for path in paths)
                issues.append(
                    f"{labels[source]} duplicada em {month.month:02d}/{month.year}: "
                    f"{filenames}"
                )
            else:
                indexed[source][month] = paths[0]

    if issues:
        raise EFDInventoryError(issues)
    if not years or not cnpjs:
        raise EFDInventoryError(["não foi possível identificar ano e CNPJ das EFDs"])

    year = years[0]
    expected = tuple(ScopeMonth(year, month) for month in range(1, 13))
    contributions = indexed["contribution"]
    icms = indexed["icms"]
    return AnnualEFDInventory(
        root,
        year,
        cnpjs[0],
        contributions,
        icms,
        tuple(month for month in expected if month not in contributions),
        tuple(month for month in expected if month not in icms),
    )


def _merge_csv_files(
    sources: list[Path],
    target: Path,
    *,
    columns: tuple[str, ...],
    delimiter: str,
) -> int:
    rows = 0
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(
            output,
            fieldnames=columns,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        for source in sources:
            with source.open(encoding="utf-8-sig", newline="") as stream:
                for row in csv.DictReader(stream, delimiter=delimiter):
                    writer.writerow(row)
                    rows += 1
    return rows


def _write_annual_scope_csv(
    path: Path,
    inventory: AnnualEFDInventory,
    *,
    delimiter: str,
) -> None:
    rows: list[dict[str, str]] = []
    for month in (ScopeMonth(inventory.year, value) for value in range(1, 13)):
        has_contribution = month in inventory.contributions
        has_icms = month in inventory.icms
        missing: list[str] = []
        if not has_contribution:
            missing.append("EFD Contribuições")
        if not has_icms:
            missing.append("EFD ICMS/IPI")
        rows.append(
            {
                "Período": month.label,
                "EFD Contribuições": "PROCESSADO" if has_contribution else "AUSENTE",
                "EFD ICMS/IPI": "PROCESSADO" if has_icms else "AUSENTE",
                "Status": (
                    "PROCESSADO"
                    if not missing
                    else f"SEM PROCESSAMENTO: {', '.join(missing)}"
                ),
            }
        )

    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=SCOPE_COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_scope_csv(
    path: Path,
    *,
    scope_labels: tuple[str, ...],
    contribution_period: str,
    icms_period: str,
    delimiter: str,
) -> None:
    contribution_label = month_from_efd_period(contribution_period).label
    icms_label = month_from_efd_period(icms_period).label
    rows: list[dict[str, str]] = []
    for period in scope_labels:
        has_contribution = period == contribution_label
        has_icms = period == icms_label
        missing: list[str] = []
        if not has_contribution:
            missing.append("EFD Contribuições")
        if not has_icms:
            missing.append("EFD ICMS/IPI")
        rows.append(
            {
                "Período": period,
                "EFD Contribuições": "PROCESSADO" if has_contribution else "AUSENTE",
                "EFD ICMS/IPI": "PROCESSADO" if has_icms else "AUSENTE",
                "Status": (
                    "PROCESSADO"
                    if not missing
                    else f"SEM PROCESSAMENTO: {', '.join(missing)}"
                ),
            }
        )

    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=SCOPE_COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)


def _write_missing_notes_csv(
    comparison_path: Path,
    output_path: Path,
    *,
    delimiter: str,
) -> int:
    with comparison_path.open(encoding="utf-8-sig", newline="") as stream:
        rows = [
            row
            for row in csv.DictReader(stream, delimiter=delimiter)
            if row["Status"] == "SOMENTE_EFD_ICMS"
        ]
    with output_path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=COMPARISON_COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def process_efd_files(
    contribution_path: str | Path,
    icms_path: str | Path,
    output_directory: str | Path,
    *,
    delimiter: str = ";",
    cfop_include: set[str] | frozenset[str] = frozenset(),
    cfop_exclude: set[str] | frozenset[str] = frozenset(),
    period_start: str | None = None,
    period_end: str | None = None,
) -> WorkflowResult:
    """Executa consolidação, indicadores e validação entre as duas EFDs."""

    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    analytical_path = output / "efd_contribuicoes_analitico.csv"
    indicator_path = output / "efd_contribuicoes_indicadores.csv"
    comparison_path = output / "efd_comparacao_notas.csv"
    scope_path = output / "efd_periodos_escopo.csv"
    missing_notes_path = output / "efd_icms_nao_lancadas_contribuicoes.csv"

    conversion = convert_file(contribution_path, analytical_path, delimiter=delimiter)
    scope = build_scope(
        period_start,
        period_end,
        fallback_period=conversion.period,
    )
    validate_period_in_scope(conversion.period, scope)

    comparison = compare_efd_files(
        contribution_path,
        icms_path,
        comparison_path,
        delimiter=delimiter,
    )
    validate_period_in_scope(comparison.icms_period, scope)

    scope_labels = tuple(month.label for month in scope)
    indicators = generate_indicator_csv(
        conversion.output_path,
        indicator_path,
        delimiter=delimiter,
        cfop_include=cfop_include,
        cfop_exclude=cfop_exclude,
        expected_periods=scope_labels,
        scope_cnpj=conversion.cnpj,
    )
    _write_scope_csv(
        scope_path,
        scope_labels=scope_labels,
        contribution_period=conversion.period,
        icms_period=comparison.icms_period,
        delimiter=delimiter,
    )
    missing_notes = _write_missing_notes_csv(
        comparison.output_path,
        missing_notes_path,
        delimiter=delimiter,
    )
    return WorkflowResult(
        output,
        conversion,
        indicators,
        comparison,
        scope_path,
        missing_notes_path,
        missing_notes,
    )


def process_annual_efd_input(
    inventory: AnnualEFDInventory,
    output_directory: str | Path,
    *,
    delimiter: str = ";",
    cfop_include: set[str] | frozenset[str] = frozenset(),
    cfop_exclude: set[str] | frozenset[str] = frozenset(),
) -> WorkflowResult:
    """Consolida todos os períodos disponíveis de uma entrada anual validada."""

    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")
    output = Path(output_directory).expanduser().resolve()
    output.mkdir(parents=True, exist_ok=True)

    analytical_path = output / "efd_contribuicoes_analitico.csv"
    indicator_path = output / "efd_contribuicoes_indicadores.csv"
    comparison_path = output / "efd_comparacao_notas.csv"
    scope_path = output / "efd_periodos_escopo.csv"
    missing_notes_path = output / "efd_icms_nao_lancadas_contribuicoes.csv"

    conversion_results: list[ConversionResult] = []
    comparison_results: list[ComparisonResult] = []
    with tempfile.TemporaryDirectory(prefix="efd-anual-") as temporary:
        temp = Path(temporary)
        analytical_parts: list[Path] = []
        for month, source in sorted(inventory.contributions.items()):
            part = temp / f"contribuicoes-{month.month:02d}.csv"
            conversion_results.append(convert_file(source, part, delimiter=delimiter))
            analytical_parts.append(part)
        analytical_rows = _merge_csv_files(
            analytical_parts,
            analytical_path,
            columns=COLUMNS,
            delimiter=delimiter,
        )

        comparison_parts: list[Path] = []
        paired_months = sorted(inventory.contributions.keys() & inventory.icms.keys())
        for month in paired_months:
            part = temp / f"comparacao-{month.month:02d}.csv"
            comparison_results.append(
                compare_efd_files(
                    inventory.contributions[month],
                    inventory.icms[month],
                    part,
                    delimiter=delimiter,
                )
            )
            comparison_parts.append(part)
        comparison_rows = _merge_csv_files(
            comparison_parts,
            comparison_path,
            columns=COMPARISON_COLUMNS,
            delimiter=delimiter,
        )

    conversion_counts: Counter[str] = Counter()
    encodings: set[str] = set()
    for result in conversion_results:
        conversion_counts.update(result.by_record)
        encodings.add(result.input_encoding)
    conversion = ConversionResult(
        analytical_path,
        analytical_rows,
        {name: conversion_counts.get(name, 0) for name in SUPPORTED_OUTPUTS},
        ", ".join(sorted(encodings)),
        str(inventory.year),
        inventory.cnpj,
    )

    comparison_counts: Counter[str] = Counter()
    for result in comparison_results:
        comparison_counts.update(result.by_status)
    comparison = ComparisonResult(
        comparison_path,
        comparison_rows,
        sum(result.contribution_notes for result in comparison_results),
        sum(result.icms_notes for result in comparison_results),
        {status: comparison_counts.get(status, 0) for status in STATUSES},
        str(inventory.year),
        str(inventory.year),
        inventory.cnpj,
    )

    expected_periods = tuple(
        ScopeMonth(inventory.year, month).label for month in range(1, 13)
    )
    indicators = generate_indicator_csv(
        analytical_path,
        indicator_path,
        delimiter=delimiter,
        cfop_include=cfop_include,
        cfop_exclude=cfop_exclude,
        expected_periods=expected_periods,
        scope_cnpj=inventory.cnpj,
    )
    _write_annual_scope_csv(scope_path, inventory, delimiter=delimiter)
    missing_notes = _write_missing_notes_csv(
        comparison_path,
        missing_notes_path,
        delimiter=delimiter,
    )
    return WorkflowResult(
        output,
        conversion,
        indicators,
        comparison,
        scope_path,
        missing_notes_path,
        missing_notes,
    )
