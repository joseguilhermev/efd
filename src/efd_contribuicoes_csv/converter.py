from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from pathlib import Path

from .cfop import cfop_details

COLUMNS = (
    "CNPJ",
    "Período",
    "Registros",
    "Tipo Operação",
    "Situação",
    "Código Participante",
    "CNPJ Participante",
    "CPF Participante",
    "Nome Participante",
    "UF Origem/Destino",
    "Número Documento",
    "Série",
    "Chave NF-e",
    "Data Documento",
    "Data Entrada/Saída",
    "Vlr Documento",
    "Vlr Desconto NF",
    "Vlr Mercadoria/Operação",
    "Vlr Frete",
    "Vlr Seguro",
    "Vlr Outras DA",
    "Número Item",
    "Código Item",
    "Descrição Complementar",
    "Descrição Item",
    "NCM",
    "Código Serviço",
    "Código Barra",
    "Tipo Item",
    "Vlr Item",
    "Qtde",
    "Unidade Medida",
    "Vlr Desconto Item",
    "Natureza Crédito",
    "CFOP",
    "Descrição CFOP",
    "CFOP Faturamento",
    "CST ICMS",
    "Vlr Base Cálculo ICMS",
    "Alíquota ICMS",
    "Vlr ICMS",
    "Vlr Base Cálculo ICMS ST",
    "Alíquota ICMS ST",
    "Vlr ICMS ST",
    "CST IPI",
    "Vlr Base Cálculo IPI",
    "Alíquota IPI",
    "Vlr IPI",
    "CST PIS",
    "Vlr Base Cálculo PIS",
    "Qtde Base Cálculo PIS",
    "Alíquota PIS",
    "Qtde Alíquota PIS",
    "Vlr PIS",
    "CST Cofins",
    "Vlr Base Cálculo Cofins",
    "Qtde Base Cálculo Cofins",
    "Alíquota Cofins",
    "Qtde Alíquota Cofins",
    "Vlr Cofins",
    "Conta Contábil",
    "Débito/Crédito",
)

SUPPORTED_OUTPUTS = (
    "A100/A170",
    "C100/C170",
    "C100/C175",
    "C180/C181/C185",
    "C190/C191/C195",
    "C380/C381/C385",
    "C395/C396",
    "C400/C405/C481/C485",
    "C490/C491/C495",
    "C500/C501/C505",
    "C600/C601/C605",
    "C800/C810",
    "C800/C820",
    "C860/C870",
    "C860/C880",
    "D100/D101/D105",
    "D200/D201/D205",
    "D500/D501/D505",
    "D600/D601/D605",
    "F100",
    "F550",
)


IBGE_UF = {
    "11": "RO",
    "12": "AC",
    "13": "AM",
    "14": "RR",
    "15": "PA",
    "16": "AP",
    "17": "TO",
    "21": "MA",
    "22": "PI",
    "23": "CE",
    "24": "RN",
    "25": "PB",
    "26": "PE",
    "27": "AL",
    "28": "SE",
    "29": "BA",
    "31": "MG",
    "32": "ES",
    "33": "RJ",
    "35": "SP",
    "41": "PR",
    "42": "SC",
    "43": "RS",
    "50": "MS",
    "51": "MT",
    "52": "GO",
    "53": "DF",
}


class EFDParseError(ValueError):
    """Erro estrutural que impediria relacionar corretamente os registros."""


@dataclass(frozen=True)
class Record:
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
class Participant:
    name: str
    cnpj: str
    cpf: str
    cod_mun: str
    address: str

    @property
    def uf(self) -> str:
        if len(self.cod_mun) >= 2 and self.cod_mun[:2] in IBGE_UF:
            return IBGE_UF[self.cod_mun[:2]]
        match = re.match(r"\s*([A-Z]{2})(?:\s|[-/]|$)", self.address.upper())
        return match.group(1) if match else ""


@dataclass(frozen=True)
class Item:
    description: str
    barcode: str
    item_type: str
    ncm: str
    service_code: str


@dataclass(frozen=True)
class MasterData:
    cnpj: str
    period: str
    participants: dict[str, Participant]
    items: dict[str, Item]


@dataclass
class PendingDocument:
    record: Record
    cnpj: str


@dataclass
class PendingTaxGroup:
    record: Record
    cnpj: str
    pis_records: list[Record]
    cofins_records: list[Record]
    context: Record | None = None


@dataclass(frozen=True)
class DirectChildSpec:
    parent: str
    records: str
    fields: dict[str, int]
    item_position: int | None = None


@dataclass(frozen=True)
class SplitChildSpec:
    records: str
    pis_code: str
    cofins_code: str
    key_positions: tuple[int, ...]
    pis_fields: dict[str, int]
    cofins_fields: dict[str, int]
    item_position: int | None = None


@dataclass(frozen=True)
class ConversionResult:
    output_path: Path
    rows: int
    by_record: dict[str, int]
    input_encoding: str
    period: str
    cnpj: str


