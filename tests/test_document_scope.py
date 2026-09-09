"""Casos sintéticos com posições dos guias; independentes do mapa de produção."""
import csv
from pathlib import Path

import pytest

from efd_contribuicoes_csv.comparison import compare_efd_files, EFDComparisonError
from efd_contribuicoes_csv.workflow import process_annual_efd_input, discover_annual_efd_input

CNPJ = "12345678000199"
PARTNER = "00999999000188"
KEY = "1" * 44


def record(code: str, size: int, **values: str) -> str:
    fields = [code] + [""] * (size - 1)
    for position, value in values.items():
        fields[int(position[1:]) - 1] = value
    return "|" + "|".join(fields) + "|\n"


def header(contribution: bool) -> str:
    opening = record("0000", 8 if contribution else 15,
                     p2="006" if contribution else "020", p3="0", p4="01082026",
                     p5="31082026", p6="EMPRESA", p7=CNPJ)
    return opening + (record("C010", 3, p2=CNPJ) if contribution else "") + record("0150", 13, p2="P1", p5=PARTNER)


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream, delimiter=";"))


def compare(tmp_path: Path, contribution: str, icms: str):
    left, right, output = (tmp_path / name for name in ("contribution.txt", "icms.txt", "comparison.csv"))
    left.write_text(header(True) + contribution, encoding="utf-8")
    right.write_text(header(False) + icms, encoding="utf-8")
    result = compare_efd_files(left, right, output)
    return result, read_rows(output)


def c100(key: str = KEY, operation: str = "1", model: str = "55") -> str:
    return record("C100", 29, p2=operation, p3="0" if operation == "1" else "1",
                  p4="P1", p5=model, p6="00", p7="1", p8="10", p9=key,
                  p10="01082026", p11="01082026", p12="100,00")


@pytest.mark.parametrize("code,left,right", [
    ("D100", record("D100", 23, p2="0", p3="1", p4="P1", p5="57", p6="00", p7="1", p9="10", p10=KEY, p11="01082026", p12="01082026", p15="100,00"),
     record("D100", 25, p2="0", p3="1", p4="P1", p5="57", p6="00", p7="1", p9="10", p10=KEY, p11="01082026", p12="01082026", p15="100,00")),
    ("C500", record("C500", 15, p2="P1", p3="66", p4="00", p5="1", p7="10", p8="01082026", p9="01082026", p10="100,00", p15=KEY),
     record("C500", 40, p2="0", p3="1", p4="P1", p5="66", p6="00", p7="1", p10="10", p11="01082026", p12="01082026", p13="100,00", p28=KEY)),
    ("D500", record("D500", 22, p2="0", p3="1", p4="P1", p5="21", p6="00", p7="1", p9="10", p10="01082026", p11="01082026", p12="100,00"),
     record("D500", 24, p2="0", p3="1", p4="P1", p5="21", p6="00", p7="1", p9="10", p10="01082026", p11="01082026", p12="100,00")),
    ("C800", record("C800", 17, p2="59", p3="00", p4="10", p5="01082026", p6="100,00", p9=PARTNER, p10="123", p11=KEY),
     record("C800", 17, p2="59", p3="00", p4="10", p5="01082026", p6="100,00", p9=PARTNER, p10="123", p11=KEY)),
])
def test_matches_additional_individual_documents(tmp_path: Path, code: str, left: str, right: str) -> None:
    result, rows = compare(tmp_path, left, right)
    assert result.icms_notes == result.contribution_notes == 1
    assert result.by_status["CONFERENTE"] == 1
    assert rows[0]["Registros EFD ICMS"] == code
    assert rows[0]["Presença EFD Contribuições"] == "PRESENTE"
    assert rows[0]["Valor Documento EFD ICMS"] == "100,00"
    _, missing = compare(tmp_path, "", right)
    assert missing[0]["Presença EFD Contribuições"] == "NAO_LOCALIZADA"


