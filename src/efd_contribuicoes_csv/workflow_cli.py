from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from .comparison import EFDComparisonError
from .converter import EFDParseError
from .scope import ScopeMonth
from .workflow import (
    EFDInventoryError,
    discover_annual_efd_input,
    process_annual_efd_input,
)


def _cfop_codes(value: str) -> tuple[str, ...]:
    codes = tuple(code.strip() for code in value.split(",") if code.strip())
    if not codes or any(not re.fullmatch(r"\d{4}", code) for code in codes):
        raise argparse.ArgumentTypeError(
            "informe CFOPs com quatro dígitos, separados por vírgula"
        )
    return codes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="efd-processar",
        description=(
            "Consolida um ano de EFD Contribuições, cria indicadores por "
            "período e valida notas existentes na EFD ICMS/IPI."
        ),
    )
    parser.add_argument(
        "entrada",
        type=Path,
        help=(
            "pasta que contém as subpastas efd_contribuicoes e efd_icms"
        ),
    )
    parser.add_argument(
        "-o",
        "--diretorio-saida",
        type=Path,
        help="diretório dos CSVs (padrão: <entrada>/resultado)",
    )
    parser.add_argument(
        "--continuar-com-ausentes",
        action="store_true",
        help="processa sem pedir confirmação quando faltarem meses",
    )
    parser.add_argument(
        "--cfop-incluir",
        action="append",
        default=[],
        type=_cfop_codes,
        metavar="CODIGO[,CODIGO...]",
    )
    parser.add_argument(
        "--cfop-excluir",
        action="append",
        default=[],
        type=_cfop_codes,
        metavar="CODIGO[,CODIGO...]",
    )
    parser.add_argument(
        "--separador",
        choices=(";", ",", "tab"),
        default=";",
        help="separador dos CSVs (padrão: ';')",
    )
    return parser


def _month_list(months: tuple[ScopeMonth, ...]) -> str:
    return ", ".join(f"{month.month:02d}/{month.year}" for month in months)


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.diretorio_saida or args.entrada / "resultado"
    delimiter = "\t" if args.separador == "tab" else args.separador
    include = {code for group in args.cfop_incluir for code in group}
    exclude = {code for group in args.cfop_excluir for code in group}
    try:
        inventory = discover_annual_efd_input(args.entrada)
    except EFDInventoryError as exc:
        print("Inconsistências encontradas:", file=sys.stderr)
        for issue in exc.issues:
            print(f"- {issue}", file=sys.stderr)
        return 2

    print(f"Ano identificado: {inventory.year}")
    print(f"CNPJ: {inventory.cnpj}")
    print(f"EFD Contribuições: {len(inventory.contributions)}/12 períodos")
    print(f"EFD ICMS/IPI: {len(inventory.icms)}/12 períodos")
    if inventory.has_missing_months:
        print("Inconsistências encontradas:")
        if inventory.missing_contributions:
            print(
                "- EFD Contribuições ausente: "
                + _month_list(inventory.missing_contributions)
            )
        if inventory.missing_icms:
            print("- EFD ICMS/IPI ausente: " + _month_list(inventory.missing_icms))
        if not args.continuar_com_ausentes:
            try:
                answer = input("Continuar mesmo assim? [s/N] ").strip().casefold()
            except EOFError:
                answer = ""
            if answer not in {"s", "sim"}:
                print("Processamento cancelado; nenhum CSV foi gerado ou alterado.")
                return 1

    try:
        result = process_annual_efd_input(
            inventory,
            output,
            delimiter=delimiter,
            cfop_include=include,
            cfop_exclude=exclude,
        )
    except (EFDComparisonError, EFDParseError, OSError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    print(f"Fluxo concluído: {result.output_directory}")
    print(
        f"Contribuições: {result.conversion.rows} linhas analíticas; "
        f"{result.indicators.rows} linhas de indicadores"
    )
    print(
        f"Comparação: {result.comparison.rows} notas; "
        f"{result.missing_notes} não lançadas na EFD Contribuições"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
