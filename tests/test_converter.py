from __future__ import annotations

import csv
from pathlib import Path

import pytest

from efd_contribuicoes_csv import COLUMNS, convert_file
from efd_contribuicoes_csv.cli import main
from efd_contribuicoes_csv.converter import EFDParseError, SUPPORTED_OUTPUTS

PROJECT_ROOT = Path(__file__).parents[1]
SAMPLE = PROJECT_ROOT / "efd_contribuicoes_sintetico_1000_linhas.txt"
ICMS_SAMPLE = PROJECT_ROOT / "efd_icms_sintetico_estrutura_real.txt"
OTHER_PAIRS_SAMPLE = (
    PROJECT_ROOT / "tests" / "fixtures" / "efd_contribuicoes_outros_pares.txt"
)


def sped_line(*fields: str) -> str:
    return f"|{'|'.join(fields)}|\n"


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def record_counts(**overrides: int) -> dict[str, int]:
    return {name: overrides.get(name, 0) for name in SUPPORTED_OUTPUTS}


def test_converts_supplied_compact_sample(tmp_path: Path) -> None:
    output = tmp_path / "sample.csv"

    result = convert_file(SAMPLE, output)
    rows = read_csv(output)

    assert result.rows == 611
    assert result.by_record == record_counts(
        **{
            "A100/A170": 200,
            "C100/C170": 240,
            "F100": 38,
            "F550": 133,
        }
    )
    assert len(rows) == 611
    assert tuple(rows[0]) == COLUMNS

    first_a = rows[0]
    assert first_a["CNPJ"] == "99999999000199"
    assert first_a["Período"] == "01/08/2026 a 31/08/2026"
    assert first_a["Registros"] == "A100/A170"
    assert first_a["Código Participante"] == "PART001"
    assert first_a["CNPJ Participante"] == "99000000010001"
    assert first_a["UF Origem/Destino"] == "RJ"
    assert first_a["Número Documento"] == "AS00010001"
    assert first_a["Série"] == "1"
    assert first_a["Data Documento"] == "01/08/2026"
    assert first_a["Código Item"] == "ITEM001"
    assert first_a["Descrição Item"] == "ITEM OU SERVICO SINTETICO 001"
    assert first_a["Código Serviço"] == "1202"
    assert first_a["CFOP"] == ""
    assert first_a["CFOP Faturamento"] == "5933"
    assert first_a["Natureza Crédito"] == "01"
    assert first_a["Conta Contábil"] == "CTA_SERV"
    assert first_a["Débito/Crédito"] == "Crédito"
    assert first_a["Unidade Medida"] == ""
    assert first_a["Vlr Frete"] == ""

    first_c = rows[200]
    assert first_c["Registros"] == "C100/C170"
    assert first_c["Número Documento"] == "20001"
    assert first_c["Chave NF-e"].startswith("352608")
    assert first_c["Qtde"] == "2,000"
    assert first_c["NCM"] == "84000009"
    assert first_c["CST PIS"] == "06"
    assert first_c["CFOP"] == "5102"
    assert first_c["Débito/Crédito"] == "Débito"

    first_f100 = rows[440]
    assert first_f100["Registros"] == "F100"
    assert first_f100["Número Documento"] == "DOC-F100-000003"
    assert first_f100["Vlr Documento"] == ""
    assert first_f100["Vlr Mercadoria/Operação"] == "518,25"
    assert first_f100["Vlr Item"] == ""
    assert first_f100["Natureza Crédito"] == "04"

    first_f550 = rows[478]
    assert first_f550["Registros"] == "F550"
    assert first_f550["Vlr Documento"] == ""
    assert first_f550["Vlr Mercadoria/Operação"] == "373,75"
    assert first_f550["Vlr Item"] == ""
    assert first_f550["CFOP"] == "5102"
    assert first_f550["Débito/Crédito"] == ""


