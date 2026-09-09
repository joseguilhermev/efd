"""Posições dos documentos e resumos nos guias SPED ICMS 3.2.3 / Contribuições 1.35.

Campos não existentes no leiaute não são tratados como divergências.
Registros auxiliares não representam outra nota; códigos desconhecidos são expostos.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class DocumentLayout:
    lengths: tuple[int, ...]
    fields: dict[str, int]
    fixed: dict[str, str] = field(default_factory=dict)


C100 = DocumentLayout((29,), dict(
    operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
    number=8, key=9, document_date=10, entry_exit_date=11, amount=12,
))
D100 = DocumentLayout((23, 25), dict(
    operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
    subseries=8, number=9, key=10, document_date=11, entry_exit_date=12, amount=15,
))
D500 = DocumentLayout((24,), dict(
    operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
    subseries=8, number=9, document_date=10, entry_exit_date=11, amount=12,
))
C800 = DocumentLayout((17,), dict(
    model=2, situation=3, number=4, document_date=5, amount=6,
    participant_tax_id=9, equipment=10, key=11,
), dict(operation="1", issuer="0"))
CANCELLED_PARENTS = {"C310": "C300", "C601": "C600", "D301": "D300", "D411": "D410"}

ICMS_DOCUMENTS = {
    **{code: DocumentLayout((2,), dict(number=2), dict(operation="1", issuer="0", situation="02"))
       for code in CANCELLED_PARENTS},
    "B020": DocumentLayout((21,), dict(
        operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
        number=8, key=9, document_date=10, amount=12,
    )),
    "C100": C100,
    "C350": DocumentLayout((12,), dict(
        series=2, subseries=3, number=4, document_date=5, participant_tax_id=6, amount=8,
    ), dict(model="02", operation="1", issuer="0")),
    "C460": DocumentLayout((10,), dict(
        model=2, situation=3, number=4, document_date=5, amount=6, participant_tax_id=9,
    ), dict(operation="1", issuer="0")),
    "C500": DocumentLayout((27, 40), dict(
        operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
        subseries=8, number=10, document_date=11, entry_exit_date=12, amount=13, key=28,
    )),
    "C800": C800,
    "D100": D100,
    "D500": D500,
    "D700": DocumentLayout((32,), dict(
        operation=2, issuer=3, participant=4, model=5, situation=6, series=7,
        number=8, document_date=9, entry_exit_date=10, amount=11, key=22,
    )),
}

CONTRIBUTION_DOCUMENTS = {
    "A100": DocumentLayout((21,), dict(
        operation=2, issuer=3, participant=4, situation=5, series=6, subseries=7,
        number=8, key=9, document_date=10, entry_exit_date=11, amount=12,
    )),
    "C100": DocumentLayout((28, 29), C100.fields),
    "C395": DocumentLayout((8,), dict(
        model=2, participant=3, series=4, subseries=5, number=6, document_date=7, amount=8,
    ), dict(operation="0", issuer="1")),
    "C500": DocumentLayout((14, 15), dict(
        participant=2, model=3, situation=4, series=5, subseries=6, number=7,
        document_date=8, entry_exit_date=9, amount=10, key=15,
    ), dict(operation="0", issuer="1")),
    "C800": C800,
    "D100": DocumentLayout((23,), D100.fields),
    "D500": DocumentLayout((22,), D500.fields),
}
COMPACT_A100 = DocumentLayout((19,), dict(
    operation=2, issuer=3, participant=4, situation=5, series=6,
    number=7, key=8, document_date=9, entry_exit_date=10, amount=11,
))

# Uma faixa ou um total não comprova a inclusão de cada documento individual.
ICMS_SUMMARIES = {
    "B030": DocumentLayout((12,), dict(model=2, series=3, number=4, end_number=5, document_date=6, amount=8)),
    "B350": DocumentLayout((), {}),
    "C300": DocumentLayout((11,), dict(model=2, series=3, subseries=4, number=5, end_number=6, document_date=7, amount=8)),
    "C405": DocumentLayout((7,), dict(document_date=2, amount=7)),
    "C495": DocumentLayout((15,), dict(amount=7)),
    "C600": DocumentLayout((22,), dict(model=2, series=4, subseries=5, document_date=9, amount=10)),
    "C700": DocumentLayout((9,), dict(model=2, series=3, document_date=6, end_date=7)),
    "C860": DocumentLayout((6,), dict(model=2, equipment=3, document_date=4, number=5, end_number=6)),
    "D300": DocumentLayout((20,), dict(model=2, series=3, subseries=4, number=5, end_number=6, document_date=10, amount=11)),
    "D355": DocumentLayout((7,), dict(document_date=2, amount=7)),
    "D400": DocumentLayout((16,), dict(participant=2, model=3, situation=4, series=5, subseries=6, number=7, document_date=8, amount=9)),
    "D410": DocumentLayout((15,), dict(model=2, series=3, subseries=4, number=5, end_number=6, document_date=7, amount=11)),
    "D600": DocumentLayout((18,), dict(model=2, series=4, subseries=5, document_date=8, amount=9)),
    "D695": DocumentLayout((9,), dict(model=2, series=3, document_date=6, end_date=7)),
    "D750": DocumentLayout((17,), dict(model=2, series=3, document_date=4, amount=7)),
}
CONTRIBUTION_SUMMARIES = {
    "C180": DocumentLayout((8,), dict(model=2, document_date=3, end_date=4, amount=8), dict(operation="1")),
    "C190": DocumentLayout((8,), dict(model=2, document_date=3, end_date=4, amount=8)),
    "C380": DocumentLayout((8,), dict(model=2, document_date=3, end_date=4, number=5, end_number=6, amount=7), dict(operation="1")),
    "C405": ICMS_SUMMARIES["C405"],
    "C490": DocumentLayout((4,), dict(model=4, document_date=2, end_date=3), dict(operation="1")),
    "C600": ICMS_SUMMARIES["C600"],
    "C860": ICMS_SUMMARIES["C860"],
    "D200": DocumentLayout((11,), dict(model=2, situation=3, series=4, subseries=5, number=6, end_number=7, document_date=9, amount=10), dict(operation="1")),
    "D300": DocumentLayout((19,), dict(model=2, series=3, subseries=4, number=5, end_number=6, document_date=8, amount=9), dict(operation="1")),
    "D350": DocumentLayout((23,), dict(model=2, equipment=4, document_date=5, amount=10), dict(operation="1")),
    "D600": DocumentLayout((19,), dict(model=2, series=4, subseries=5, document_date=8, end_date=9, amount=10), dict(operation="1")),
    "F100": DocumentLayout((19, 20), dict(operation=2, participant=3, document_date=5)),
    "F500": DocumentLayout((16,), dict(model=13, amount=2), dict(operation="1")),
    "F510": DocumentLayout((), {}, dict(operation="1")),
    "F550": DocumentLayout((16,), dict(model=13, amount=2), dict(operation="1")),
    "F560": DocumentLayout((), {}, dict(operation="1")),
}

# Detalhes, referências, equipamentos e apurações: não contar como novas notas.
ICMS_AUXILIARY = set("""
B001 B025 B035 B420 B440 B460 B470 B500 B510 B990
C001 C101 C105 C110 C111 C112 C113 C114 C115 C116 C120 C130 C140 C141
C160 C165 C170 C171 C172 C173 C174 C175 C176 C177 C178 C179 C180 C181
C185 C186 C190 C191 C195 C197 C310 C320 C321 C330 C370 C380 C390 C400
C410 C420 C425 C430 C465 C470 C480 C490 C510 C590 C591 C595 C597
C601 C610 C690 C790 C791 C810 C815 C850 C855 C857 C870 C880 C890 C895 C897 C990
D001 D101 D110 D120 D130 D140 D150 D160 D161 D162 D170 D180 D190 D195 D197
D301 D310 D350 D360 D365 D370 D390 D411 D420 D510 D530 D590 D610 D690
D696 D697 D730 D731 D735 D737 D760 D761 D990
""".split())
CONTRIBUTION_AUXILIARY = set("""
A001 A010 A110 A111 A120 A170 A990
C001 C010 C110 C111 C120 C170 C175 C181 C185 C188 C191 C195 C198 C199
C381 C385 C396 C400 C481 C485 C489 C491 C495 C499 C501 C505 C509 C601 C605 C609
C810 C820 C830 C870 C880 C890 C990
D001 D010 D101 D105 D111 D201 D205 D209 D309 D359 D501 D505 D509 D601 D605 D609 D990
F001 F010 F111 F120 F129 F130 F139 F150 F200 F205 F210 F211 F600 F700 F800 F990
F509 F519 F525 F559 F569
""".split())