DIRECT_CHILD_SPECS = {
    "C175": DirectChildSpec(
        "C100",
        "C100/C175",
        {
            "CFOP": 2,
            "Vlr Item": 3,
            "Vlr Desconto Item": 4,
            "CST PIS": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Qtde Base Cálculo PIS": 8,
            "Qtde Alíquota PIS": 9,
            "Vlr PIS": 10,
            "CST Cofins": 11,
            "Vlr Base Cálculo Cofins": 12,
            "Alíquota Cofins": 13,
            "Qtde Base Cálculo Cofins": 14,
            "Qtde Alíquota Cofins": 15,
            "Vlr Cofins": 16,
            "Conta Contábil": 17,
            "Descrição Complementar": 18,
        },
    ),
    "C396": DirectChildSpec(
        "C395",
        "C395/C396",
        {
            "Vlr Item": 3,
            "Vlr Desconto Item": 4,
            "Natureza Crédito": 5,
            "CST PIS": 6,
            "Vlr Base Cálculo PIS": 7,
            "Alíquota PIS": 8,
            "Vlr PIS": 9,
            "CST Cofins": 10,
            "Vlr Base Cálculo Cofins": 11,
            "Alíquota Cofins": 12,
            "Vlr Cofins": 13,
            "Conta Contábil": 14,
        },
        2,
    ),
    "C810": DirectChildSpec(
        "C800",
        "C800/C810",
        {
            "CFOP": 2,
            "Vlr Item": 3,
            "CST PIS": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Vlr PIS": 8,
            "CST Cofins": 9,
            "Vlr Base Cálculo Cofins": 10,
            "Alíquota Cofins": 11,
            "Vlr Cofins": 12,
            "Conta Contábil": 13,
        },
        4,
    ),
    "C820": DirectChildSpec(
        "C800",
        "C800/C820",
        {
            "CFOP": 2,
            "Vlr Item": 3,
            "CST PIS": 5,
            "Qtde Base Cálculo PIS": 6,
            "Qtde Alíquota PIS": 7,
            "Vlr PIS": 8,
            "CST Cofins": 9,
            "Qtde Base Cálculo Cofins": 10,
            "Qtde Alíquota Cofins": 11,
            "Vlr Cofins": 12,
            "Conta Contábil": 13,
        },
        4,
    ),
    "C870": DirectChildSpec(
        "C860",
        "C860/C870",
        {
            "CFOP": 3,
            "Vlr Item": 4,
            "Vlr Desconto Item": 5,
            "CST PIS": 6,
            "Vlr Base Cálculo PIS": 7,
            "Alíquota PIS": 8,
            "Vlr PIS": 9,
            "CST Cofins": 10,
            "Vlr Base Cálculo Cofins": 11,
            "Alíquota Cofins": 12,
            "Vlr Cofins": 13,
            "Conta Contábil": 14,
        },
        2,
    ),
    "C880": DirectChildSpec(
        "C860",
        "C860/C880",
        {
            "CFOP": 3,
            "Vlr Item": 4,
            "Vlr Desconto Item": 5,
            "CST PIS": 6,
            "Qtde Base Cálculo PIS": 7,
            "Qtde Alíquota PIS": 8,
            "Vlr PIS": 9,
            "CST Cofins": 10,
            "Qtde Base Cálculo Cofins": 11,
            "Qtde Alíquota Cofins": 12,
            "Vlr Cofins": 13,
            "Conta Contábil": 14,
        },
        2,
    ),
}


