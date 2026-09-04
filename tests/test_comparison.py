from __future__ import annotations

import csv
from pathlib import Path

import pytest

from efd_contribuicoes_csv.comparison import (
    COMPARISON_COLUMNS,
    EFDComparisonError,
    compare_efd_files,
)
from efd_contribuicoes_csv.comparison_cli import main
from efd_contribuicoes_csv.synthetic_icms import generate_synthetic_icms

PROJECT_ROOT = Path(__file__).parents[1]
SAMPLE = PROJECT_ROOT / "efd_contribuicoes_sintetico_1000_linhas.txt"


def sped_line(*fields: str) -> str:
    return f"|{'|'.join(fields)}|\n"


def c100_line(
    number: str,
    key: str,
    amount: str,
    *,
    participant: str = "P1",
    model: str = "55",
) -> str:
    fields = [
        "C100",
        "1",
        "0",
        participant,
        model,
        "00",
        "1",
        number,
        key,
        "01082026",
        "01082026",
        amount,
        "0",
        "0,00",
        "0,00",
        amount,
        "9",
        *("0,00" for _ in range(12)),
    ]
    assert len(fields) == 29
    return sped_line(*fields)


def contribution_header(cnpj: str = "12345678000199") -> str:
    return sped_line(
        "0000",
        "006",
        "0",
        "01082026",
        "31082026",
        "EMPRESA",
        cnpj,
        "SP",
    ) + sped_line("C010", cnpj, "2")


def icms_header(cnpj: str = "12345678000199") -> str:
    return sped_line(
        "0000",
        "020",
        "0",
        "01082026",
        "31082026",
        "EMPRESA",
        cnpj,
        "",
        "SP",
        "123456789",
        "3550308",
        "",
        "",
        "A",
        "1",
    )


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def participant_line(code: str, cnpj: str) -> str:
    return sped_line("0150", code, "PARTICIPANTE", "01058", cnpj)


def test_compares_distinct_invoices_and_reports_duplicates(tmp_path: Path) -> None:
    contribution = tmp_path / "contribution.txt"
    icms = tmp_path / "icms.txt"
    output = tmp_path / "comparison.csv"
    keys = {name: digit * 44 for name, digit in zip("ABCDE", "12345")}
    contribution.write_text(
        contribution_header()
        + c100_line("1", keys["A"], "100,00")
        + c100_line("2", keys["B"], "200,00")
        + c100_line("3", keys["C"], "300,00")
        + c100_line("5", keys["E"], "500,00")
        + c100_line("5", keys["E"], "500,00"),
        encoding="ascii",
    )
    icms.write_text(
        icms_header()
        + c100_line("1", keys["A"], "100,00")
        + c100_line("2", keys["B"], "201,00")
        + c100_line("4", keys["D"], "400,00")
        + c100_line("5", keys["E"], "500,00"),
        encoding="ascii",
    )

    result = compare_efd_files(contribution, icms, output)
    rows = read_csv(output)
    by_key = {row["Chave NF-e"]: row for row in rows}

    assert tuple(rows[0]) == COMPARISON_COLUMNS
    assert result.rows == 5
    assert result.contribution_notes == 5
    assert result.icms_notes == 4
    assert result.by_status == {
        "CONFERENTE": 1,
        "DIVERGENTE": 1,
        "SOMENTE_EFD_CONTRIBUICOES": 1,
        "SOMENTE_EFD_ICMS": 1,
        "DUPLICADA_EFD_CONTRIBUICOES": 1,
        "DUPLICADA_EFD_ICMS": 0,
        "DUPLICADA_AMBAS": 0,
    }
    assert by_key[keys["A"]]["Status"] == "CONFERENTE"
    assert by_key[keys["B"]]["Status"] == "DIVERGENTE"
    assert by_key[keys["B"]]["Divergências"] == "Valor Documento"
    assert by_key[keys["C"]]["Status"] == "SOMENTE_EFD_CONTRIBUICOES"
    assert by_key[keys["D"]]["Status"] == "SOMENTE_EFD_ICMS"
    assert by_key[keys["E"]]["Status"] == "DUPLICADA_EFD_CONTRIBUICOES"
    assert by_key[keys["E"]]["Quantidade EFD Contribuições"] == "2"