@pytest.mark.parametrize("code,document", [
    ("C350", record("C350", 12, p2="1", p4="10", p5="01082026", p6=PARTNER, p8="100,00")),
    ("C460", record("C400", 5, p2="2D", p4="ECF123") + record("C460", 10, p2="2D", p3="00", p4="10", p5="01082026", p6="100,00")),
    ("B020", record("B020", 21, p2="1", p3="0", p4="P1", p5="03", p6="00", p7="1", p8="10", p10="01082026", p12="100,00")),
    ("D700", record("D700", 32, p2="0", p3="1", p4="P1", p5="62", p6="00", p7="1", p8="10", p9="01082026", p10="01082026", p11="100,00", p22=KEY)),
])
def test_reports_missing_documents_previously_ignored(tmp_path: Path, code: str, document: str) -> None:
    result, rows = compare(tmp_path, "", document)
    assert result.icms_notes == 1
    assert rows[0]["Registros EFD ICMS"] == code
    assert rows[0]["Presença EFD Contribuições"] == "NAO_LOCALIZADA"
    assert rows[0]["Arquivo EFD ICMS"] == "icms.txt"


def test_matches_energy_record_to_c100_by_key(tmp_path: Path) -> None:
    left = record("C500", 15, p2="P1", p3="55", p4="00", p5="1", p7="10", p8="01082026", p9="01082026", p10="100,00", p15=KEY)
    result, rows = compare(tmp_path, left, c100(operation="0"))
    assert result.by_status["CONFERENTE"] == 1
    assert rows[0]["Registros EFD Contribuições"] == "C500"


def test_matches_c395_without_key_to_c100_and_normalizes_numbers(tmp_path: Path) -> None:
    left = record("C395", 8, p2="65", p3="P1", p4="001", p6="000010", p7="01082026", p8="100,00")
    result, rows = compare(tmp_path, left, c100(operation="0", model="65"))
    assert result.by_status["CONFERENTE"] == 1
    assert rows[0]["Critério de Conferência"] == "IDENTIFICAÇÃO DOCUMENTAL"
    assert rows[0]["Chave NF-e"] == KEY
    assert rows[0]["Chave EFD Contribuições"] == ""
    assert rows[0]["Chave EFD ICMS"] == KEY


@pytest.mark.parametrize("key", [KEY, ""])
@pytest.mark.parametrize("left_series,right_series,status", [
    ("1", "001", "CONFERENTE"),
    ("001", "1", "CONFERENTE"),
    ("0", "000", "CONFERENTE"),
    ("1", "002", "DIVERGENTE"),
])
def test_c100_series_leading_zeros(
    tmp_path: Path, key: str, left_series: str, right_series: str, status: str,
) -> None:
    def document(series: str) -> str:
        fields = c100(key=key).strip().split("|")
        fields[7] = series
        return "|".join(fields) + "\n"

    result, rows = compare(tmp_path, document(left_series), document(right_series))
    if status == "DIVERGENTE" and not key:
        # Séries diferentes sem chave não identificam o mesmo documento.
        assert result.by_status["CONFERENTE"] == 0
        assert len(rows) == 2
        return
    assert len(rows) == 1
    assert result.by_status[status] == 1
    assert rows[0]["Série EFD Contribuições"] == left_series
    assert rows[0]["Série EFD ICMS"] == right_series
    assert rows[0]["Divergências"] == ("Série" if status == "DIVERGENTE" else "")


def test_matches_service_in_block_b_to_a100(tmp_path: Path) -> None:
    left = record("A100", 21, p2="1", p3="0", p4="P1", p5="00", p6="1", p8="10", p10="01082026", p12="100,00")
    right = record("B020", 21, p2="1", p3="0", p4="P1", p5="03", p6="00", p7="1", p8="10", p10="01082026", p12="100,00")
    result, _ = compare(tmp_path, left, right)
    assert result.by_status["CONFERENTE"] == 1


def test_c465_is_key_complement_not_another_note(tmp_path: Path) -> None:
    right = record("C400", 5, p2="60", p4="ECF123") + record("C460", 10, p2="60", p3="00", p4="10", p5="01082026", p6="100,00") + record("C465", 3, p2=KEY)
    result, rows = compare(tmp_path, "", right)
    assert result.icms_notes == 1
    assert rows[0]["Chave NF-e"] == KEY