SPLIT_CHILD_SPECS = {
    "C180": SplitChildSpec(
        "C180/C181/C185",
        "C181",
        "C185",
        (3, 4, 5),
        {
            "CST PIS": 2,
            "CFOP": 3,
            "Vlr Item": 4,
            "Vlr Desconto Item": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Qtde Base Cálculo PIS": 8,
            "Qtde Alíquota PIS": 9,
            "Vlr PIS": 10,
            "Conta Contábil": 11,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 6,
            "Alíquota Cofins": 7,
            "Qtde Base Cálculo Cofins": 8,
            "Qtde Alíquota Cofins": 9,
            "Vlr Cofins": 10,
            "Conta Contábil": 11,
        },
    ),
    "C190": SplitChildSpec(
        "C190/C191/C195",
        "C191",
        "C195",
        (2, 4, 5, 6),
        {
            "CNPJ Participante": 2,
            "CST PIS": 3,
            "CFOP": 4,
            "Vlr Item": 5,
            "Vlr Desconto Item": 6,
            "Vlr Base Cálculo PIS": 7,
            "Alíquota PIS": 8,
            "Qtde Base Cálculo PIS": 9,
            "Qtde Alíquota PIS": 10,
            "Vlr PIS": 11,
            "Conta Contábil": 12,
        },
        {
            "CNPJ Participante": 2,
            "CST Cofins": 3,
            "Vlr Base Cálculo Cofins": 7,
            "Alíquota Cofins": 8,
            "Qtde Base Cálculo Cofins": 9,
            "Qtde Alíquota Cofins": 10,
            "Vlr Cofins": 11,
            "Conta Contábil": 12,
        },
    ),
    "C380": SplitChildSpec(
        "C380/C381/C385",
        "C381",
        "C385",
        (3, 4),
        {
            "CST PIS": 2,
            "Vlr Item": 4,
            "Vlr Base Cálculo PIS": 5,
            "Alíquota PIS": 6,
            "Qtde Base Cálculo PIS": 7,
            "Qtde Alíquota PIS": 8,
            "Vlr PIS": 9,
            "Conta Contábil": 10,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 5,
            "Alíquota Cofins": 6,
            "Qtde Base Cálculo Cofins": 7,
            "Qtde Alíquota Cofins": 8,
            "Vlr Cofins": 9,
            "Conta Contábil": 10,
        },
        3,
    ),
    "C405": SplitChildSpec(
        "C400/C405/C481/C485",
        "C481",
        "C485",
        (3, 9),
        {
            "CST PIS": 2,
            "Vlr Item": 3,
            "Vlr Base Cálculo PIS": 4,
            "Alíquota PIS": 5,
            "Qtde Base Cálculo PIS": 6,
            "Qtde Alíquota PIS": 7,
            "Vlr PIS": 8,
            "Conta Contábil": 10,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 4,
            "Alíquota Cofins": 5,
            "Qtde Base Cálculo Cofins": 6,
            "Qtde Alíquota Cofins": 7,
            "Vlr Cofins": 8,
            "Conta Contábil": 10,
        },
        9,
    ),
    "C490": SplitChildSpec(
        "C490/C491/C495",
        "C491",
        "C495",
        (2, 4, 5),
        {
            "CST PIS": 3,
            "CFOP": 4,
            "Vlr Item": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Qtde Base Cálculo PIS": 8,
            "Qtde Alíquota PIS": 9,
            "Vlr PIS": 10,
            "Conta Contábil": 11,
        },
        {
            "CST Cofins": 3,
            "Vlr Base Cálculo Cofins": 6,
            "Alíquota Cofins": 7,
            "Qtde Base Cálculo Cofins": 8,
            "Qtde Alíquota Cofins": 9,
            "Vlr Cofins": 10,
            "Conta Contábil": 11,
        },
        2,
    ),
    "C500": SplitChildSpec(
        "C500/C501/C505",
        "C501",
        "C505",
        (3, 4),
        {
            "CST PIS": 2,
            "Vlr Item": 3,
            "Natureza Crédito": 4,
            "Vlr Base Cálculo PIS": 5,
            "Alíquota PIS": 6,
            "Vlr PIS": 7,
            "Conta Contábil": 8,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 5,
            "Alíquota Cofins": 6,
            "Vlr Cofins": 7,
            "Conta Contábil": 8,
        },
    ),
    "C600": SplitChildSpec(
        "C600/C601/C605",
        "C601",
        "C605",
        (3,),
        {
            "CST PIS": 2,
            "Vlr Item": 3,
            "Vlr Base Cálculo PIS": 4,
            "Alíquota PIS": 5,
            "Vlr PIS": 6,
            "Conta Contábil": 7,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 4,
            "Alíquota Cofins": 5,
            "Vlr Cofins": 6,
            "Conta Contábil": 7,
        },
    ),
    "D100": SplitChildSpec(
        "D100/D101/D105",
        "D101",
        "D105",
        (2, 3, 5),
        {
            "Vlr Item": 3,
            "CST PIS": 4,
            "Natureza Crédito": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Vlr PIS": 8,
            "Conta Contábil": 9,
        },
        {
            "CST Cofins": 4,
            "Vlr Base Cálculo Cofins": 6,
            "Alíquota Cofins": 7,
            "Vlr Cofins": 8,
            "Conta Contábil": 9,
        },
    ),
    "D200": SplitChildSpec(
        "D200/D201/D205",
        "D201",
        "D205",
        (3,),
        {
            "CST PIS": 2,
            "Vlr Item": 3,
            "Vlr Base Cálculo PIS": 4,
            "Alíquota PIS": 5,
            "Vlr PIS": 6,
            "Conta Contábil": 7,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 4,
            "Alíquota Cofins": 5,
            "Vlr Cofins": 6,
            "Conta Contábil": 7,
        },
    ),
    "D500": SplitChildSpec(
        "D500/D501/D505",
        "D501",
        "D505",
        (3, 4),
        {
            "CST PIS": 2,
            "Vlr Item": 3,
            "Natureza Crédito": 4,
            "Vlr Base Cálculo PIS": 5,
            "Alíquota PIS": 6,
            "Vlr PIS": 7,
            "Conta Contábil": 8,
        },
        {
            "CST Cofins": 2,
            "Vlr Base Cálculo Cofins": 5,
            "Alíquota Cofins": 6,
            "Vlr Cofins": 7,
            "Conta Contábil": 8,
        },
    ),
    "D600": SplitChildSpec(
        "D600/D601/D605",
        "D601",
        "D605",
        (2, 3, 4),
        {
            "Código Serviço": 2,
            "Vlr Item": 3,
            "Vlr Desconto Item": 4,
            "CST PIS": 5,
            "Vlr Base Cálculo PIS": 6,
            "Alíquota PIS": 7,
            "Vlr PIS": 8,
            "Conta Contábil": 9,
        },
        {
            "CST Cofins": 5,
            "Vlr Base Cálculo Cofins": 6,
            "Alíquota Cofins": 7,
            "Vlr Cofins": 8,
            "Conta Contábil": 9,
        },
    ),
}

SPLIT_CHILD_TO_PARENT = {
    child: parent
    for parent, spec in SPLIT_CHILD_SPECS.items()
    for child in (spec.pis_code, spec.cofins_code)
}

LEVEL_THREE_PARENTS = {
    "A100",
    "C100",
    "C180",
    "C190",
    "C380",
    "C395",
    "C400",
    "C490",
    "C500",
    "C600",
    "C800",
    "C860",
    "D100",
    "D200",
    "D300",
    "D350",
    "D500",
    "D600",
}


def _decode_input(path: Path) -> tuple[str, str]:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "latin-1"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    raise EFDParseError(f"não foi possível decodificar o arquivo {path}")


def _parse_records(text: str) -> list[Record]:
    records: list[Record] = []
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        fields = line.split("|")
        if fields and fields[0] == "":
            fields = fields[1:]
        if fields and fields[-1] == "":
            fields = fields[:-1]
        if not fields or not fields[0].strip():
            raise EFDParseError(f"linha {line_number}: registro vazio ou malformado")
        records.append(Record(line_number, tuple(fields)))
    if not records:
        raise EFDParseError("o arquivo EFD está vazio")
    return records


