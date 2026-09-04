from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .cfop import cfop_details, is_product_sale_cfop

INDICATOR_COLUMNS = (
    "CNPJ",
    "Período",
    "Indicador",
    "Registros",
    "CST PIS",
    "CFOP",
    "Descrição CFOP",
    "Âmbito CFOP",
    "Classificação CFOP",
    "Código Item",
    "Descrição Item",
    "Quantidade Registros",
    "Valor Operação",
    "Valor PIS",
    "Valor Cofins",
)

INDICATORS = (
    "Receita de venda para serviço",
    "Receita de venda para produto",
    "Receitas financeiras",
    "Outras receitas",
)

INDICATOR_RECORDS = {
    "Receita de venda para serviço": "A100/A170",
    "Receita de venda para produto": "C100/C170",
    "Receitas financeiras": "F100",
    "Outras receitas": "F100",
}


@dataclass(frozen=True)
class IndicatorResult:
    output_path: Path
    rows: int
    source_rows: int
    by_indicator: dict[str, int]


@dataclass
class _Aggregate:
    row: dict[str, str]
    quantity: int = 0
    operation_value: Decimal = Decimal(0)
    pis_value: Decimal = Decimal(0)
    cofins_value: Decimal = Decimal(0)


def _decimal(value: str, field: str) -> Decimal:
    raw = value.strip()
    if not raw:
        return Decimal(0)
    normalized = raw.replace(".", "").replace(",", ".") if "," in raw else raw
    try:
        return Decimal(normalized)
    except InvalidOperation as exc:
        raise ValueError(f"valor inválido em {field}: {value!r}") from exc


def _format_money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _accepts_cfop(cfop: str, include: set[str], exclude: set[str]) -> bool:
    if include and cfop not in include:
        return False
    return cfop not in exclude


def _classify(
    row: dict[str, str], cfop_include: set[str], cfop_exclude: set[str]
) -> str | None:
    if row["Tipo Operação"] != "1":
        return None

    records = row["Registros"]
    if records == "A100/A170":
        return INDICATORS[0]
    if (
        records == "C100/C170"
        and is_product_sale_cfop(row["CFOP"])
        and _accepts_cfop(row["CFOP"], cfop_include, cfop_exclude)
    ):
        return INDICATORS[1]
    if records != "F100":
        return None

    cst_pis = row["CST PIS"]
    if (
        cst_pis == "02"
        and _decimal(row["Alíquota Cofins"], "Alíquota Cofins") == Decimal(4)
    ):
        return INDICATORS[2]
    if cst_pis != "02":
        return INDICATORS[3]
    return None


def _group_values(row: dict[str, str], indicator: str) -> dict[str, str]:
    is_f100 = row["Registros"] == "F100"
    cfop = "" if is_f100 else row["CFOP"]
    if row["Registros"] == "A100/A170" and not cfop:
        cfop = row["CFOP Faturamento"]
    cfop_description, cfop_scope, cfop_classification = cfop_details(cfop)
    return {
        "CNPJ": row["CNPJ"],
        "Período": row["Período"],
        "Indicador": indicator,
        "Registros": row["Registros"],
        "CST PIS": row["CST PIS"],
        "CFOP": cfop,
        "Descrição CFOP": cfop_description,
        "Âmbito CFOP": cfop_scope,
        "Classificação CFOP": cfop_classification,
        "Código Item": "" if is_f100 else row["Código Item"],
        "Descrição Item": "" if is_f100 else row["Descrição Item"],
        "Quantidade Registros": "",
        "Valor Operação": "",
        "Valor PIS": "",
        "Valor Cofins": "",
    }