def test_maps_official_a100_a170_and_c100_c170(tmp_path: Path) -> None:
    source = tmp_path / "official.txt"
    output = tmp_path / "official.csv"
    text = "".join(
        [
            sped_line(
                "0000",
                "006",
                "1",
                "",
                "",
                "01082026",
                "31082026",
                "EMPRESA",
                "12ABC34501DE67",
                "SP",
                "3550308",
                "",
                "00",
                "0",
            ),
            sped_line(
                "0150",
                "P1",
                "FORNECEDOR AÇÃO",
                "01058",
                "00123456000199",
                "",
                "",
                "3550308",
                "",
                "RUA A",
                "1",
                "",
                "CENTRO",
            ),
            sped_line(
                "0200",
                "I1",
                "ITEM OFICIAL",
                "789",
                "",
                "UN",
                "00",
                "12345678",
                "",
                "",
                "0101",
                "18,00",
                "",
            ),
            sped_line("A010", "98ABC76501DE43"),
            sped_line(
                "A100",
                "0",
                "1",
                "P1",
                "00",
                "S1",
                "",
                "123",
                "NFS-KEY",
                "01082026",
                "02082026",
                "100,00",
                "0",
                "5,00",
                "100,00",
                "1,65",
                "100,00",
                "7,60",
                "0,00",
                "0,00",
                "2,00",
            ),
            sped_line(
                "A170",
                "1",
                "I1",
                "SERVIÇO",
                "100,00",
                "5,00",
                "",
                "",
                "50",
                "100,00",
                "1,6500",
                "1,65",
                "50",
                "100,00",
                "7,6000",
                "7,60",
                "CTA_A",
                "CC1",
            ),
            sped_line("A990", "4"),
            sped_line("C010", "98ABC76501DE43", "2"),
            sped_line(
                "C100",
                "1",
                "0",
                "P1",
                "55",
                "00",
                "1",
                "456",
                "35260812345678000199550010000004561000004567",
                "03082026",
                "04082026",
                "100,00",
                "0",
                "5,00",
                "0,00",
                "95,00",
                "0",
                "2,00",
                "1,00",
                "0,50",
                "90,00",
                "16,20",
                "10,00",
                "1,80",
                "4,50",
                "1,49",
                "6,84",
                "0,00",
                "0,00",
            ),
            sped_line(
                "C170",
                "1",
                "I1",
                "PRODUTO",
                "2,000",
                "UN",
                "100,00",
                "5,00",
                "0",
                "060",
                "5102",
                "VENDA",
                "90,00",
                "18,00",
                "16,20",
                "10,00",
                "18,00",
                "1,80",
                "0",
                "50",
                "999",
                "90,00",
                "5,00",
                "4,50",
                "01",
                "90,00",
                "1,6500",
                "2,000",
                "0,5000",
                "1,49",
                "01",
                "90,00",
                "7,6000",
                "2,000",
                "2,3000",
                "6,84",
                "CTA_C",
            ),
            sped_line("C990", "4"),
        ]
    )
    source.write_bytes(text.encode("latin-1"))

    result = convert_file(source, output)
    rows = read_csv(output)

    assert result.input_encoding == "latin-1"
    assert result.rows == 2
    assert rows[0]["CNPJ"] == "98ABC76501DE43"
    assert rows[0]["Nome Participante"] == "FORNECEDOR AÇÃO"
    assert rows[0]["Número Documento"] == "123"
    assert rows[0]["CFOP"] == ""
    assert rows[0]["Vlr Frete"] == ""
    assert rows[0]["CST PIS"] == "50"

    c_row = rows[1]
    assert c_row["CST ICMS"] == "060"
    assert c_row["Vlr Base Cálculo ICMS"] == "90,00"
    assert c_row["CST IPI"] == "50"
    assert c_row["Vlr IPI"] == "4,50"
    assert c_row["Qtde Base Cálculo PIS"] == "2,000"
    assert c_row["Qtde Alíquota PIS"] == "0,5000"
    assert c_row["Conta Contábil"] == "CTA_C"


def test_consolidates_all_other_operational_record_pairs(tmp_path: Path) -> None:
    output = tmp_path / "other-pairs.csv"

    result = convert_file(OTHER_PAIRS_SAMPLE, output)
    rows = read_csv(output)
    expected = set(SUPPORTED_OUTPUTS) - {
        "A100/A170",
        "C100/C170",
        "F100",
        "F550",
    }

    assert result.rows == len(expected) == 17
    assert {row["Registros"] for row in rows} == expected
    assert all(result.by_record[name] == 1 for name in expected)

    by_record = {row["Registros"]: row for row in rows}
    assert by_record["C100/C175"]["Número Documento"] == "100"
    assert by_record["C100/C175"]["CFOP"] == "5102"
    assert by_record["C180/C181/C185"]["Código Item"] == "I1"
    assert by_record["C180/C181/C185"]["Vlr PIS"] == "1,65"
    assert by_record["C180/C181/C185"]["Vlr Cofins"] == "7,60"
    assert by_record["C190/C191/C195"]["Tipo Operação"] == "0"
    assert by_record["C400/C405/C481/C485"]["Série"] == "ECF001"
    assert by_record["C800/C820"]["Qtde Base Cálculo PIS"] == "10,000"
    assert by_record["C860/C880"]["Número Documento"] == "11-20"
    assert by_record["D100/D101/D105"]["Número Documento"] == "500"
    assert by_record["D200/D201/D205"]["CFOP"] == "5353"
    assert by_record["D600/D601/D605"]["Código Serviço"] == "0101"


