import csv
from datetime import datetime
from pathlib import Path

import pytest
from openpyxl import load_workbook

from efd_contribuicoes_csv.excel import SHEETS, create_excel_workbook


@pytest.mark.parametrize("date_text", ["01082026", "01/08/2026"])
def test_excel_preserves_text_and_types_dates(tmp_path: Path, date_text: str) -> None:
    for _, filename in SHEETS:
        with (tmp_path / filename).open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Descrição Item", "Código Item", "Data Documento", "Vlr Item"])
            writer.writerow(["=1+1", "#N/A", date_text, "100,50"])
    output = create_excel_workbook(tmp_path, tmp_path / "resultado.xlsx")
    workbook = load_workbook(output)
    try:
        for worksheet in workbook:
            assert worksheet["A2"].data_type == "s"
            assert worksheet["A2"].value == "=1+1"
            assert worksheet["B2"].data_type == "s"
            assert worksheet["B2"].value == "#N/A"
            assert worksheet["C2"].value == datetime(2026, 8, 1)
            assert worksheet["D2"].value == 100.5
    finally:
        workbook.close()


def test_excel_removes_illegal_controls_without_changing_csv(tmp_path: Path) -> None:
    controls = "".join(chr(code) for code in range(32) if code not in (9, 10, 13))
    description = "Descrição" + controls + " válida\tcom\nquebra\rde linha"
    originals = {}
    for _, filename in SHEETS:
        path = tmp_path / filename
        with path.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.writer(stream, delimiter=";")
            writer.writerow(["Descrição Item", "Código Item", "Data Documento", "Vlr Item"])
            writer.writerow([description, "\x00=1+1", "01\x00082026", "100,\x0050"])
        originals[path] = path.read_bytes()

    output = create_excel_workbook(tmp_path, tmp_path / "resultado.xlsx")
    workbook = load_workbook(output)
    try:
        for worksheet in workbook:
            # A leitura do XML pode normalizar o retorno de carro para nova linha.
            assert worksheet["A2"].value.replace("\r", "\n") == "Descrição válida\tcom\nquebra\nde linha"
            assert worksheet["B2"].value == "=1+1"
            assert worksheet["B2"].data_type == "s"
            assert worksheet["C2"].value == datetime(2026, 8, 1)
            assert worksheet["D2"].value == 100.5
    finally:
        workbook.close()
    assert all(path.read_bytes() == content for path, content in originals.items())