def test_matches_non_electronic_invoice_without_key(tmp_path: Path) -> None:
    contribution = tmp_path / "contribution.txt"
    icms = tmp_path / "icms.txt"
    output = tmp_path / "comparison.csv"
    contribution.write_text(
        contribution_header()
        + participant_line("PART-CONTRIB", "00999999000188")
        + c100_line("10", "", "50,00", participant="PART-CONTRIB", model="01"),
        encoding="ascii",
    )
    icms.write_text(
        icms_header()
        + participant_line("PART-ICMS", "00999999000188")
        + c100_line("10", "", "50,00", participant="PART-ICMS", model="01"),
        encoding="ascii",
    )

    result = compare_efd_files(contribution, icms, output)

    assert result.by_status["CONFERENTE"] == 1


def test_does_not_match_non_electronic_documents_from_different_participants(
    tmp_path: Path,
) -> None:
    contribution = tmp_path / "contribution.txt"
    icms = tmp_path / "icms.txt"
    output = tmp_path / "comparison.csv"
    contribution.write_text(
        contribution_header()
        + participant_line("P1", "00111111000111")
        + c100_line("10", "", "50,00", participant="P1", model="01"),
        encoding="ascii",
    )
    icms.write_text(
        icms_header()
        + participant_line("P2", "00222222000122")
        + c100_line("10", "", "50,00", participant="P2", model="01"),
        encoding="ascii",
    )

    result = compare_efd_files(contribution, icms, output)

    assert result.by_status["CONFERENTE"] == 0
    assert result.by_status["SOMENTE_EFD_CONTRIBUICOES"] == 1
    assert result.by_status["SOMENTE_EFD_ICMS"] == 1


def test_rejects_icms_c100_outside_official_shape(tmp_path: Path) -> None:
    contribution = tmp_path / "contribution.txt"
    icms = tmp_path / "icms.txt"
    output = tmp_path / "comparison.csv"
    contribution.write_text(contribution_header(), encoding="ascii")
    malformed = c100_line("1", "1" * 44, "10,00").replace("|0,00|\n", "|\n", 1)
    icms.write_text(icms_header() + malformed, encoding="ascii")

    with pytest.raises(EFDComparisonError, match="C100 da EFD ICMS/IPI possui"):
        compare_efd_files(contribution, icms, output)


def test_generates_real_c100_shape_and_compares_sample(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    icms = tmp_path / "icms.txt"
    output = tmp_path / "comparison.csv"

    generated = generate_synthetic_icms(SAMPLE, icms)
    exit_code = main([str(SAMPLE), str(icms), "--saida", str(output)])
    message = capsys.readouterr().out
    c100_lengths: list[int] = []
    c190_lengths: list[int] = []
    for line in icms.read_text(encoding="utf-8").splitlines():
        fields = line.split("|")[1:-1]
        if fields[0] == "C100":
            c100_lengths.append(len(fields))
        elif fields[0] == "C190":
            c190_lengths.append(len(fields))

    result = compare_efd_files(SAMPLE, icms, output)

    assert generated.c100_records == 119
    assert len(c100_lengths) == 119
    assert set(c100_lengths) == {29}
    assert len(c190_lengths) == 119
    assert set(c190_lengths) == {12}
    assert exit_code == 0
    assert "Comparação criada:" in message
    assert result.rows == 121
    assert result.by_status == {
        "CONFERENTE": 117,
        "DIVERGENTE": 1,
        "SOMENTE_EFD_CONTRIBUICOES": 2,
        "SOMENTE_EFD_ICMS": 1,
        "DUPLICADA_EFD_CONTRIBUICOES": 0,
        "DUPLICADA_EFD_ICMS": 0,
        "DUPLICADA_AMBAS": 0,
    }
