from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .comparison import EFDComparisonError, _FileData, _read_file, _Record


@dataclass(frozen=True)
class SyntheticICMSResult:
    output_path: Path
    c100_records: int
    matching_records: int
    divergent_records: int
    only_contribution_records: int
    only_icms_records: int


def _line(*fields: str) -> str:
    return f"|{'|'.join(fields)}|"


def _format_decimal(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):.2f}".replace(".", ",")


def _decimal(value: str) -> Decimal:
    normalized = value.replace(".", "").replace(",", ".")
    return Decimal(normalized)


def _nfe_key(cnpj: str, number: int) -> str:
    base = f"35{2608:04d}{cnpj}55{1:03d}{number:09d}1{12345678:08d}"
    total = 0
    weight = 2
    for digit in reversed(base):
        total += int(digit) * weight
        weight = 2 if weight == 9 else weight + 1
    check_digit = 11 - (total % 11)
    if check_digit >= 10:
        check_digit = 0
    return f"{base}{check_digit}"


def _official_participant(record: _Record) -> str:
    return _line(
        "0150",
        record.get(2),
        record.get(3),
        record.get(4) or "01058",
        record.get(5),
        record.get(6),
        record.get(7),
        record.get(8) or "3550308",
        "",
        "RUA SINTETICA",
        "100",
        "",
        "CENTRO",
    )


def _c100_and_cfop(data: _FileData) -> list[tuple[_Record, str]]:
    documents: list[tuple[_Record, str]] = []
    current: _Record | None = None
    current_cfop = ""
    for record in data.records:
        if record.code == "C100":
            if current is not None:
                documents.append((current, current_cfop))
            current = record
            current_cfop = ""
        elif record.code == "C170" and current is not None and not current_cfop:
            current_cfop = record.get(11)
        elif record.code == "C990" and current is not None:
            documents.append((current, current_cfop))
            current = None
            current_cfop = ""
    if current is not None:
        documents.append((current, current_cfop))
    return documents


def _official_c100(record: _Record, *, amount_delta: Decimal = Decimal(0)) -> list[str]:
    fields = list(record.fields)
    if len(fields) not in {28, 29}:
        raise EFDComparisonError(
            f"linha {record.line_number}: C100 da origem possui "
            f"{len(fields)} campos; esperado 28 ou 29"
        )
    while len(fields) < 29:
        fields.append("")
    if amount_delta:
        amount = _decimal(fields[11]) + amount_delta
        fields[11] = _format_decimal(amount)
        if fields[15]:
            fields[15] = _format_decimal(_decimal(fields[15]) + amount_delta)
    return fields


def _c190(cfop: str, amount: str) -> str:
    operation_value = _decimal(amount)
    rate = Decimal(12) if cfop.startswith(("2", "6")) else Decimal(18)
    icms_value = operation_value * rate / Decimal(100)
    return _line(
        "C190",
        "000",
        cfop or "5102",
        _format_decimal(rate),
        _format_decimal(operation_value),
        _format_decimal(operation_value),
        _format_decimal(icms_value),
        "0,00",
        "0,00",
        "0,00",
        "0,00",
        "",
    )


def _block_9(lines: list[str]) -> list[str]:
    record_order = []
    for line in lines:
        code = line.split("|", 2)[1]
        if code not in record_order:
            record_order.append(code)
    record_order.extend(("9001", "9900", "9990", "9999"))
    counts = Counter(line.split("|", 2)[1] for line in lines)
    counts.update({"9001": 1, "9900": len(record_order), "9990": 1, "9999": 1})
    block = [_line("9001", "0")]
    block.extend(_line("9900", code, str(counts[code])) for code in record_order)
    block.append(_line("9990", str(len(block) + 1)))
    block.append(_line("9999", str(len(lines) + len(block) + 1)))
    return block


def generate_synthetic_icms(
    contribution_path: str | Path,
    output_path: str | Path,
) -> SyntheticICMSResult:
    """Cria uma massa ICMS/IPI estrutural para testar a comparação de C100."""

    source = Path(contribution_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if source == target:
        raise ValueError("a EFD ICMS sintética não pode sobrescrever a origem")
    data = _read_file(source)
    documents = _c100_and_cfop(data)
    if len(documents) < 3:
        raise EFDComparisonError("são necessários pelo menos três C100 na origem")

    start_date, end_date = data.period.split(" a ", maxsplit=1)
    lines = [
        _line(
            "0000",
            "020",
            "0",
            start_date,
            end_date,
            "EMPRESA SINTETICA EFD ICMS IPI",
            data.cnpj,
            "",
            "SP",
            "123456789",
            "3550308",
            "",
            "",
            "A",
            "1",
        ),
        _line("0001", "0"),
        _line(
            "0005",
            "EMPRESA SINTETICA",
            "01001000",
            "RUA SINTETICA",
            "100",
            "",
            "CENTRO",
            "11999999999",
            "",
            "fiscal@example.com",
        ),
    ]
    participants = {
        record.get(2): record for record in data.records if record.code == "0150"
    }
    used_participants = {record.get(4) for record, _ in documents[:-2] if record.get(4)}
    lines.extend(
        _official_participant(participants[code])
        for code in sorted(used_participants)
        if code in participants
    )
    lines.append(
        _line(
            "0150",
            "PART-EXCLUSIVO-ICMS",
            "PARTICIPANTE EXCLUSIVO EFD ICMS",
            "01058",
            "99888888000199",
            "",
            "",
            "3550308",
            "",
            "RUA EXCLUSIVA",
            "999",
            "",
            "CENTRO",
        )
    )
    lines.append(_line("0990", str(len(lines) + 1)))

    block_c = [_line("C001", "0")]
    for index, (record, cfop) in enumerate(documents[:-2]):
        fields = _official_c100(
            record,
            amount_delta=Decimal("1.00") if index == 0 else Decimal(0),
        )
        block_c.append(_line(*fields))
        block_c.append(_c190(cfop, fields[11]))

    extra_amount = "999,99"
    extra_c100 = [
        "C100",
        "1",
        "0",
        "PART-EXCLUSIVO-ICMS",
        "55",
        "00",
        "1",
        "999999",
        _nfe_key(data.cnpj, 999999),
        end_date,
        end_date,
        extra_amount,
        "0",
        "0,00",
        "0,00",
        extra_amount,
        "9",
        *("0,00" for _ in range(12)),
    ]
    block_c.append(_line(*extra_c100))
    block_c.append(_c190("5102", extra_amount))
    block_c.append(_line("C990", str(len(block_c) + 1)))
    lines.extend(block_c)
    lines.extend(_block_9(lines))

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return SyntheticICMSResult(
        target,
        c100_records=len(documents) - 1,
        matching_records=len(documents) - 3,
        divergent_records=1,
        only_contribution_records=2,
        only_icms_records=1,
    )