def test_rejects_orphan_child(tmp_path: Path) -> None:
    source = tmp_path / "orphan.txt"
    output = tmp_path / "orphan.csv"
    source.write_text(
        sped_line(
            "A170",
            "1",
            "I1",
            "X",
            "1,00",
            "0,00",
            "01",
            "0",
            "50",
            "1,00",
            "1,65",
            "0,02",
            "50",
            "1,00",
            "7,60",
            "0,08",
            "CTA",
            "CC",
        ),
        encoding="ascii",
    )

    with pytest.raises(EFDParseError, match="A170 sem um A100"):
        convert_file(source, output)


def test_maps_official_f100_and_f550(tmp_path: Path) -> None:
    source = tmp_path / "official-f.txt"
    output = tmp_path / "official-f.csv"
    text = "".join(
        [
            sped_line(
                "0000",
                "006",
                "0",
                "",
                "",
                "01082026",
                "31082026",
                "EMPRESA",
                "12345678000199",
                "SP",
                "3550308",
                "",
                "00",
                "0",
            ),
            sped_line(
                "0150",
                "P1",
                "PARTICIPANTE",
                "01058",
                "00999999000188",
                "",
                "",
                "3304557",
                "",
                "RUA A",
                "1",
                "",
                "CENTRO",
            ),
            sped_line(
                "0200",
                "I1",
                "ITEM F",
                "",
                "",
                "UN",
                "09",
                "",
                "",
                "",
                "3101",
                "",
                "",
            ),
            sped_line("F010", "12ABC34501DE67"),
            sped_line(
                "F100",
                "1",
                "P1",
                "I1",
                "01082026",
                "100,00",
                "50",
                "100,00",
                "1,6500",
                "1,65",
                "50",
                "100,00",
                "7,6000",
                "7,60",
                "",
                "",
                "CTA_F",
                "CC_F",
                "OPERAÇÃO F100",
            ),
            sped_line(
                "F550",
                "200,00",
                "01",
                "0,00",
                "200,00",
                "1,6500",
                "3,30",
                "01",
                "0,00",
                "200,00",
                "7,6000",
                "15,20",
                "55",
                "5102",
                "CTA_550",
                "CONSOLIDAÇÃO",
            ),
        ]
    )
    source.write_bytes(text.encode("latin-1"))

    result = convert_file(source, output)
    rows = read_csv(output)

    assert result.by_record == record_counts(F100=1, F550=1)
    assert rows[0]["CNPJ"] == "12ABC34501DE67"
    assert rows[0]["Código Item"] == "I1"
    assert rows[0]["Código Serviço"] == "3101"
    assert rows[0]["Descrição Complementar"] == "OPERAÇÃO F100"
    assert rows[0]["Natureza Crédito"] == ""
    assert rows[0]["Conta Contábil"] == "CTA_F"
    assert rows[0]["Vlr Documento"] == ""
    assert rows[0]["Vlr Mercadoria/Operação"] == "100,00"
    assert rows[0]["Vlr Item"] == "100,00"
    assert rows[0]["Débito/Crédito"] == "Débito"
    assert rows[1]["Registros"] == "F550"
    assert rows[1]["CFOP"] == "5102"
    assert rows[1]["Vlr Cofins"] == "15,20"


def test_detects_compact_f100_by_field_count(tmp_path: Path) -> None:
    source = tmp_path / "compact-f100.txt"
    output = tmp_path / "compact-f100.csv"
    source.write_text(
        "".join(
            [
                sped_line(
                    "0000",
                    "006",
                    "0",
                    "01082026",
                    "31082026",
                    "EMPRESA",
                    "12345678000199",
                    "SP",
                ),
                sped_line(
                    "F100",
                    "1",
                    "",
                    "RECEITA COMPACTA",
                    "01082026",
                    "31",
                    "10",
                    "0",
                    "01",
                    "10,00",
                    "1,6500",
                    "0,17",
                    "01",
                    "10,00",
                    "7,6000",
                    "0,76",
                    "",
                    "CTA",
                    "DOC-1",
                    "",
                ),
            ]
        ),
        encoding="ascii",
    )

    result = convert_file(source, output)
    row = read_csv(output)[0]

    assert result.by_record["F100"] == 1
    assert row["Código Serviço"] == "31"
    assert row["Número Documento"] == "DOC-1"
    assert row["Descrição Complementar"] == "RECEITA COMPACTA"
    assert row["Vlr Mercadoria/Operação"] == "10"
    assert row["CST PIS"] == "01"
    assert row["Conta Contábil"] == "CTA"


