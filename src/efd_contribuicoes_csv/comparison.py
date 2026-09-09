from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .identifiers import cnpj_root
from .scope import month_from_efd_period
from .document_layouts import (
    CANCELLED_PARENTS, COMPACT_A100, CONTRIBUTION_AUXILIARY, CONTRIBUTION_DOCUMENTS,
    CONTRIBUTION_SUMMARIES, ICMS_AUXILIARY, ICMS_DOCUMENTS, ICMS_SUMMARIES,
)

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
    "Presença EFD Contribuições",
    "Registros EFD Contribuições",
    "Registros EFD ICMS",
    "Arquivo EFD Contribuições",
    "Arquivo EFD ICMS",
    "Critério de Conferência",
    "Motivo da Revisão",
    "Evidências EFD Contribuições",
    "Tipo Evidência EFD Contribuições",
    "Tipo Evidência EFD ICMS",
    "Chave EFD Contribuições",
    "Chave EFD ICMS",
)

COVERAGE_COLUMNS = (
    "Origem", "Arquivo", "CNPJ", "Período", "Registro", "Tratamento",
    "Quantidade Registros", "Primeira Linha",
)

STATUSES = (
    "CONFERENTE",
    "DIVERGENTE",
    "SOMENTE_EFD_CONTRIBUICOES",
    "SOMENTE_EFD_ICMS",
    "DUPLICADA_EFD_CONTRIBUICOES",
    "DUPLICADA_EFD_ICMS",
    "DUPLICADA_AMBAS",
    "REVISAO_NECESSARIA",
    "SEM_EFD_CONTRIBUICOES",
    "SEM_EFD_ICMS",
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
    scoped_participants: dict[tuple[str, str], str] = field(default_factory=dict)
    filename: str = ""


@dataclass(frozen=True)
class FiscalNote:
    cnpj: str
    line_number: int
    operation: str = ""
    issuer: str = ""
    participant: str = ""
    participant_tax_id: str = ""
    model: str = ""
    situation: str = ""
    series: str = ""
    number: str = ""
    key: str = ""
    document_date: str = ""
    entry_exit_date: str = ""
    amount: str = ""
    subseries: str = ""
    equipment: str = ""
    record_code: str = "C100"
    source: str = ""
    kind: str = "DOCUMENTO"
    end_date: str = ""
    end_number: str = ""
    available_fields: frozenset[str] = frozenset()

    @property
    def identity(self) -> str:
        company = cnpj_root(self.cnpj)
        if self.key:
            namespace = "NFSE" if self.record_code == "A100" or (
                self.record_code == "B020" and self.model == "03"
            ) else "CHV_NFE"
            return f"{company}|{namespace}|{self.key}"
        return self.document_identity or f"{self.source}|{self.record_code}|LINHA|{self.line_number}"

    @property
    def document_identity(self) -> str:
        emitter = self.cnpj if self.issuer == "0" else self.participant_tax_id
        model = "ISS" if self.record_code in {"A100", "B020"} else self.model
        if not emitter or not model or not self.number or not self.document_date:
            return ""
        return "|".join((
            cnpj_root(self.cnpj), "DOC", emitter, model,
            _normalized_code(self.series), _normalized_code(self.subseries),
            _normalized_code(self.number), self.document_date[-4:], self.equipment,
            self.participant_tax_id,
        ))

    @property
    def display_identity(self) -> str:
        if self.kind != "DOCUMENTO":
            return f"{self.record_code}:LINHA:{self.line_number}"
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
    coverage: tuple[dict[str, str], ...] = ()


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
    try:
        month_from_efd_period(period)
    except ValueError as exc:
        raise EFDComparisonError(f"{path.name}: {exc}") from exc
    participant_tax_ids: dict[str, str] = {}
    scoped_participants: dict[tuple[str, str], str] = {}
    establishment = ""
    for record in records:
        if record.code == "0140":
            establishment = record.get(4)
        elif record.code == "0150" and record.get(2):
            tax_id = record.get(5) or record.get(6)
            if establishment:
                scoped_participants[establishment, record.get(2)] = tax_id
            else:
                participant_tax_ids[record.get(2)] = tax_id
    return _FileData(cnpj, period, tuple(records), participant_tax_ids, scoped_participants, path.name)


def _validate_file_kind(data: _FileData, *, source: str, filename: str) -> None:
    codes = {record.code for record in data.records}
    contribution_markers = {
        "0110",
        "0145",
        "A010",
        "A100",
        "A170",
        "C010",
        "D010",
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


def _normalized_code(value: str) -> str:
    if not value or value.isdecimal():
        return value.lstrip("0") or "0"
    return value


def _notes(data: _FileData, *, source: str) -> list[FiscalNote]:
    documents = CONTRIBUTION_DOCUMENTS if source == "contribution" else ICMS_DOCUMENTS
    summaries = CONTRIBUTION_SUMMARIES if source == "contribution" else ICMS_SUMMARIES
    auxiliary = CONTRIBUTION_AUXILIARY if source == "contribution" else ICMS_AUXILIARY
    notes: list[FiscalNote] = []
    current_cnpj = {block: data.cnpj for block in "ABCDF"}
    equipment: _Record | None = None
    cancellation_parent: FiscalNote | None = None
    current_block = ""
    for record in data.records:
        block = record.code[:1]
        if block != current_block or record.code in {"C010", "D010", "C990", "D990"}:
            equipment = None
            cancellation_parent = None
        current_block = block
        if source == "contribution" and record.code in {"A010", "C010", "D010", "F010"}:
            current_cnpj[block] = record.get(2) or data.cnpj
            continue
        if record.code in {"C400", "D350"} and (
            record.code == "C400" or source == "icms"
        ):
            equipment = record
            continue
        if source == "icms" and record.code == "C465":
            if not notes or notes[-1].record_code != "C460":
                raise EFDComparisonError(f"linha {record.line_number}: C465 sem C460 anterior")
            if len(record.fields) != 3 or not re.fullmatch(r"\d{44}", record.get(2)):
                raise EFDComparisonError(f"linha {record.line_number}: C465 inválido")
            notes[-1] = replace(notes[-1], key=record.get(2))
            continue
        spec = documents.get(record.code) or summaries.get(record.code)
        cnpj = current_cnpj.get(block, data.cnpj)
        if spec is None:
            blocks = "ACDF" if source == "contribution" else "BCD"
            if block in blocks and record.code not in auxiliary:
                notes.append(FiscalNote(
                    cnpj, record.line_number, record_code=record.code,
                    source=source, kind="NAO_MAPEADO",
                ))
            continue
        if source == "contribution" and record.code == "A100" and len(record.fields) == 19:
            spec = COMPACT_A100
        if spec.lengths and len(record.fields) not in spec.lengths:
            label = "EFD Contribuições" if source == "contribution" else "EFD ICMS/IPI"
            expected = " ou ".join(str(length) for length in spec.lengths)
            raise EFDComparisonError(
                f"linha {record.line_number}: {record.code} da {label} possui "
                f"{len(record.fields)} campos; esperado {expected}"
            )
        values = {name: record.get(position) for name, position in spec.fields.items()}
        values.update(spec.fixed)
        if source == "icms" and record.code in CANCELLED_PARENTS:
            if cancellation_parent is None or cancellation_parent.record_code != CANCELLED_PARENTS[record.code]:
                raise EFDComparisonError(f"linha {record.line_number}: {record.code} sem resumo pai anterior")
            values.update({
                name: getattr(cancellation_parent, name)
                for name in ("model", "series", "subseries", "document_date")
            })
        participant = values.get("participant", "")
        if participant:
            values["participant_tax_id"] = data.scoped_participants.get(
                (cnpj, participant), data.participant_tax_ids.get(participant, "")
            )
        elif "participant" in values:
            values.setdefault("participant_tax_id", "")
        if record.code in {"C460", "C405", "D355"}:
            if equipment is None:
                raise EFDComparisonError(
                    f"linha {record.line_number}: {record.code} sem equipamento anterior"
                )
            values.update(equipment=equipment.get(4), model=values.get("model") or equipment.get(2))
        kind = "DOCUMENTO" if record.code in documents else "CONSOLIDADO"
        if kind == "CONSOLIDADO" and block in "BCD" and record.code != "C190":
            values.setdefault("operation", "1")
        for name in ("document_date", "entry_exit_date", "end_date"):
            value = values.get(name, "")
            if value:
                try:
                    if not re.fullmatch(r"\d{8}", value):
                        raise ValueError("formato de data")
                    datetime.strptime(value, "%d%m%Y")
                except ValueError as exc:
                    raise EFDComparisonError(
                        f"linha {record.line_number}: data inválida em {record.code}: {value!r}"
                    ) from exc
        # O compacto original permite chaves sintéticas; os demais leiautes usam 44 dígitos.
        key = values.get("key", "")
        if key and record.code != "A100" and not (
            source == "contribution" and record.code == "C100" and len(record.fields) == 28
        ) and not re.fullmatch(r"\d{44}", key):
            raise EFDComparisonError(f"linha {record.line_number}: chave de {record.code} deve possuir 44 dígitos")
        if values.get("amount"):
            _decimal_equal(values["amount"], values["amount"])
        notes.append(FiscalNote(
            cnpj, record.line_number, **values, record_code=record.code,
            source=source, kind=kind, available_fields=frozenset(values),
        ))
        if source == "icms" and record.code not in CANCELLED_PARENTS:
            cancellation_parent = notes[-1] if record.code in CANCELLED_PARENTS.values() else None
    return notes


def _coverage(data: _FileData, *, source: str) -> tuple[dict[str, str], ...]:
    documents = CONTRIBUTION_DOCUMENTS if source == "contribution" else ICMS_DOCUMENTS
    summaries = CONTRIBUTION_SUMMARIES if source == "contribution" else ICMS_SUMMARIES
    auxiliary = CONTRIBUTION_AUXILIARY if source == "contribution" else ICMS_AUXILIARY
    counts = Counter(record.code for record in data.records)
    first_lines: dict[str, int] = {}
    for record in data.records:
        first_lines.setdefault(record.code, record.line_number)
    blocks = "ACDF" if source == "contribution" else "BCD"
    return tuple({
        "Origem": "EFD Contribuições" if source == "contribution" else "EFD ICMS/IPI",
        "Arquivo": data.filename, "CNPJ": data.cnpj, "Período": data.period,
        "Registro": code,
        "Tratamento": (
            "DOCUMENTO INDIVIDUAL" if code in documents else
            "SEM IDENTIFICAÇÃO INDIVIDUAL" if code in summaries else
            "AUXILIAR / NÃO É OUTRA NOTA" if code in auxiliary else "NÃO MAPEADO"
        ),
        "Quantidade Registros": str(count), "Primeira Linha": str(first_lines[code]),
    } for code, count in sorted(counts.items()) if code[:1] in blocks)


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
            parsed = Decimal(normalized)
            if not parsed.is_finite():
                raise InvalidOperation
            return parsed
        except InvalidOperation as exc:
            raise EFDComparisonError(f"valor monetário inválido: {value!r}") from exc

    return parse(left) == parse(right)


def _differences(contribution: FiscalNote, icms: FiscalNote) -> list[str]:
    fields = {
        "operation": "Tipo Operação", "issuer": "Indicador Emitente",
        "participant_tax_id": "Documento Participante", "model": "Modelo",
        "situation": "Situação", "series": "Série", "subseries": "Subsérie",
        "number": "Número Documento", "document_date": "Data Documento",
        "entry_exit_date": "Data Entrada/Saída", "amount": "Valor Documento",
    }
    differences: list[str] = []
    for attribute, label in fields.items():
        if attribute not in contribution.available_fields & icms.available_fields:
            continue
        left, right = getattr(contribution, attribute), getattr(icms, attribute)
        if attribute == "amount":
            equal = _decimal_equal(left, right)
        elif attribute in {"series", "subseries", "number"}:
            equal = _normalized_code(left) == _normalized_code(right)
        else:
            equal = left == right
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
        "Chave NF-e": value(contribution, "key") or value(icms, "key"),
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
        "Presença EFD Contribuições": "PRESENTE" if contribution else "NAO_LOCALIZADA",
        "Registros EFD Contribuições": ",".join(sorted({note.record_code for note in contribution_notes})),
        "Registros EFD ICMS": ",".join(sorted({note.record_code for note in icms_notes})),
        "Arquivo EFD Contribuições": "",
        "Arquivo EFD ICMS": "",
        "Critério de Conferência": "CHAVE" if contribution and icms and contribution.key and icms.key else "IDENTIFICAÇÃO DOCUMENTAL",
        "Motivo da Revisão": "",
        "Evidências EFD Contribuições": "",
        "Tipo Evidência EFD Contribuições": value(contribution, "kind"),
        "Tipo Evidência EFD ICMS": value(icms, "kind"),
        "Chave EFD Contribuições": value(contribution, "key"),
        "Chave EFD ICMS": value(icms, "key"),
    }


def _may_cover(summary: FiscalNote, note: FiscalNote) -> bool:
    if summary.cnpj != note.cnpj:
        return False
    if summary.kind == "NAO_MAPEADO":
        return summary.record_code[0] in {note.record_code[0], "F"} or (
            summary.record_code.startswith("A") and note.record_code.startswith("B")
        )
    if summary.operation and summary.operation.replace("2", "1") != note.operation:
        return False
    if summary.model and note.model and summary.model != note.model:
        return False
    if summary.participant_tax_id and note.participant_tax_id and summary.participant_tax_id != note.participant_tax_id:
        return False
    for attribute in ("series", "subseries", "equipment"):
        left, right = getattr(summary, attribute), getattr(note, attribute)
        if left and right and _normalized_code(left) != _normalized_code(right):
            return False
    reference_date = note.entry_exit_date if note.operation == "0" else note.document_date
    reference_date = reference_date or note.document_date
    if summary.document_date and reference_date:
        start = datetime.strptime(summary.document_date, "%d%m%Y")
        end = datetime.strptime(summary.end_date or summary.document_date, "%d%m%Y")
        if not start <= datetime.strptime(reference_date, "%d%m%Y") <= end:
            return False
    if all(value.isdecimal() for value in (summary.number, summary.end_number, note.number)):
        if not int(summary.number) <= int(note.number) <= int(summary.end_number):
            return False
    return True


def _matched_groups(
    contributions: list[FiscalNote], icms: list[FiscalNote],
) -> list[tuple[list[FiscalNote], list[FiscalNote]]]:
    left, right = _index(contributions), _index(icms)
    pairs = [(left.pop(key), right.pop(key)) for key in sorted(left.keys() & right.keys())]
    # Sem chave em um dos lados, só usar uma identificação documental única.
    left_ids: dict[str, set[str]] = defaultdict(set)
    right_ids: dict[str, set[str]] = defaultdict(set)
    for notes, identities in ((contributions, left_ids), (icms, right_ids)):
        for note in notes:
            if note.document_identity:
                identities[note.document_identity].add(note.identity)
    for identity in sorted(left_ids.keys() & right_ids.keys()):
        if len(left_ids[identity]) != 1 or len(right_ids[identity]) != 1:
            continue
        left_key = next(iter(left_ids[identity]))
        right_key = next(iter(right_ids[identity]))
        if left_key in left and right_key in right:
            if not left[left_key][0].key or not right[right_key][0].key:
                pairs.append((left.pop(left_key), right.pop(right_key)))
    pairs.extend((notes, []) for notes in left.values())
    pairs.extend(([], notes) for notes in right.values())
    return pairs


def _partial_identity(note: FiscalNote) -> tuple[str, str, str]:
    model = "ISS" if note.record_code in {"A100", "B020"} else note.model
    return cnpj_root(note.cnpj), model, _normalized_code(note.number)


def _compatible_identity(left: FiscalNote, right: FiscalNote) -> bool:
    for attribute in ("participant_tax_id", "series", "subseries", "equipment"):
        a, b = getattr(left, attribute), getattr(right, attribute)
        if a and b and _normalized_code(a) != _normalized_code(b):
            return False
    return not (left.document_date and right.document_date and left.document_date[-4:] != right.document_date[-4:])


def compare_efd_files(
    contribution_path: str | Path | None,
    icms_path: str | Path | None,
    output_path: str | Path,
    *,
    delimiter: str = ";",
) -> ComparisonResult:
    """Confere documentos e expõe limitações de identificação e cobertura."""

    if contribution_path is None and icms_path is None:
        raise ValueError("informe ao menos uma EFD")
    target = Path(output_path).expanduser().resolve()
    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")
    data_by_source: dict[str, _FileData] = {}
    for source, path in (("contribution", contribution_path), ("icms", icms_path)):
        if path is None:
            continue
        resolved = Path(path).expanduser().resolve()
        if target == resolved:
            raise ValueError("o CSV de comparação não pode sobrescrever uma EFD")
        data = _read_file(resolved)
        _validate_file_kind(data, source=source, filename=resolved.name)
        data_by_source[source] = data
    reference = data_by_source.get("icms") or data_by_source["contribution"]
    empty = _FileData(reference.cnpj, "", (), {})
    contribution_data = data_by_source.get("contribution", empty)
    icms_data = data_by_source.get("icms", empty)
    if contribution_path is not None and icms_path is not None:
        if contribution_data.period != icms_data.period:
            raise EFDComparisonError(
                "os períodos das escriturações são diferentes: "
                f"{contribution_data.period} e {icms_data.period}"
            )
        if cnpj_root(contribution_data.cnpj) != cnpj_root(icms_data.cnpj):
            raise EFDComparisonError("as raízes de CNPJ das escriturações são diferentes")

    contribution_records = [
        note for note in _notes(contribution_data, source="contribution")
        if cnpj_root(note.cnpj) == cnpj_root(reference.cnpj)
    ]
    icms_records = _notes(icms_data, source="icms")
    contribution_notes = [note for note in contribution_records if note.kind == "DOCUMENTO"]
    icms_notes = [note for note in icms_records if note.kind == "DOCUMENTO"]
    alternatives = [note for note in contribution_records if note.kind != "DOCUMENTO"]
    contribution_identities = {note.document_identity for note in contribution_notes if note.document_identity}
    incomplete_candidates: dict[tuple[str, str, str], list[FiscalNote]] = defaultdict(list)
    for note in contribution_notes:
        if not note.key and note.number:
            incomplete_candidates[_partial_identity(note)].append(note)
    pairs = _matched_groups(contribution_notes, icms_notes)
    # Resumos do ICMS não desaparecem nem são transformados em notas fictícias.
    pairs.extend(([], [note]) for note in icms_records if note.kind != "DOCUMENTO")
    pairs.extend(([note], []) for note in alternatives if note.kind == "NAO_MAPEADO")
    rows: list[dict[str, str]] = []
    for left, right in pairs:
        row = _comparison_row(left, right, contribution_data.period, icms_data.period)
        row["Arquivo EFD Contribuições"] = contribution_data.filename
        row["Arquivo EFD ICMS"] = icms_data.filename
        note = (right or left)[0]
        reason = ""
        if note.kind != "DOCUMENTO":
            reason = (
                "Registro não mapeado: conferir o leiaute antes de concluir a presença."
                if note.kind == "NAO_MAPEADO" else
                "ICMS escriturado por resumo/faixa; o TXT não individualiza todas as notas."
            )
        elif right and not left:
            evidence = [item for item in alternatives if _may_cover(item, note)]
            if evidence:
                reason = "Há escrituração sem identificação individual compatível; ela não comprova a presença nem a ausência desta nota."
                row["Evidências EFD Contribuições"] = "; ".join(
                    f"{item.record_code} linha {item.line_number}" for item in evidence
                )
            elif not note.key and not note.document_identity:
                reason = "Dados insuficientes para identificar unicamente o documento (emitente/modelo/número/data)."
            elif note.document_identity and note.document_identity in contribution_identities:
                reason = "Identificação documental ambígua ou chaves diferentes; conferir os documentos candidatos."
            elif any(_compatible_identity(item, note) for item in incomplete_candidates.get(_partial_identity(note), [])):
                reason = "Há documento com mesmo modelo e número, mas faltam dados para confirmar uma correspondência única."
        if reason:
            row["Status"] = "REVISAO_NECESSARIA"
            row["Presença EFD Contribuições"] = "INCONCLUSIVA"
            row["Motivo da Revisão"] = reason
            row["Divergências"] = ""
            row["Critério de Conferência"] = "REVISÃO MANUAL"
        if contribution_path is None:
            row["Status"] = "SEM_EFD_CONTRIBUICOES"
            row["Presença EFD Contribuições"] = "SEM_ARQUIVO"
            row["Motivo da Revisão"] = "EFD Contribuições do período não fornecida; não é possível concluir ausência."
            row["Divergências"] = ""
        elif icms_path is None:
            row["Status"] = "SEM_EFD_ICMS"
            row["Motivo da Revisão"] = "EFD ICMS/IPI do período não fornecida."
            row["Divergências"] = ""
        if not left and row["Presença EFD Contribuições"] == "NAO_LOCALIZADA":
            row["Critério de Conferência"] = "CHAVE" if note.key else "IDENTIFICAÇÃO DOCUMENTAL"
            row["Divergências"] = "Documento não localizado nas formas de escrituração verificadas; avaliar a obrigatoriedade fiscal."
        rows.append(row)
    rows.sort(key=lambda row: (row["Identificador"], row["Registros EFD ICMS"], row["Linhas EFD ICMS"]))

    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=COMPARISON_COLUMNS, delimiter=delimiter, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    observed = Counter(row["Status"] for row in rows)
    return ComparisonResult(
        target, len(rows), len(contribution_notes), len(icms_notes),
        {status: observed.get(status, 0) for status in STATUSES},
        contribution_data.period, icms_data.period, reference.cnpj,
        _coverage(contribution_data, source="contribution") + _coverage(icms_data, source="icms"),
    )
