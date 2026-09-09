from __future__ import annotations

import csv
import tempfile
from collections import Counter
from dataclasses import dataclass, replace
from pathlib import Path

from .comparison import (
    COMPARISON_COLUMNS,
    COVERAGE_COLUMNS,
    STATUSES,
    ComparisonResult,
    EFDComparisonError,
    compare_efd_files,
    inspect_efd_file,
)
from .converter import COLUMNS, SUPPORTED_OUTPUTS, ConversionResult, convert_file
from .excel import create_excel_workbook
from .identifiers import cnpj_root
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
    workbook_path: Path
    pending_notes_path: Path
    coverage_path: Path
    pending_notes: int


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
    cnpj_roots = sorted({cnpj_root(cnpj) for cnpj in cnpjs})
    if len(years) > 1:
        issues.append(
            "foram encontrados arquivos de mais de um ano: "
            + ", ".join(str(year) for year in years)
        )
    if len(cnpj_roots) > 1:
        issues.append(
            "foram encontrados CNPJs de raízes diferentes: " + ", ".join(cnpjs)
        )

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
        discovered["contribution"][0][2] if discovered["contribution"] else cnpjs[0],
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
            if row["Presença EFD Contribuições"] == "NAO_LOCALIZADA"
            and row["Tipo Evidência EFD ICMS"] == "DOCUMENTO"
            and int(row["Quantidade EFD ICMS"]) > 0
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


def _write_review_reports(
    comparison: ComparisonResult, output: Path, *, delimiter: str,
) -> tuple[Path, Path, int]:
    pending_path = output / "efd_pendencias_conferencia.csv"
    coverage_path = output / "efd_cobertura_registros.csv"
    with comparison.output_path.open(encoding="utf-8-sig", newline="") as stream:
        pending = [row for row in csv.DictReader(stream, delimiter=delimiter) if row["Motivo da Revisão"]]
    for path, columns, rows in (
        (pending_path, COMPARISON_COLUMNS, pending),
        (coverage_path, COVERAGE_COLUMNS, comparison.coverage),
    ):
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=columns, delimiter=delimiter, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    return pending_path, coverage_path, len(pending)


def _reconcile_other_periods(path: Path, *, delimiter: str) -> tuple[int, Counter[str]]:
    """Procura chaves eletrônicas nos outros meses fornecidos do mesmo ano."""
    with path.open(encoding="utf-8-sig", newline="") as stream:
        rows = list(csv.DictReader(stream, delimiter=delimiter))
    by_key: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        key = row["Chave EFD Contribuições"]
        if (len(key) == 44 and key.isdecimal()
                and row["Tipo Evidência EFD Contribuições"] == "DOCUMENTO"
                and not row["Registros EFD Contribuições"].startswith("A")):
            by_key.setdefault(key, []).append(row)
    consumed: set[int] = set()
    for row in rows:
        if row["Tipo Evidência EFD ICMS"] != "DOCUMENTO" or row["Quantidade EFD Contribuições"] != "0":
            continue
        if row["Registros EFD ICMS"] == "B020" and row["Modelo EFD ICMS"] == "03":
            continue
        candidates = [candidate for candidate in by_key.get(row["Chave EFD ICMS"], [])
                      if candidate["Período EFD Contribuições"] != row["Período EFD ICMS"]]
        if not candidates:
            continue
        if len(candidates) == 1:
            for column in COMPARISON_COLUMNS:
                if column.endswith(" EFD Contribuições"):
                    row[column] = candidates[0][column]
            consumed.add(id(candidates[0]))
        else:
            row["Quantidade EFD Contribuições"] = str(sum(int(item["Quantidade EFD Contribuições"]) for item in candidates))
            row["Tipo Evidência EFD Contribuições"] = "DOCUMENTO"
        row["Status"] = "REVISAO_NECESSARIA"
        row["Presença EFD Contribuições"] = "PRESENTE"
        row["Critério de Conferência"] = "CHAVE EM OUTRO PERÍODO"
        row["Motivo da Revisão"] = (
            "Chave localizada em outro período; revisar a competência e os valores."
            if len(candidates) == 1 else
            "Chave localizada em vários períodos das Contribuições; revisar duplicidade e competência."
        )
        row["Divergências"] = "Período de escrituração"
        row["Evidências EFD Contribuições"] = "; ".join(
            f"{item['Arquivo EFD Contribuições']} ({item['Período EFD Contribuições']}), linhas {item['Linhas EFD Contribuições']}"
            for item in candidates
        )
    rows = [row for row in rows if not (id(row) in consumed and row["Quantidade EFD ICMS"] == "0")]
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COMPARISON_COLUMNS, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    return len(rows), Counter(row["Status"] for row in rows)


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
    """Gera todas as saídas antes de substituir os relatórios anteriores."""

    output = Path(output_directory).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="efd-fluxo-", dir=output.parent) as temporary:
        result = _process_efd_files(
            contribution_path, icms_path, temporary,
            delimiter=delimiter,
            cfop_include=cfop_include,
            cfop_exclude=cfop_exclude,
            period_start=period_start,
            period_end=period_end,
        )
        return _publish_result(result, output, (contribution_path, icms_path))


