from pathlib import Path

import pytest

from efd_contribuicoes_csv.comparison import EFDComparisonError, _read_file
from efd_contribuicoes_csv.converter import EFDParseError, _parse_records


@pytest.mark.parametrize("code", ["Cyž¬", "DXVê\x00abc", "Ftexto", "C10", "c100"])
def test_invalid_record_code_is_rejected_by_both_readers(tmp_path: Path, code: str) -> None:
    text = f"|0000|006|\r\n|{code}|conteúdo|\r\n"
    path = tmp_path / "entrada.txt"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(EFDParseError, match="linha 2: código de registro inválido"):
        _parse_records(text)
    with pytest.raises(EFDComparisonError, match="entrada.txt, linha 2: código de registro inválido"):
        _read_file(path)


@pytest.mark.parametrize("control", ["\x0b", "\x0c", "\x1c", "\x1d", "\x1e", "\x85"])
def test_controls_inside_fields_do_not_create_fake_records(tmp_path: Path, control: str) -> None:
    text = f"|0000|006|0|01012024|31012024|EMPRESA|12345678000199|\r\n|0999|Descrição{control}DXtexto|\r\n|9999|3|\r\n"
    path = tmp_path / "entrada.txt"
    path.write_text(text, encoding="utf-8")
    for records in (_parse_records(text), _read_file(path).records):
        assert [record.line_number for record in records] == [1, 2, 3]
        assert records[1].fields == ("0999", f"Descrição{control}DXtexto")
