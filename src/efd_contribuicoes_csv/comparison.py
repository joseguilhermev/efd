from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .identifiers import cnpj_root

COMPARISON_COLUMNS = (
    "Status",
    "Identificador",
    "CNPJ",
    "Período EFD Contribuições",
    "Período EFD ICMS",
    "Chave NF-e",
    "Tipo Operação EFD Contribuições",
    "Tipo Operação EFD ICMS",
    "Indicador Emitente EFD Contribuições",
    "Indicador Emitente EFD ICMS",
    "Código Participante EFD Contribuições",
    "Código Participante EFD ICMS",
    "Documento Participante EFD Contribuições",
    "Documento Participante EFD ICMS",
    "Modelo EFD Contribuições",
    "Modelo EFD ICMS",
    "Situação EFD Contribuições",
    "Situação EFD ICMS",
    "Série EFD Contribuições",
    "Série EFD ICMS",
    "Número Documento EFD Contribuições",
    "Número Documento EFD ICMS",
    "Data Documento EFD Contribuições",
    "Data Documento EFD ICMS",
    "Data Entrada/Saída EFD Contribuições",
    "Data Entrada/Saída EFD ICMS",
    "Valor Documento EFD Contribuições",
    "Valor Documento EFD ICMS",
    "Divergências",
    "Linhas EFD Contribuições",
    "Linhas EFD ICMS",
    "Quantidade EFD Contribuições",
    "Quantidade EFD ICMS",
)

STATUSES = (
    "CONFERENTE",
    "DIVERGENTE",
    "SOMENTE_EFD_CONTRIBUICOES",
    "SOMENTE_EFD_ICMS",
    "DUPLICADA_EFD_CONTRIBUICOES",
    "DUPLICADA_EFD_ICMS",
    "DUPLICADA_AMBAS",
)


class EFDComparisonError(ValueError):
    """Erro que impede uma comparação confiável entre as escriturações."""


@dataclass(frozen=True)
class _Record:
    line_number: int
    fields: tuple[str, ...]

    @property
    def code(self) -> str:
        return self.get(1)

    def get(self, position: int) -> str:
        if 1 <= position <= len(self.fields):
            return self.fields[position - 1].strip()
        return ""


@dataclass(frozen=True)
class _FileData:
    cnpj: str
    period: str
    records: tuple[_Record, ...]
    participant_tax_ids: dict[str, str]


@dataclass(frozen=True)
class FiscalNote:
    cnpj: str
    line_number: int
    operation: str
    issuer: str
    participant: str
    participant_tax_id: str
    model: str
    situation: str
    series: str
    number: str
    key: str
    document_date: str
    entry_exit_date: str
    amount: str

    @property
    def identity(self) -> str:
        company = cnpj_root(self.cnpj)
        if self.key:
            return f"{company}|CHV_NFE|{self.key}"
        participant = self.participant_tax_id or self.participant
        return (
            f"{company}|DOC|{participant}|{self.model}|{self.series}|{self.number}"
        )

    @property
    def display_identity(self) -> str:
        if self.key:
            return f"CHV_NFE:{self.key}"
        participant = self.participant_tax_id or self.participant
        return f"DOC:{participant}/{self.model}/{self.series}/{self.number}"


@dataclass(frozen=True)
class ComparisonResult:
    output_path: Path
    rows: int
    contribution_notes: int
    icms_notes: int
    by_status: dict[str, int]
    contribution_period: str
    icms_period: str
    cnpj: str


@dataclass(frozen=True)
class EFDFileInfo:
    path: Path
    cnpj: str
    period: str


