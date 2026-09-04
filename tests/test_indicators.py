from __future__ import annotations

import csv
from pathlib import Path

from efd_contribuicoes_csv import COLUMNS
from efd_contribuicoes_csv.cli import main
from efd_contribuicoes_csv.cfop import cfop_details, is_product_sale_cfop
from efd_contribuicoes_csv.indicators import (
    INDICATOR_COLUMNS,
    INDICATORS,
    generate_indicator_csv,
)

PROJECT_ROOT = Path(__file__).parents[1]
SAMPLE = PROJECT_ROOT / "efd_contribuicoes_sintetico_1000_linhas.txt"


def write_analytical_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COLUMNS, delimiter=";")
        writer.writeheader()
        for values in rows:
            writer.writerow(dict.fromkeys(COLUMNS, "") | values)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def test_generates_scoped_indicators_and_aggregates_other_revenue(
    tmp_path: Path,
) -> None:
    analytical = tmp_path / "analytical.csv"
    indicators = tmp_path / "indicators.csv"
    common = {"CNPJ": "12345678000199", "Período": "08/2026"}
    write_analytical_csv(
        analytical,
        [
            common
            | {
                "Registros": "A100/A170",
                "Tipo Operação": "1",
                "CST PIS": "01",
                "Código Item": "SERV1",
                "Descrição Item": "SERVIÇO",
                "CFOP Faturamento": "5933",
                "Vlr Item": "100,00",
                "Vlr Mercadoria/Operação": "1.000,00",
                "Vlr PIS": "1,65",
                "Vlr Cofins": "7,60",
            },
            common
            | {
                "Registros": "A100/A170",
                "Tipo Operação": "0",
                "Vlr Item": "900,00",
            },
            common
            | {
                "Registros": "C100/C170",
                "Tipo Operação": "1",
                "CST PIS": "01",
                "CFOP": "5101",
                "Código Item": "PROD1",
                "Descrição Item": "PRODUTO",
                "Vlr Item": "200,00",
                "Vlr Mercadoria/Operação": "2.000,00",
                "Vlr PIS": "3,30",
                "Vlr Cofins": "15,20",
            },
            common
            | {
                "Registros": "C100/C170",
                "Tipo Operação": "1",
                "CFOP": "5405",
                "Código Item": "PROD2",
                "Vlr Item": "50,00",
            },
            common
            | {
                "Registros": "C100/C170",
                "Tipo Operação": "1",
                "CST PIS": "01",
                "CFOP": "5152",
                "Código Item": "TRANSF",
                "Vlr Item": "500,00",
            },
            common
                | {
                    "Registros": "F100",
                    "Tipo Operação": "1",
                    "CST PIS": "02",
                    "Alíquota PIS": "0,6500",
                    "Alíquota Cofins": "4,0000",
                "Vlr Mercadoria/Operação": "300,00",
                "Vlr PIS": "1,95",
                "Vlr Cofins": "12,00",
            },
            common
            | {
                "Registros": "F100",
                "Tipo Operação": "1",
                "CST PIS": "02",
                "Alíquota PIS": "1,6500",
                "Alíquota Cofins": "4,0000",
                "Vlr Mercadoria/Operação": "999,00",
            },
            common
            | {
                "Registros": "F100",
                "Tipo Operação": "1",
                "CST PIS": "49",
                "Vlr Mercadoria/Operação": "50,00",
                "Vlr PIS": "0,33",
                "Vlr Cofins": "2,00",
            },
            common
            | {
                "Registros": "F100",
                "Tipo Operação": "1",
                "CST PIS": "49",
                "Vlr Mercadoria/Operação": "25,00",
                "Vlr PIS": "0,16",
                "Vlr Cofins": "1,00",
            },
            common
            | {
                "Registros": "F100",
                "Tipo Operação": "2",
                "CST PIS": "49",
                "Vlr Mercadoria/Operação": "500,00",
            },
            common
            | {
                "Registros": "F550",
                "Tipo Operação": "1",
                "CST PIS": "02",
                "Alíquota Cofins": "4,0000",
                "Vlr Mercadoria/Operação": "700,00",
            },
        ],
    )

    result = generate_indicator_csv(
        analytical,
        indicators,
        cfop_include={"5101", "5405"},
        cfop_exclude={"5405"},
    )
    rows = read_csv(indicators)
    by_indicator = {row["Indicador"]: row for row in rows}

    assert tuple(rows[0]) == INDICATOR_COLUMNS
    assert result.rows == 4
    assert result.source_rows == 6
    assert result.by_indicator == {
        "Receita de venda para serviço": 1,
        "Receita de venda para produto": 1,
        "Receitas financeiras": 2,
        "Outras receitas": 2,
    }

    service = by_indicator["Receita de venda para serviço"]
    assert service["CFOP"] == "5933"
    assert service["Descrição CFOP"] == "Prestação de serviço sujeita ao ISSQN."
    assert service["Âmbito CFOP"] == "Saída interna"
    assert (
        service["Classificação CFOP"]
        == "OUTRAS SAÍDAS DE MERCADORIAS OU PRESTAÇÕES DE SERVIÇOS"
    )
    assert service["Código Item"] == "SERV1"
    assert service["Valor Operação"] == "100,00"

    product = by_indicator["Receita de venda para produto"]
    assert product["CFOP"] == "5101"
    assert product["Descrição CFOP"] == "Venda de produção do estabelecimento."
    assert product["Âmbito CFOP"] == "Saída interna"
    assert (
        product["Classificação CFOP"]
        == "VENDAS DE PRODUÇÃO PRÓPRIA OU DE TERCEIROS"
    )
    assert product["Valor Operação"] == "200,00"

    financial = by_indicator["Receitas financeiras"]
    assert financial["CST PIS"] == "02"
    assert financial["Quantidade Registros"] == "2"
    assert financial["Valor Operação"] == "1299,00"

    other = by_indicator["Outras receitas"]
    assert other["CST PIS"] == "49"
    assert other["Quantidade Registros"] == "2"
    assert other["Valor Operação"] == "75,00"
    assert other["Valor PIS"] == "0,49"
    assert other["Valor Cofins"] == "3,00"