@pytest.mark.parametrize("summary", [
    record("C180", 8, p2="55", p3="01082026", p4="31082026", p5="ITEM", p8="100,00"),
    record("F550", 16, p2="100,00", p13="55"),
    record("F100", 19, p2="1", p3="P1", p5="01082026"),
])
def test_consolidation_is_not_proof_of_presence_or_absence(tmp_path: Path, summary: str) -> None:
    result, rows = compare(tmp_path, summary, c100())
    assert result.by_status["REVISAO_NECESSARIA"] == 1
    assert rows[0]["Presença EFD Contribuições"] == "INCONCLUSIVA"
    assert "linha" in rows[0]["Evidências EFD Contribuições"]


@pytest.mark.parametrize("summary", [
    record("C180", 8, p2="65", p3="01082026", p4="31082026"),
    record("C180", 8, p2="55", p3="02082026", p4="31082026"),
    record("C010", 3, p2="12345678000270") + record("C180", 8, p2="55", p3="01082026", p4="31082026"),
])
def test_unrelated_consolidation_does_not_hide_missing_note(tmp_path: Path, summary: str) -> None:
    _, rows = compare(tmp_path, summary, c100())
    assert rows[0]["Presença EFD Contribuições"] == "NAO_LOCALIZADA"


def test_icms_summary_and_unknown_record_are_visible_in_review(tmp_path: Path) -> None:
    result, rows = compare(tmp_path, "", record("C860", 6, p2="59", p3="123", p4="01082026", p5="1", p6="10") + record("C999", 2, p2="novo"))
    assert result.icms_notes == 0
    assert len(rows) == 2
    assert all(row["Presença EFD Contribuições"] == "INCONCLUSIVA" for row in rows)
    assert {row["Tratamento"] for row in result.coverage if row["Origem"] == "EFD ICMS/IPI"} == {"SEM IDENTIFICAÇÃO INDIVIDUAL", "NÃO MAPEADO"}


def test_unknown_contribution_record_blocks_false_absence(tmp_path: Path) -> None:
    _, rows = compare(tmp_path, record("C999", 2), c100())
    note = next(row for row in rows if row["Chave NF-e"] == KEY)
    assert note["Presença EFD Contribuições"] == "INCONCLUSIVA"


def test_referenced_invoice_is_not_counted_as_another_invoice(tmp_path: Path) -> None:
    result, rows = compare(tmp_path, "", c100() + record("C113", 10, p10="2" * 44))
    assert result.icms_notes == len(rows) == 1


def test_distinct_keys_with_same_document_identity_need_review(tmp_path: Path) -> None:
    _, rows = compare(tmp_path, c100("2" * 44), c100())
    note = next(row for row in rows if row["Registros EFD ICMS"])
    assert note["Presença EFD Contribuições"] == "INCONCLUSIVA"


def test_insufficient_identification_does_not_merge_notes(tmp_path: Path) -> None:
    document = record("D500", 24, p2="0", p3="1", p5="21", p9="10", p10="01082026")
    result, rows = compare(tmp_path, "", document + document)
    assert result.icms_notes == len(rows) == 2
    assert all(row["Presença EFD Contribuições"] == "INCONCLUSIVA" for row in rows)


def test_rejects_malformed_additional_document(tmp_path: Path) -> None:
    with pytest.raises(EFDComparisonError, match="C500 da EFD ICMS/IPI possui"):
        compare(tmp_path, "", record("C500", 12))


def test_annual_flow_without_any_contributions_keeps_all_icms_documents(tmp_path: Path) -> None:
    input_path = tmp_path / "entrada"
    (input_path / "efd_contribuicoes").mkdir(parents=True)
    (input_path / "efd_icms").mkdir()
    (input_path / "efd_icms" / "agosto.txt").write_text(header(False) + c100())
    result = process_annual_efd_input(discover_annual_efd_input(input_path), tmp_path / "resultado")
    assert result.missing_notes == 0
    assert result.pending_notes == 1
    assert result.comparison.icms_notes == 1
    assert read_rows(result.pending_notes_path)[0]["Status"] == "SEM_EFD_CONTRIBUICOES"
    assert read_rows(result.coverage_path)