def _validate_supported_layouts(records: list[Record]) -> None:
    expected_lengths = {
        "A100": {19, 21},
        "A170": {18, 19},
        "C100": {28, 29},
        "C170": {24, 37},
        "C175": {18},
        "C180": {8},
        "C181": {11},
        "C185": {11},
        "C190": {8},
        "C191": {12},
        "C195": {12},
        "C380": {8},
        "C381": {10},
        "C385": {10},
        "C395": {8},
        "C396": {14},
        "C400": {5},
        "C405": {7},
        "C481": {10},
        "C485": {10},
        "C490": {4},
        "C491": {11},
        "C495": {11},
        "C500": {15},
        "C501": {8},
        "C505": {8},
        "C600": {22},
        "C601": {7},
        "C605": {7},
        "C800": {17},
        "C810": {13},
        "C820": {13},
        "C860": {6},
        "C870": {14},
        "C880": {14},
        "D100": {23},
        "D101": {9},
        "D105": {9},
        "D200": {11},
        "D201": {7},
        "D205": {7},
        "D500": {22},
        "D501": {8},
        "D505": {8},
        "D600": {19},
        "D601": {9},
        "D605": {9},
        "F100": {19, 20},
        "F550": {16},
    }
    contribution_only = set(expected_lengths) - {
        "A100",
        "A170",
        "C100",
        "C170",
        "F100",
        "F550",
    }
    codes = {record.code for record in records}
    is_contribution = bool(
        codes
        & {
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
    )
    for record in records:
        allowed = expected_lengths.get(record.code)
        if record.code in contribution_only and not is_contribution:
            continue
        if allowed is not None and len(record.fields) not in allowed:
            expected = " ou ".join(str(length) for length in sorted(allowed))
            raise EFDParseError(
                f"linha {record.line_number}: {record.code} possui "
                f"{len(record.fields)} campos; esperado {expected}"
            )


def _validate_contribution_file(records: list[Record], master: MasterData) -> None:
    codes = {record.code for record in records}
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
    if "0000" not in codes or not (codes & contribution_markers):
        raise EFDParseError(
            "o arquivo não foi identificado como uma EFD Contribuições"
        )
    if not master.cnpj:
        raise EFDParseError("CNPJ não encontrado no registro 0000")
    if not master.period:
        raise EFDParseError("período não encontrado no registro 0000")


def _is_date(value: str) -> bool:
    return bool(re.fullmatch(r"\d{8}", value))


def _format_date(value: str) -> str:
    if not _is_date(value):
        return value
    return f"{value[0:2]}/{value[2:4]}/{value[4:8]}"


def _master_data(records: list[Record]) -> MasterData:
    cnpj = ""
    period = ""
    participants: dict[str, Participant] = {}
    items: dict[str, Item] = {}

    for record in records:
        if record.code == "0000":
            date_position = next(
                (
                    pos
                    for pos in range(2, len(record.fields))
                    if _is_date(record.get(pos)) and _is_date(record.get(pos + 1))
                ),
                None,
            )
            if date_position is not None:
                start = _format_date(record.get(date_position))
                end = _format_date(record.get(date_position + 1))
                period = f"{start} a {end}"
                cnpj = record.get(date_position + 3)
            if not cnpj:
                cnpj = next(
                    (
                        field
                        for field in record.fields
                        if re.fullmatch(r"\d{14}", field)
                    ),
                    "",
                )
        elif record.code == "0150":
            address = record.get(10)
            if re.match(r"\s*[A-Z]{2}(?:\s|[-/]|$)", record.get(9).upper()):
                # A massa sintetica colocou "UF MUNICIPIO" no campo 9.
                address = record.get(9)
            participants[record.get(2)] = Participant(
                name=record.get(3),
                cnpj=record.get(5),
                cpf=record.get(6),
                cod_mun=record.get(8),
                address=address,
            )
        elif record.code == "0200":
            items[record.get(2)] = Item(
                description=record.get(3),
                barcode=record.get(4),
                item_type=record.get(7),
                ncm=record.get(8),
                service_code=record.get(11),
            )
    return MasterData(cnpj, period, participants, items)


def _empty_row(master: MasterData, cnpj: str, records: str) -> dict[str, str]:
    row = dict.fromkeys(COLUMNS, "")
    row["CNPJ"] = cnpj or master.cnpj
    row["Período"] = master.period
    row["Registros"] = records
    return row


def _add_participant(row: dict[str, str], code: str, master: MasterData) -> None:
    row["Código Participante"] = code
    participant = master.participants.get(code)
    if participant is None:
        return
    row["CNPJ Participante"] = participant.cnpj
    row["CPF Participante"] = participant.cpf
    row["Nome Participante"] = participant.name
    row["UF Origem/Destino"] = participant.uf


def _add_item(row: dict[str, str], code: str, master: MasterData) -> None:
    row["Código Item"] = code
    item = master.items.get(code)
    if item is None:
        return
    row["Descrição Item"] = item.description
    row["NCM"] = item.ncm
    row["Código Serviço"] = item.service_code
    row["Código Barra"] = item.barcode
    row["Tipo Item"] = item.item_type


def _finish_row(row: dict[str, str]) -> dict[str, str]:
    cfop = row["CFOP"]
    row["Descrição CFOP"] = cfop_details(cfop)[0]
    operation = row["Tipo Operação"]
    if operation == "0":
        row["Débito/Crédito"] = "Crédito"
    elif operation == "1":
        row["Débito/Crédito"] = "Débito"
    return row


def _a_header_row(
    header: Record, master: MasterData, cnpj: str, *, compact: bool
) -> dict[str, str]:
    row = _empty_row(master, cnpj, "A100/A170")
    row["Tipo Operação"] = header.get(2)
    row["Situação"] = header.get(5)
    _add_participant(row, header.get(4), master)
    row["Série"] = header.get(6)
    if compact:
        row["Número Documento"] = header.get(7)
        row["Chave NF-e"] = header.get(8)
        row["Data Documento"] = _format_date(header.get(9))
        row["Data Entrada/Saída"] = _format_date(header.get(10))
        row["Vlr Documento"] = header.get(11)
        row["Vlr Desconto NF"] = header.get(12)
        row["Vlr Mercadoria/Operação"] = header.get(11)
    else:
        row["Número Documento"] = header.get(8)
        row["Chave NF-e"] = header.get(9)
        row["Data Documento"] = _format_date(header.get(10))
        row["Data Entrada/Saída"] = _format_date(header.get(11))
        row["Vlr Documento"] = header.get(12)
        row["Vlr Desconto NF"] = header.get(14)
        row["Vlr Mercadoria/Operação"] = header.get(12)
    return row


def _a_row(
    header: Record,
    item_record: Record,
    master: MasterData,
    cnpj: str,
) -> dict[str, str]:
    pair_lengths = (len(header.fields), len(item_record.fields))
    if pair_lengths not in {(19, 19), (21, 18)}:
        raise EFDParseError(
            f"linha {item_record.line_number}: combinação de leiautes "
            f"A100/A170 incompatível ({pair_lengths[0]}/{pair_lengths[1]} campos)"
        )
    compact = len(item_record.fields) == 19
    row = _a_header_row(header, master, cnpj, compact=compact)

    row["Número Item"] = item_record.get(2)
    _add_item(row, item_record.get(3), master)
    row["Descrição Complementar"] = item_record.get(4)
    row["Vlr Item"] = item_record.get(5)
    row["Vlr Desconto Item"] = item_record.get(6)
    if compact:
        row["Código Serviço"] = item_record.get(7)
        row["CST PIS"] = item_record.get(8)
        row["Vlr Base Cálculo PIS"] = item_record.get(9)
        row["Alíquota PIS"] = item_record.get(10)
        row["Vlr PIS"] = item_record.get(11)
        row["CST Cofins"] = item_record.get(12)
        row["Vlr Base Cálculo Cofins"] = item_record.get(13)
        row["Alíquota Cofins"] = item_record.get(14)
        row["Vlr Cofins"] = item_record.get(15)
        row["Natureza Crédito"] = item_record.get(17)
        row["Conta Contábil"] = item_record.get(18)
        row["CFOP Faturamento"] = item_record.get(19)
    else:
        row["Natureza Crédito"] = item_record.get(7)
        row["CST PIS"] = item_record.get(9)
        row["Vlr Base Cálculo PIS"] = item_record.get(10)
        row["Alíquota PIS"] = item_record.get(11)
        row["Vlr PIS"] = item_record.get(12)
        row["CST Cofins"] = item_record.get(13)
        row["Vlr Base Cálculo Cofins"] = item_record.get(14)
        row["Alíquota Cofins"] = item_record.get(15)
        row["Vlr Cofins"] = item_record.get(16)
        row["Conta Contábil"] = item_record.get(17)
    return _finish_row(row)


def _c_header_row(
    header: Record,
    master: MasterData,
    cnpj: str,
    records: str = "C100/C170",
) -> dict[str, str]:
    row = _empty_row(master, cnpj, records)
    row["Tipo Operação"] = header.get(2)
    row["Situação"] = header.get(6)
    _add_participant(row, header.get(4), master)
    row["Número Documento"] = header.get(8)
    row["Série"] = header.get(7)
    row["Chave NF-e"] = header.get(9)
    row["Data Documento"] = _format_date(header.get(10))
    row["Data Entrada/Saída"] = _format_date(header.get(11))
    row["Vlr Documento"] = header.get(12)
    row["Vlr Desconto NF"] = header.get(14)
    row["Vlr Mercadoria/Operação"] = header.get(16)
    row["Vlr Frete"] = header.get(18)
    row["Vlr Seguro"] = header.get(19)
    row["Vlr Outras DA"] = header.get(20)
    return row


def _c_row(
    header: Record,
    item_record: Record,
    master: MasterData,
    cnpj: str,
) -> dict[str, str]:
    pair_lengths = (len(header.fields), len(item_record.fields))
    if pair_lengths not in {(28, 24), (29, 37)}:
        raise EFDParseError(
            f"linha {item_record.line_number}: combinação de leiautes "
            f"C100/C170 incompatível ({pair_lengths[0]}/{pair_lengths[1]} campos)"
        )
    row = _c_header_row(header, master, cnpj)

    row["Número Item"] = item_record.get(2)
    _add_item(row, item_record.get(3), master)
    row["Descrição Complementar"] = item_record.get(4)
    row["Qtde"] = item_record.get(5)
    row["Unidade Medida"] = item_record.get(6)
    row["Vlr Item"] = item_record.get(7)
    row["Vlr Desconto Item"] = item_record.get(8)
    row["CFOP"] = item_record.get(11)

    if len(item_record.fields) >= 37:
        row["CST ICMS"] = item_record.get(10)
        row["Vlr Base Cálculo ICMS"] = item_record.get(13)
        row["Alíquota ICMS"] = item_record.get(14)
        row["Vlr ICMS"] = item_record.get(15)
        row["Vlr Base Cálculo ICMS ST"] = item_record.get(16)
        row["Alíquota ICMS ST"] = item_record.get(17)
        row["Vlr ICMS ST"] = item_record.get(18)
        row["CST IPI"] = item_record.get(20)
        row["Vlr Base Cálculo IPI"] = item_record.get(22)
        row["Alíquota IPI"] = item_record.get(23)
        row["Vlr IPI"] = item_record.get(24)
        row["CST PIS"] = item_record.get(25)
        row["Vlr Base Cálculo PIS"] = item_record.get(26)
        row["Qtde Base Cálculo PIS"] = item_record.get(28)
        row["Alíquota PIS"] = item_record.get(27)
        row["Qtde Alíquota PIS"] = item_record.get(29)
        row["Vlr PIS"] = item_record.get(30)
        row["CST Cofins"] = item_record.get(31)
        row["Vlr Base Cálculo Cofins"] = item_record.get(32)
        row["Qtde Base Cálculo Cofins"] = item_record.get(34)
        row["Alíquota Cofins"] = item_record.get(33)
        row["Qtde Alíquota Cofins"] = item_record.get(35)
        row["Vlr Cofins"] = item_record.get(36)
        row["Conta Contábil"] = item_record.get(37)
    else:
        # Variante compacta usada no TXT sintetico fornecido.
        row["CST PIS"] = item_record.get(10)
        row["Vlr Base Cálculo PIS"] = item_record.get(13)
        row["Alíquota PIS"] = item_record.get(14)
        row["Vlr PIS"] = item_record.get(15)
        row["CST Cofins"] = item_record.get(16)
        row["Vlr Base Cálculo Cofins"] = item_record.get(17)
        row["Alíquota Cofins"] = item_record.get(18)
        row["Vlr Cofins"] = item_record.get(19)
        row["Conta Contábil"] = item_record.get(20)
    return _finish_row(row)


def _copy_fields(
    row: dict[str, str], record: Record, fields: dict[str, int]
) -> None:
    for column, position in fields.items():
        value = record.get(position)
        if not row[column]:
            row[column] = value


def _document_range(initial: str, final: str) -> str:
    if initial and final and initial != final:
        return f"{initial}-{final}"
    return initial or final


def _parent_row(
    header: Record,
    master: MasterData,
    cnpj: str,
    records: str,
    context: Record | None = None,
) -> dict[str, str]:
    code = header.code
    if code == "C100":
        return _c_header_row(header, master, cnpj, records)

    row = _empty_row(master, cnpj, records)
    if code in {"C180", "C380", "C405", "C490", "C600", "C800", "C860", "D200", "D600"}:
        row["Tipo Operação"] = "1"
    elif code in {"C190", "C395", "C500"}:
        row["Tipo Operação"] = "0"

    if code in {"C180", "C190"}:
        row["Data Documento"] = _format_date(header.get(3))
        row["Data Entrada/Saída"] = _format_date(header.get(4))
        _add_item(row, header.get(5), master)
        row["NCM"] = header.get(6) or row["NCM"]
        row["Vlr Mercadoria/Operação"] = header.get(8)
    elif code == "C380":
        row["Data Documento"] = _format_date(header.get(3))
        row["Data Entrada/Saída"] = _format_date(header.get(4))
        row["Número Documento"] = _document_range(header.get(5), header.get(6))
        row["Vlr Documento"] = header.get(7)
        row["Vlr Desconto NF"] = header.get(8)
        row["Vlr Mercadoria/Operação"] = header.get(7)
    elif code == "C395":
        _add_participant(row, header.get(3), master)
        row["Série"] = header.get(4)
        row["Número Documento"] = header.get(6)
        row["Data Documento"] = _format_date(header.get(7))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Vlr Documento"] = header.get(8)
        row["Vlr Mercadoria/Operação"] = header.get(8)
    elif code == "C405":
        row["Data Documento"] = _format_date(header.get(2))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Número Documento"] = header.get(5)
        row["Vlr Documento"] = header.get(7)
        row["Vlr Mercadoria/Operação"] = header.get(7)
        if context is not None:
            row["Série"] = context.get(4)
    elif code == "C490":
        row["Data Documento"] = _format_date(header.get(2))
        row["Data Entrada/Saída"] = _format_date(header.get(3))
    elif code == "C500":
        _add_participant(row, header.get(2), master)
        row["Situação"] = header.get(4)
        row["Série"] = header.get(5)
        row["Número Documento"] = header.get(7)
        row["Data Documento"] = _format_date(header.get(8))
        row["Data Entrada/Saída"] = _format_date(header.get(9))
        row["Vlr Documento"] = header.get(10)
        row["Vlr Mercadoria/Operação"] = header.get(10)
        row["Vlr ICMS"] = header.get(11)
        row["Chave NF-e"] = header.get(15)
    elif code == "C600":
        row["Série"] = header.get(4)
        row["Data Documento"] = _format_date(header.get(9))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Vlr Documento"] = header.get(10)
        row["Vlr Desconto NF"] = header.get(11)
        row["Qtde"] = header.get(12)
        row["Vlr Mercadoria/Operação"] = header.get(13)
        row["Vlr Outras DA"] = header.get(16)
        row["Vlr Base Cálculo ICMS"] = header.get(17)
        row["Vlr ICMS"] = header.get(18)
        row["Vlr Base Cálculo ICMS ST"] = header.get(19)
        row["Vlr ICMS ST"] = header.get(20)
    elif code == "C800":
        row["Situação"] = header.get(3)
        row["Número Documento"] = header.get(4)
        row["Data Documento"] = _format_date(header.get(5))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Vlr Documento"] = header.get(6)
        row["Vlr Desconto NF"] = header.get(12)
        row["Vlr Mercadoria/Operação"] = header.get(13) or header.get(6)
        row["Vlr Outras DA"] = header.get(14)
        row["Vlr ICMS"] = header.get(15)
        row["Série"] = header.get(10)
        row["Chave NF-e"] = header.get(11)
        document = header.get(9)
        if len(document) == 11:
            row["CPF Participante"] = document
        else:
            row["CNPJ Participante"] = document
    elif code == "C860":
        row["Série"] = header.get(3)
        row["Data Documento"] = _format_date(header.get(4))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Número Documento"] = _document_range(header.get(5), header.get(6))
    elif code == "D100":
        row["Tipo Operação"] = header.get(2)
        _add_participant(row, header.get(4), master)
        row["Situação"] = header.get(6)
        row["Série"] = header.get(7)
        row["Número Documento"] = header.get(9)
        row["Chave NF-e"] = header.get(10)
        row["Data Documento"] = _format_date(header.get(11))
        row["Data Entrada/Saída"] = _format_date(header.get(12))
        row["Vlr Documento"] = header.get(15)
        row["Vlr Desconto NF"] = header.get(16)
        row["Vlr Mercadoria/Operação"] = header.get(18)
        row["Vlr Base Cálculo ICMS"] = header.get(19)
        row["Vlr ICMS"] = header.get(20)
        row["Conta Contábil"] = header.get(23)
    elif code == "D200":
        row["Situação"] = header.get(3)
        row["Série"] = header.get(4)
        row["Número Documento"] = _document_range(header.get(6), header.get(7))
        row["CFOP"] = header.get(8)
        row["Data Documento"] = _format_date(header.get(9))
        row["Data Entrada/Saída"] = row["Data Documento"]
        row["Vlr Documento"] = header.get(10)
        row["Vlr Desconto NF"] = header.get(11)
        row["Vlr Mercadoria/Operação"] = header.get(10)
    elif code == "D500":
        row["Tipo Operação"] = header.get(2)
        _add_participant(row, header.get(4), master)
        row["Situação"] = header.get(6)
        row["Série"] = header.get(7)
        row["Número Documento"] = header.get(9)
        row["Data Documento"] = _format_date(header.get(10))
        row["Data Entrada/Saída"] = _format_date(header.get(11))
        row["Vlr Documento"] = header.get(12)
        row["Vlr Desconto NF"] = header.get(13)
        row["Vlr Mercadoria/Operação"] = header.get(14)
        row["Vlr Outras DA"] = header.get(17)
        row["Vlr Base Cálculo ICMS"] = header.get(18)
        row["Vlr ICMS"] = header.get(19)
    elif code == "D600":
        row["Série"] = header.get(4)
        row["Data Documento"] = _format_date(header.get(8))
        row["Data Entrada/Saída"] = _format_date(header.get(9))
        row["Vlr Documento"] = header.get(10)
        row["Vlr Desconto NF"] = header.get(11)
        row["Vlr Mercadoria/Operação"] = header.get(12)
        row["Vlr Outras DA"] = header.get(15)
        row["Vlr Base Cálculo ICMS"] = header.get(16)
        row["Vlr ICMS"] = header.get(17)
    return row


def _direct_child_row(
    document: PendingDocument,
    child: Record,
    spec: DirectChildSpec,
    master: MasterData,
) -> dict[str, str]:
    row = _parent_row(document.record, master, document.cnpj, spec.records)
    _copy_fields(row, child, spec.fields)
    if spec.item_position is not None:
        _add_item(row, child.get(spec.item_position), master)
    return _finish_row(row)


def _tax_child_key(record: Record, positions: tuple[int, ...]) -> tuple[str, ...]:
    values: list[str] = []
    for position in positions:
        value = record.get(position)
        if re.fullmatch(r"-?\d+,\d+", value):
            value = value.rstrip("0").rstrip(",")
        values.append(value)
    return tuple(values)


def _split_tax_rows(
    group: PendingTaxGroup,
    spec: SplitChildSpec,
    master: MasterData,
) -> list[dict[str, str]]:
    cofins_by_key: defaultdict[tuple[str, ...], deque[Record]] = defaultdict(deque)
    for record in group.cofins_records:
        cofins_by_key[_tax_child_key(record, spec.key_positions)].append(record)

    pairs: list[tuple[Record | None, Record | None]] = []
    for pis in group.pis_records:
        key = _tax_child_key(pis, spec.key_positions)
        cofins = cofins_by_key[key].popleft() if cofins_by_key[key] else None
        pairs.append((pis, cofins))
    for records in cofins_by_key.values():
        pairs.extend((None, cofins) for cofins in records)

    rows: list[dict[str, str]] = []
    for pis, cofins in pairs:
        row = _parent_row(
            group.record,
            master,
            group.cnpj,
            spec.records,
            group.context,
        )
        if pis is not None:
            _copy_fields(row, pis, spec.pis_fields)
        if cofins is not None:
            _copy_fields(row, cofins, spec.cofins_fields)
        detail = pis or cofins
        if detail is not None and spec.item_position is not None:
            _add_item(row, detail.get(spec.item_position), master)
        participant = row["CNPJ Participante"]
        if len(participant) == 11:
            row["CPF Participante"] = participant
            row["CNPJ Participante"] = ""
        rows.append(_finish_row(row))
    return rows


def _f100_row(record: Record, master: MasterData, cnpj: str) -> dict[str, str]:
    row = _empty_row(master, cnpj, "F100")
    row["Tipo Operação"] = record.get(2)
    _add_participant(row, record.get(3), master)
    row["Data Documento"] = _format_date(record.get(5))
    row["Data Entrada/Saída"] = row["Data Documento"]

    official = len(record.fields) == 19
    if official:
        _add_item(row, record.get(4), master)
        amount = record.get(6)
        row["Descrição Complementar"] = record.get(19)
        row["Natureza Crédito"] = record.get(15)
        row["CST PIS"] = record.get(7)
        row["Vlr Base Cálculo PIS"] = record.get(8)
        row["Alíquota PIS"] = record.get(9)
        row["Vlr PIS"] = record.get(10)
        row["CST Cofins"] = record.get(11)
        row["Vlr Base Cálculo Cofins"] = record.get(12)
        row["Alíquota Cofins"] = record.get(13)
        row["Vlr Cofins"] = record.get(14)
        row["Conta Contábil"] = record.get(17)
    else:
        # Variante compacta: valores de debito e credito em colunas separadas.
        amount = record.get(7) if record.get(2) in {"1", "2"} else record.get(8)
        row["Descrição Complementar"] = record.get(4)
        row["Código Serviço"] = record.get(6)
        row["Número Documento"] = record.get(19)
        row["Natureza Crédito"] = record.get(17)
        row["CST PIS"] = record.get(9)
        row["Vlr Base Cálculo PIS"] = record.get(10)
        row["Alíquota PIS"] = record.get(11)
        row["Vlr PIS"] = record.get(12)
        row["CST Cofins"] = record.get(13)
        row["Vlr Base Cálculo Cofins"] = record.get(14)
        row["Alíquota Cofins"] = record.get(15)
        row["Vlr Cofins"] = record.get(16)
        row["Conta Contábil"] = record.get(18)

    row["Vlr Mercadoria/Operação"] = amount
    if row["Código Item"]:
        row["Vlr Item"] = amount
    return _finish_row(row)


def _f_consolidated_row(
    record: Record, master: MasterData, cnpj: str
) -> dict[str, str]:
    row = _empty_row(master, cnpj, record.code)
    row["Tipo Operação"] = "1"
    amount = record.get(2)
    row["Vlr Mercadoria/Operação"] = amount
    row["CST PIS"] = record.get(3)
    row["Vlr Base Cálculo PIS"] = record.get(5)
    row["Alíquota PIS"] = record.get(6)
    row["Vlr PIS"] = record.get(7)
    row["CST Cofins"] = record.get(8)
    row["Vlr Base Cálculo Cofins"] = record.get(10)
    row["Alíquota Cofins"] = record.get(11)
    row["Vlr Cofins"] = record.get(12)
    row["CFOP"] = record.get(14)
    row["Conta Contábil"] = record.get(15)
    row["Descrição Complementar"] = record.get(16)
    row = _finish_row(row)
    taxed_revenue_csts = {"01", "02", "03", "05"}
    if not ({row["CST PIS"], row["CST Cofins"]} & taxed_revenue_csts):
        row["Débito/Crédito"] = ""
    return row


def _analytical_rows(records: list[Record], master: MasterData) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    pending: dict[str, PendingDocument | None] = {"A": None, "C": None}
    current_cnpj = {
        "A": master.cnpj,
        "C": master.cnpj,
        "D": master.cnpj,
        "F": master.cnpj,
    }
    direct_document: PendingDocument | None = None
    tax_group: PendingTaxGroup | None = None
    c400: Record | None = None

    def flush(block: str) -> None:
        # O escopo exige os pares completos. Cabecalhos sem item podem ser
        # documentos cancelados ou modelos detalhados por outro registro e nao
        # devem gerar uma linha analitica ficticia.
        pending[block] = None

    def flush_tax_group() -> None:
        nonlocal tax_group
        if tax_group is None:
            return
        spec = SPLIT_CHILD_SPECS[tax_group.record.code]
        rows.extend(_split_tax_rows(tax_group, spec, master))
        tax_group = None

    for record in records:
        if record.code in LEVEL_THREE_PARENTS:
            flush_tax_group()
            direct_document = None
            if record.code != "C400":
                c400 = None
            if record.code.startswith("A"):
                flush("A")
            elif record.code.startswith("C"):
                flush("C")

        if record.code in {"A010", "C010", "D010", "F010"}:
            flush_tax_group()
            direct_document = None
            block = record.code[0]
            if block in pending:
                flush(block)
            current_cnpj[block] = record.get(2) or master.cnpj
        elif record.code == "A100":
            pending["A"] = PendingDocument(record, current_cnpj["A"])
        elif record.code == "A170":
            document = pending["A"]
            if document is None:
                raise EFDParseError(
                    f"linha {record.line_number}: A170 sem um A100 anterior"
                )
            rows.append(_a_row(document.record, record, master, document.cnpj))
        elif record.code == "A990":
            flush("A")
        elif record.code == "C100":
            pending["C"] = PendingDocument(record, current_cnpj["C"])
            direct_document = pending["C"]
        elif record.code == "C170":
            document = pending["C"]
            if document is None:
                raise EFDParseError(
                    f"linha {record.line_number}: C170 sem um C100 anterior"
                )
            rows.append(_c_row(document.record, record, master, document.cnpj))
        elif record.code in DIRECT_CHILD_SPECS:
            spec = DIRECT_CHILD_SPECS[record.code]
            if direct_document is None or direct_document.record.code != spec.parent:
                raise EFDParseError(
                    f"linha {record.line_number}: {record.code} sem um "
                    f"{spec.parent} anterior"
                )
            rows.append(_direct_child_row(direct_document, record, spec, master))
        elif record.code == "C400":
            c400 = record
        elif record.code == "C405":
            flush_tax_group()
            if c400 is None:
                raise EFDParseError(
                    f"linha {record.line_number}: C405 sem um C400 anterior"
                )
            tax_group = PendingTaxGroup(
                record,
                current_cnpj["C"],
                [],
                [],
                c400,
            )
        elif record.code in SPLIT_CHILD_SPECS:
            tax_group = PendingTaxGroup(
                record,
                current_cnpj[record.code[0]],
                [],
                [],
            )
        elif record.code in SPLIT_CHILD_TO_PARENT:
            parent = SPLIT_CHILD_TO_PARENT[record.code]
            if tax_group is None or tax_group.record.code != parent:
                raise EFDParseError(
                    f"linha {record.line_number}: {record.code} sem um "
                    f"{parent} anterior"
                )
            spec = SPLIT_CHILD_SPECS[parent]
            target = (
                tax_group.pis_records
                if record.code == spec.pis_code
                else tax_group.cofins_records
            )
            target.append(record)
        elif record.code in {"C395", "C800", "C860"}:
            direct_document = PendingDocument(record, current_cnpj["C"])
        elif record.code in {"C990", "D990"}:
            flush_tax_group()
            direct_document = None
            if record.code == "C990":
                flush("C")
        elif record.code == "F100":
            if record.get(2) in {"1", "2"}:
                rows.append(_f100_row(record, master, current_cnpj["F"]))
        elif record.code == "F550":
            rows.append(_f_consolidated_row(record, master, current_cnpj["F"]))

    flush_tax_group()
    flush("A")
    flush("C")
    return rows


def convert_file(
    input_path: str | Path,
    output_path: str | Path,
    *,
    delimiter: str = ";",
) -> ConversionResult:
    """Converte ``input_path`` e grava o CSV analitico em ``output_path``."""

    source = Path(input_path).expanduser().resolve()
    target = Path(output_path).expanduser().resolve()
    if source == target:
        raise ValueError("o arquivo de saída não pode ser o próprio arquivo EFD")
    if len(delimiter) != 1:
        raise ValueError("o separador do CSV deve ter exatamente um caractere")

    text, encoding = _decode_input(source)
    records = _parse_records(text)
    _validate_supported_layouts(records)
    master = _master_data(records)
    rows = _analytical_rows(records, master)
    _validate_contribution_file(records, master)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8-sig", newline="") as csv_file:
        writer = csv.DictWriter(
            csv_file,
            fieldnames=COLUMNS,
            delimiter=delimiter,
            lineterminator="\n",
        )
        writer.writeheader()
        writer.writerows(rows)

    observed = Counter(row["Registros"] for row in rows)
    counts = {name: observed.get(name, 0) for name in SUPPORTED_OUTPUTS}
    return ConversionResult(
        target,
        len(rows),
        counts,
        encoding,
        master.period,
        master.cnpj,
    )