def _decode(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise EFDComparisonError(f"não foi possível decodificar o arquivo {path}")


def _read_file(path: Path) -> _FileData:
    records: list[_Record] = []
    for line_number, raw_line in enumerate(_decode(path).splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split("|")
        if fields[0] == "":
            fields = fields[1:]
        if fields and fields[-1] == "":
            fields = fields[:-1]
        if not fields or not fields[0].strip():
            raise EFDComparisonError(
                f"{path.name}, linha {line_number}: registro vazio"
            )
        records.append(_Record(line_number, tuple(fields)))
    if not records:
        raise EFDComparisonError(f"o arquivo {path} está vazio")

    cnpj = ""
    period = ""
    record_0000 = next((record for record in records if record.code == "0000"), None)
    if record_0000 is not None:
        for position in range(2, len(record_0000.fields)):
            start = record_0000.get(position)
            end = record_0000.get(position + 1)
            if re.fullmatch(r"\d{8}", start) and re.fullmatch(r"\d{8}", end):
                period = f"{start} a {end}"
                cnpj = record_0000.get(position + 3)
                break
    if not cnpj:
        raise EFDComparisonError(f"{path.name}: CNPJ não encontrado no registro 0000")
    participant_tax_ids = {
        record.get(2): record.get(5) or record.get(6)
        for record in records
        if record.code == "0150" and record.get(2)
    }
    return _FileData(cnpj, period, tuple(records), participant_tax_ids)


def _validate_file_kind(data: _FileData, *, source: str, filename: str) -> None:
    codes = {record.code for record in data.records}
    contribution_markers = {
        "0110",
        "0145",
        "A010",
        "A100",
        "A170",
        "C010",
        "F010",
        "F100",
        "F550",
        "M001",
        "P001",
    }
    record_0000 = next(record for record in data.records if record.code == "0000")
    if source == "contribution":
        valid = bool(codes & contribution_markers)
        label = "EFD Contribuições"
    else:
        valid = not (codes & contribution_markers) and len(record_0000.fields) >= 15
        label = "EFD ICMS/IPI"
    if not valid:
        raise EFDComparisonError(
            f"{filename}: o arquivo não foi identificado como {label}"
        )


def _notes(data: _FileData, *, source: str) -> list[FiscalNote]:
    notes: list[FiscalNote] = []
    current_cnpj = data.cnpj
    for record in data.records:
        if source == "contribution" and record.code == "C010":
            current_cnpj = record.get(2) or data.cnpj
            continue
        if record.code != "C100":
            continue

        allowed_lengths = {28, 29} if source == "contribution" else {29}
        if len(record.fields) not in allowed_lengths:
            label = "EFD Contribuições" if source == "contribution" else "EFD ICMS/IPI"
            expected = "28 ou 29" if source == "contribution" else "29"
            raise EFDComparisonError(
                f"linha {record.line_number}: C100 da {label} possui "
                f"{len(record.fields)} campos; esperado {expected}"
            )

        note = FiscalNote(
            cnpj=current_cnpj if source == "contribution" else data.cnpj,
            line_number=record.line_number,
            operation=record.get(2),
            issuer=record.get(3),
            participant=record.get(4),
            participant_tax_id=data.participant_tax_ids.get(record.get(4), ""),
            model=record.get(5),
            situation=record.get(6),
            series=record.get(7),
            number=record.get(8),
            key=record.get(9),
            document_date=record.get(10),
            entry_exit_date=record.get(11),
            amount=record.get(12),
        )
        if (
            source == "icms"
            and note.model in {"55", "65"}
            and note.situation != "05"
            and not re.fullmatch(r"\d{44}", note.key)
        ):
            raise EFDComparisonError(
                f"linha {record.line_number}: CHV_NFE do C100 da EFD ICMS/IPI "
                "deve possuir 44 dígitos"
            )
        notes.append(note)
    return notes


def inspect_efd_file(path: str | Path, *, source: str) -> EFDFileInfo:
    """Valida o tipo da EFD e retorna os metadados necessários ao fluxo anual."""

    if source not in {"contribution", "icms"}:
        raise ValueError("a origem da EFD deve ser 'contribution' ou 'icms'")
    resolved = Path(path).expanduser().resolve()
    data = _read_file(resolved)
    _validate_file_kind(data, source=source, filename=resolved.name)
    _notes(data, source=source)
    if not data.period:
        raise EFDComparisonError(
            f"{resolved.name}: período não encontrado no registro 0000"
        )
    return EFDFileInfo(resolved, data.cnpj, data.period)


def _decimal_equal(left: str, right: str) -> bool:
    if not left or not right:
        return left == right

    def parse(value: str) -> Decimal:
        normalized = value.replace(".", "").replace(",", ".") if "," in value else value
        try:
            return Decimal(normalized)
        except InvalidOperation as exc:
            raise EFDComparisonError(f"valor monetário inválido: {value!r}") from exc

    return parse(left) == parse(right)


def _differences(contribution: FiscalNote, icms: FiscalNote) -> list[str]:
    fields = (
        ("Tipo Operação", contribution.operation, icms.operation, False),
        ("Indicador Emitente", contribution.issuer, icms.issuer, False),
        (
            "Documento Participante",
            contribution.participant_tax_id,
            icms.participant_tax_id,
            False,
        ),
        ("Modelo", contribution.model, icms.model, False),
        ("Situação", contribution.situation, icms.situation, False),
        ("Série", contribution.series, icms.series, False),
        ("Número Documento", contribution.number, icms.number, False),
        ("Data Documento", contribution.document_date, icms.document_date, False),
        (
            "Data Entrada/Saída",
            contribution.entry_exit_date,
            icms.entry_exit_date,
            False,
        ),
        ("Valor Documento", contribution.amount, icms.amount, True),
    )
    differences: list[str] = []
    for label, left, right, is_decimal in fields:
        equal = _decimal_equal(left, right) if is_decimal else left == right
        if not equal:
            differences.append(label)
    return differences


def _index(notes: list[FiscalNote]) -> dict[str, list[FiscalNote]]:
    indexed: dict[str, list[FiscalNote]] = defaultdict(list)
    for note in notes:
        indexed[note.identity].append(note)
    return indexed


def _comparison_row(
    contribution_notes: list[FiscalNote],
    icms_notes: list[FiscalNote],
    contribution_period: str,
    icms_period: str,
) -> dict[str, str]:
    contribution = contribution_notes[0] if contribution_notes else None
    icms = icms_notes[0] if icms_notes else None
    reference = contribution or icms
    assert reference is not None

    if len(contribution_notes) > 1 and len(icms_notes) > 1:
        status = "DUPLICADA_AMBAS"
        differences = ["Chave documental duplicada nas duas EFDs"]
    elif len(contribution_notes) > 1:
        status = "DUPLICADA_EFD_CONTRIBUICOES"
        differences = ["Chave documental duplicada na EFD Contribuições"]
    elif len(icms_notes) > 1:
        status = "DUPLICADA_EFD_ICMS"
        differences = ["Chave documental duplicada na EFD ICMS/IPI"]
    elif contribution is None:
        status = "SOMENTE_EFD_ICMS"
        differences = ["Nota ausente na EFD Contribuições"]
    elif icms is None:
        status = "SOMENTE_EFD_CONTRIBUICOES"
        differences = ["Nota ausente na EFD ICMS/IPI"]
    else:
        differences = _differences(contribution, icms)
        status = "DIVERGENTE" if differences else "CONFERENTE"

    def value(note: FiscalNote | None, attribute: str) -> str:
        return str(getattr(note, attribute)) if note is not None else ""

    return {
        "Status": status,
        "Identificador": reference.display_identity,
        "CNPJ": reference.cnpj,
        "Período EFD Contribuições": contribution_period,
        "Período EFD ICMS": icms_period,
        "Chave NF-e": reference.key,
        "Tipo Operação EFD Contribuições": value(contribution, "operation"),
        "Tipo Operação EFD ICMS": value(icms, "operation"),
        "Indicador Emitente EFD Contribuições": value(contribution, "issuer"),
        "Indicador Emitente EFD ICMS": value(icms, "issuer"),
        "Código Participante EFD Contribuições": value(contribution, "participant"),
        "Código Participante EFD ICMS": value(icms, "participant"),
        "Documento Participante EFD Contribuições": value(
            contribution, "participant_tax_id"
        ),
        "Documento Participante EFD ICMS": value(icms, "participant_tax_id"),
        "Modelo EFD Contribuições": value(contribution, "model"),
        "Modelo EFD ICMS": value(icms, "model"),
        "Situação EFD Contribuições": value(contribution, "situation"),
        "Situação EFD ICMS": value(icms, "situation"),
        "Série EFD Contribuições": value(contribution, "series"),
        "Série EFD ICMS": value(icms, "series"),
        "Número Documento EFD Contribuições": value(contribution, "number"),
        "Número Documento EFD ICMS": value(icms, "number"),
        "Data Documento EFD Contribuições": value(contribution, "document_date"),
        "Data Documento EFD ICMS": value(icms, "document_date"),
        "Data Entrada/Saída EFD Contribuições": value(contribution, "entry_exit_date"),
        "Data Entrada/Saída EFD ICMS": value(icms, "entry_exit_date"),
        "Valor Documento EFD Contribuições": value(contribution, "amount"),
        "Valor Documento EFD ICMS": value(icms, "amount"),
        "Divergências": ", ".join(differences),
        "Linhas EFD Contribuições": ",".join(
            str(note.line_number) for note in contribution_notes
        ),
        "Linhas EFD ICMS": ",".join(str(note.line_number) for note in icms_notes),
        "Quantidade EFD Contribuições": str(len(contribution_notes)),
        "Quantidade EFD ICMS": str(len(icms_notes)),
    }


def compare_efd_files(
    contribution_path: str | Path,
    icms_path: str | Path,
    output_path: str | Path,
    *,
    delimiter: str = ";",
) -> ComparisonResult:
    """Compara as notas C100 distintas da EFD Contribuições e EFD ICMS/IPI."""

    contribution_source = Path(contribution_path).expanduser().resolve()
    icms_source = Path(icms_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if target in {contribution_source, icms_source}:
        raise ValueError("o CSV de comparação não pode sobrescrever uma EFD")
    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")

    contribution_data = _read_file(contribution_source)
    icms_data = _read_file(icms_source)
    _validate_file_kind(
        contribution_data,
        source="contribution",
        filename=contribution_source.name,
    )
    _validate_file_kind(icms_data, source="icms", filename=icms_source.name)
    if (
        contribution_data.period
        and icms_data.period
        and contribution_data.period != icms_data.period
    ):
        raise EFDComparisonError(
            "os períodos das escriturações são diferentes: "
            f"{contribution_data.period} e {icms_data.period}"
        )

    all_contribution_notes = _notes(contribution_data, source="contribution")
    icms_notes = _notes(icms_data, source="icms")
    contribution_notes = [
        note
        for note in all_contribution_notes
        if cnpj_root(note.cnpj) == cnpj_root(icms_data.cnpj)
    ]
    if all_contribution_notes and not contribution_notes:
        raise EFDComparisonError(
            "a raiz do CNPJ da EFD ICMS/IPI não possui notas C100 "
            "na EFD Contribuições"
        )

    contribution_index = _index(contribution_notes)
    icms_index = _index(icms_notes)
    rows = [
        _comparison_row(
            contribution_index.get(identity, []),
            icms_index.get(identity, []),
            contribution_data.period,
            icms_data.period,
        )
        for identity in sorted(contribution_index.keys() | icms_index.keys())
    ]

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=COMPARISON_COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    observed = Counter(row["Status"] for row in rows)
    counts = {status: observed.get(status, 0) for status in STATUSES}
    return ComparisonResult(
        target,
        len(rows),
        len(contribution_notes),
        len(icms_notes),
        counts,
        contribution_data.period,
        icms_data.period,
        icms_data.cnpj,
    )