@pytest.mark.parametrize("parent,cancelled", [
    (record("C300", 11, p2="02", p3="1", p5="1", p6="10", p7="01082026"), "C310"),
    (record("C600", 22, p2="06", p4="1", p9="01082026"), "C601"),
    (record("D300", 20, p2="13", p3="1", p5="1", p6="10", p10="01082026"), "D301"),
    (record("D410", 15, p2="13", p3="1", p5="1", p6="10", p7="01082026"), "D411"),
])
def test_cancelled_numbers_are_listed_with_parent_context(tmp_path: Path, parent: str, cancelled: str) -> None:
    result, rows = compare(tmp_path, "", parent + record(cancelled, 2, p2="5"))
    note = next(row for row in rows if row["Registros EFD ICMS"] == cancelled)
    assert result.icms_notes == 1
    assert note["Número Documento EFD ICMS"] == "5"
    assert note["Data Documento EFD ICMS"] == "01082026"
    assert note["Situação EFD ICMS"] == "02"


def test_participant_codes_are_resolved_per_establishment(tmp_path: Path) -> None:
    branch = "12345678000270"
    master = record("0140", 9, p4=CNPJ) + record("0150", 13, p2="P1", p5=PARTNER)
    master += record("0140", 9, p4=branch) + record("0150", 13, p2="P1", p5="00888888000188")
    left = master + record("C010", 3, p2=CNPJ) + c100(operation="0")
    result, _ = compare(tmp_path, left, c100(operation="0"))
    assert result.by_status["CONFERENTE"] == 1


def test_incomplete_contribution_identity_requires_review(tmp_path: Path) -> None:
    left = record("C395", 8, p2="65", p4="1", p6="10", p7="01082026", p8="100,00")
    _, rows = compare(tmp_path, left, c100(operation="0", model="65"))
    note = next(row for row in rows if row["Registros EFD ICMS"])
    assert note["Presença EFD Contribuições"] == "INCONCLUSIVA"


def test_nfse_key_does_not_match_merchandise_key(tmp_path: Path) -> None:
    left = record("A100", 21, p2="1", p3="0", p4="P1", p5="00", p6="1", p8="10", p9=KEY, p10="01082026", p12="100,00")
    result, rows = compare(tmp_path, left, c100())
    assert result.rows == 2
    assert next(row for row in rows if row["Registros EFD ICMS"])["Presença EFD Contribuições"] == "NAO_LOCALIZADA"


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "sNaN"])
def test_non_finite_document_amount_is_rejected(tmp_path: Path, amount: str) -> None:
    with pytest.raises(EFDComparisonError, match="valor monetário inválido"):
        compare(tmp_path, "", c100().replace("100,00", amount))


def test_presence_in_another_month_is_not_reported_as_missing(tmp_path: Path) -> None:
    input_path = tmp_path / "entrada"
    (input_path / "efd_contribuicoes").mkdir(parents=True)
    (input_path / "efd_icms").mkdir()
    september = header(True).replace("01082026", "01092026").replace("31082026", "30092026")
    (input_path / "efd_contribuicoes" / "setembro.txt").write_text(september + c100())
    (input_path / "efd_icms" / "agosto.txt").write_text(header(False) + c100())
    result = process_annual_efd_input(discover_annual_efd_input(input_path), tmp_path / "resultado")
    rows = read_rows(result.comparison.output_path)
    assert result.missing_notes == 0
    assert len(rows) == result.comparison.rows == 1
    assert rows[0]["Presença EFD Contribuições"] == "PRESENTE"
    assert rows[0]["Critério de Conferência"] == "CHAVE EM OUTRO PERÍODO"
    assert rows[0]["Arquivo EFD Contribuições"] == "setembro.txt"
    assert rows[0]["Período EFD Contribuições"] == "01092026 a 30092026"
    assert result.pending_notes == 1