def test_does_not_pair_across_establishments(tmp_path: Path) -> None:
    source = tmp_path / "cross-establishment.txt"
    output = tmp_path / "cross-establishment.csv"
    source.write_text(
        "".join(
            [
                sped_line("A010", "11111111000111"),
                sped_line(
                    "A100",
                    "0",
                    "1",
                    "P1",
                    "00",
                    "1",
                    "DOC",
                    "KEY",
                    "01082026",
                    "01082026",
                    "10,00",
                    "0,00",
                    "10,00",
                    "0,17",
                    "10,00",
                    "0,76",
                    "0,00",
                    "0,00",
                    "0,00",
                ),
                sped_line("A010", "22222222000122"),
                sped_line(
                    "A170",
                    "1",
                    "I1",
                    "ITEM",
                    "10,00",
                    "0,00",
                    "1201",
                    "01",
                    "10,00",
                    "1,6500",
                    "0,17",
                    "01",
                    "10,00",
                    "7,6000",
                    "0,76",
                    "0",
                    "",
                    "CTA",
                    "5933",
                ),
            ]
        ),
        encoding="ascii",
    )

    with pytest.raises(EFDParseError, match="A170 sem um A100"):
        convert_file(source, output)


def test_rejects_unknown_supported_record_shape(tmp_path: Path) -> None:
    source = tmp_path / "bad-shape.txt"
    output = tmp_path / "bad-shape.csv"
    source.write_text(sped_line("A100", "0", "1"), encoding="ascii")

    with pytest.raises(EFDParseError, match="A100 possui 3 campos"):
        convert_file(source, output)


def test_rejects_icms_file_as_contributions(tmp_path: Path) -> None:
    output = tmp_path / "wrong-type.csv"

    with pytest.raises(EFDParseError, match="não foi identificado como uma EFD Contribuições"):
        convert_file(ICMS_SAMPLE, output)


def test_reports_zero_for_groups_not_filled(tmp_path: Path) -> None:
    source = tmp_path / "without-scope-records.txt"
    output = tmp_path / "without-scope-records.csv"
    source.write_text(
        "".join(
            [
                sped_line(
                    "0000",
                    "006",
                    "0",
                    "01082026",
                    "31082026",
                    "EMPRESA",
                    "12345678000199",
                    "SP",
                ),
                sped_line(
                    "A100",
                    "0",
                    "1",
                    "P1",
                    "02",
                    "1",
                    "CANCELADA",
                    "",
                    "01082026",
                    "",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                    "0,00",
                ),
                sped_line("F001", "1"),
                sped_line("F990", "2"),
                sped_line("9999", "4"),
            ]
        ),
        encoding="ascii",
    )

    result = convert_file(source, output)

    assert result.rows == 0
    assert result.period == "01/08/2026 a 31/08/2026"
    assert result.by_record == record_counts()
    with output.open(encoding="utf-8-sig", newline="") as stream:
        reader = csv.reader(stream, delimiter=";")
        assert next(reader) == list(COLUMNS)
        assert list(reader) == []


def test_cli_creates_csv_and_reports_scope(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    output = tmp_path / "cli.csv"
    indicators = tmp_path / "cli_indicadores.csv"

    exit_code = main([str(SAMPLE), "--saida", str(output)])

    message = capsys.readouterr().out
    assert exit_code == 0
    assert output.is_file()
    assert indicators.is_file()
    assert "período=01/08/2026 a 31/08/2026" in message
    assert "A100/A170=200" in message
    assert "C100/C170=240" in message
    assert "F100=38" in message
    assert "F550=133" in message
    assert "Indicadores criados:" in message
    assert "Receita de venda para serviço=50" in message
    assert "Receita de venda para produto=192" in message
    assert "Receitas financeiras=0" in message
    assert "Outras receitas=35" in message