def test_maps_all_cfop_scopes_and_identifies_product_sales() -> None:
    expected_scopes = {
        "1101": "Entrada interna",
        "2101": "Entrada interestadual",
        "3101": "Entrada do exterior",
        "5101": "Saída interna",
        "6101": "Saída interestadual",
        "7101": "Saída para o exterior",
    }

    for cfop, expected_scope in expected_scopes.items():
        description, scope, classification = cfop_details(cfop)
        assert description
        assert scope == expected_scope
        assert classification

    assert is_product_sale_cfop("5101")
    assert is_product_sale_cfop("5405")
    assert is_product_sale_cfop("7501")
    assert not is_product_sale_cfop("5152")
    assert not is_product_sale_cfop("5501")
    assert not is_product_sale_cfop("5551")
    assert not is_product_sale_cfop("5922")


def test_cfop_exclusion_takes_precedence(tmp_path: Path) -> None:
    analytical = tmp_path / "analytical.csv"
    indicators = tmp_path / "indicators.csv"
    write_analytical_csv(
        analytical,
        [
            {
                "Registros": "C100/C170",
                "Tipo Operação": "1",
                "CFOP": "5102",
                "Vlr Item": "10,00",
            }
        ],
    )

    result = generate_indicator_csv(
        analytical,
        indicators,
        cfop_include={"5102"},
        cfop_exclude={"5102"},
    )

    assert result.rows == 0
    assert read_csv(indicators) == []


def test_adds_zero_indicators_for_unprocessed_scope_periods(
    tmp_path: Path,
) -> None:
    analytical = tmp_path / "analytical.csv"
    indicators = tmp_path / "indicators.csv"
    cnpj = "12345678000199"
    august = "01/08/2026 a 31/08/2026"
    september = "01/09/2026 a 30/09/2026"
    october = "01/10/2026 a 31/10/2026"
    write_analytical_csv(
        analytical,
        [
            {
                "CNPJ": cnpj,
                "Período": august,
                "Registros": "C100/C170",
                "Tipo Operação": "1",
                "CST PIS": "01",
                "CFOP": "5102",
                "Código Item": "P1",
                "Vlr Item": "100,00",
            }
        ],
    )

    result = generate_indicator_csv(
        analytical,
        indicators,
        expected_periods=(august, september, october),
        scope_cnpj=cnpj,
    )
    rows = read_csv(indicators)
    zero_rows = [row for row in rows if row["Quantidade Registros"] == "0"]

    assert result.rows == 12
    assert len(zero_rows) == 11
    assert {row["Período"] for row in zero_rows} == {
        august,
        september,
        october,
    }
    assert {row["Indicador"] for row in zero_rows} == set(INDICATORS)
    assert {row["Valor Operação"] for row in zero_rows} == {"0,00"}


def test_cli_applies_cfop_include_and_exclude_filters(tmp_path: Path) -> None:
    analytical = tmp_path / "analytical.csv"
    indicators = tmp_path / "indicators.csv"

    exit_code = main(
        [
            str(SAMPLE),
            "--saida",
            str(analytical),
            "--saida-indicadores",
            str(indicators),
            "--cfop-incluir",
            "5101,5102",
            "--cfop-excluir",
            "5102",
        ]
    )
    product_rows = [
        row
        for row in read_csv(indicators)
        if row["Indicador"] == "Receita de venda para produto"
    ]

    assert exit_code == 0
    assert product_rows
    assert {row["CFOP"] for row in product_rows} == {"5101"}