def _publish_result(
    result: WorkflowResult,
    output_directory: str | Path,
    input_paths: tuple[str | Path, ...],
) -> WorkflowResult:
    output = Path(output_directory).expanduser().resolve()
    inputs = {Path(path).expanduser().resolve() for path in input_paths}
    sources = list(result.output_directory.iterdir())
    if any((output / source.name).resolve() in inputs for source in sources):
        raise ValueError("os relatórios não podem sobrescrever um arquivo EFD")
    output.mkdir(parents=True, exist_ok=True)
    for source in sources:
        source.replace(output / source.name)
    return replace(
        result,
        output_directory=output,
        conversion=replace(
            result.conversion, output_path=output / result.conversion.output_path.name
        ),
        indicators=replace(
            result.indicators, output_path=output / result.indicators.output_path.name
        ),
        comparison=replace(
            result.comparison, output_path=output / result.comparison.output_path.name
        ),
        scope_path=output / result.scope_path.name,
        missing_notes_path=output / result.missing_notes_path.name,
        workbook_path=output / result.workbook_path.name,
        pending_notes_path=output / result.pending_notes_path.name,
        coverage_path=output / result.coverage_path.name,
    )


def _process_efd_files(
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
    workbook_path = output / "efd_resultado.xlsx"

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
    pending_path, coverage_path, pending_count = _write_review_reports(comparison, output, delimiter=delimiter)
    create_excel_workbook(output, workbook_path, delimiter=delimiter)
    return WorkflowResult(
        output,
        conversion,
        indicators,
        comparison,
        scope_path,
        missing_notes_path,
        missing_notes,
        workbook_path,
        pending_path,
        coverage_path,
        pending_count,
    )


def process_annual_efd_input(
    inventory: AnnualEFDInventory,
    output_directory: str | Path,
    *,
    delimiter: str = ";",
    cfop_include: set[str] | frozenset[str] = frozenset(),
    cfop_exclude: set[str] | frozenset[str] = frozenset(),
) -> WorkflowResult:
    """Gera o resultado anual completo antes de substituir as saídas anteriores."""

    output = Path(output_directory).expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="efd-fluxo-anual-", dir=output.parent) as temporary:
        result = _process_annual_efd_input(
            inventory, temporary,
            delimiter=delimiter,
            cfop_include=cfop_include,
            cfop_exclude=cfop_exclude,
        )
        return _publish_result(
            result, output,
            (*inventory.contributions.values(), *inventory.icms.values()),
        )


def _process_annual_efd_input(
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
    workbook_path = output / "efd_resultado.xlsx"

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
        available_months = sorted(inventory.contributions.keys() | inventory.icms.keys())
        for month in available_months:
            part = temp / f"comparacao-{month.month:02d}.csv"
            comparison_results.append(
                compare_efd_files(
                    inventory.contributions.get(month),
                    inventory.icms.get(month),
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

    comparison_rows, comparison_counts = _reconcile_other_periods(comparison_path, delimiter=delimiter)
    comparison = ComparisonResult(
        comparison_path,
        comparison_rows,
        sum(result.contribution_notes for result in comparison_results),
        sum(result.icms_notes for result in comparison_results),
        {status: comparison_counts.get(status, 0) for status in STATUSES},
        str(inventory.year),
        str(inventory.year),
        inventory.cnpj,
        tuple(row for result in comparison_results for row in result.coverage),
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
    pending_path, coverage_path, pending_count = _write_review_reports(comparison, output, delimiter=delimiter)
    create_excel_workbook(output, workbook_path, delimiter=delimiter)
    return WorkflowResult(
        output,
        conversion,
        indicators,
        comparison,
        scope_path,
        missing_notes_path,
        missing_notes,
        workbook_path,
        pending_path,
        coverage_path,
        pending_count,
    )