def generate_indicator_csv(
    analytical_path: str | Path,
    output_path: str | Path,
    *,
    delimiter: str = ";",
    cfop_include: set[str] | frozenset[str] = frozenset(),
    cfop_exclude: set[str] | frozenset[str] = frozenset(),
    expected_periods: tuple[str, ...] = (),
    scope_cnpj: str = "",
) -> IndicatorResult:
    """Gera os indicadores a partir do CSV analítico já convertido."""

    source = Path(analytical_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if source == target:
        raise ValueError("o CSV de indicadores não pode sobrescrever o CSV analítico")
    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")

    include = {code.strip() for code in cfop_include if code.strip()}
    exclude = {code.strip() for code in cfop_exclude if code.strip()}
    aggregates: dict[tuple[str, ...], _Aggregate] = {}
    observed: Counter[str] = Counter()

    with source.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream, delimiter=delimiter)
        missing = {
            "CNPJ",
            "Período",
            "Registros",
            "Tipo Operação",
            "CST PIS",
            "Alíquota PIS",
            "Alíquota Cofins",
            "CFOP",
            "CFOP Faturamento",
            "Código Item",
            "Descrição Item",
            "Vlr Item",
            "Vlr Mercadoria/Operação",
            "Vlr PIS",
            "Vlr Cofins",
        } - set(reader.fieldnames or ())
        if missing:
            fields = ", ".join(sorted(missing))
            raise ValueError(f"CSV analítico sem as colunas obrigatórias: {fields}")

        source_cnpjs: set[str] = set()
        for row in reader:
            if row["CNPJ"]:
                source_cnpjs.add(row["CNPJ"])
            indicator = _classify(row, include, exclude)
            if indicator is None:
                continue
            values = _group_values(row, indicator)
            key = tuple(values[column] for column in INDICATOR_COLUMNS[:-4])
            aggregate = aggregates.setdefault(key, _Aggregate(values))
            aggregate.quantity += 1
            amount_field = (
                "Vlr Mercadoria/Operação" if row["Registros"] == "F100" else "Vlr Item"
            )
            aggregate.operation_value += _decimal(row[amount_field], amount_field)
            aggregate.pis_value += _decimal(row["Vlr PIS"], "Vlr PIS")
            aggregate.cofins_value += _decimal(row["Vlr Cofins"], "Vlr Cofins")
            observed[indicator] += 1

    output_rows: list[dict[str, str]] = []
    for aggregate in aggregates.values():
        aggregate.row["Quantidade Registros"] = str(aggregate.quantity)
        aggregate.row["Valor Operação"] = _format_money(aggregate.operation_value)
        aggregate.row["Valor PIS"] = _format_money(aggregate.pis_value)
        aggregate.row["Valor Cofins"] = _format_money(aggregate.cofins_value)
        output_rows.append(aggregate.row)

    cnpjs = source_cnpjs or ({scope_cnpj} if scope_cnpj else set())
    existing_indicators = {
        (row["CNPJ"], row["Período"], row["Indicador"]) for row in output_rows
    }
    for cnpj in sorted(cnpjs):
        for period in expected_periods:
            for indicator in INDICATORS:
                if (cnpj, period, indicator) in existing_indicators:
                    continue
                output_rows.append(
                    {
                        "CNPJ": cnpj,
                        "Período": period,
                        "Indicador": indicator,
                        "Registros": INDICATOR_RECORDS[indicator],
                        "CST PIS": "",
                        "CFOP": "",
                        "Descrição CFOP": "",
                        "Âmbito CFOP": "",
                        "Classificação CFOP": "",
                        "Código Item": "",
                        "Descrição Item": "",
                        "Quantidade Registros": "0",
                        "Valor Operação": "0,00",
                        "Valor PIS": "0,00",
                        "Valor Cofins": "0,00",
                    }
                )

    indicator_order = {name: index for index, name in enumerate(INDICATORS)}
    output_rows.sort(
        key=lambda row: (
            row["CNPJ"],
            row["Período"],
            indicator_order[row["Indicador"]],
            row["CST PIS"],
            row["CFOP"],
            row["Código Item"],
        )
    )

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=INDICATOR_COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(output_rows)

    counts = {name: observed.get(name, 0) for name in INDICATORS}
    return IndicatorResult(target, len(output_rows), sum(observed.values()), counts)
