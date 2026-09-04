from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Sequence
from pathlib import Path

from .converter import EFDParseError, convert_file
from .indicators import generate_indicator_csv
from .scope import build_scope, validate_period_in_scope


def _cfop_codes(value: str) -> tuple[str, ...]:
    codes = tuple(code.strip() for code in value.split(",") if code.strip())
    invalid = [code for code in codes if not re.fullmatch(r"\d{4}", code)]
    if not codes or invalid:
        raise argparse.ArgumentTypeError(
            "informe CFOPs com quatro dígitos, separados por vírgula"
        )
    return codes


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="efd-contribuicoes-csv",
        description=(
            "Converte uma EFD Contribuicoes em CSV analitico, unindo os "
            "registros pai/filho operacionais dos blocos A, C e D e "
            "incluindo F100 e F550."
        ),
    )
    parser.add_argument(
        "arquivo_efd", type=Path, help="arquivo TXT da EFD Contribuicoes"
    )
    parser.add_argument(
        "-o",
        "--saida",
        type=Path,
        help="arquivo CSV de saida (padrao: <entrada>_analitico.csv)",
    )
    parser.add_argument(
        "--separador",
        choices=(";", ",", "tab"),
        default=";",
        help="separador do CSV (padrao: ';')",
    )
    parser.add_argument(
        "--saida-indicadores",
        type=Path,
        help="CSV de indicadores (padrao: <saida>_indicadores.csv)",
    )
    parser.add_argument(
        "--cfop-incluir",
        action="append",
        default=[],
        type=_cfop_codes,
        metavar="CODIGO[,CODIGO...]",
        help="CFOPs aceitos nas vendas de produtos; pode ser repetido",
    )
    parser.add_argument(
        "--cfop-excluir",
        action="append",
        default=[],
        type=_cfop_codes,
        metavar="CODIGO[,CODIGO...]",
        help="CFOPs retirados das vendas de produtos; pode ser repetido",
    )
    parser.add_argument(
        "--periodo-inicial",
        metavar="MM/AAAA",
        help="primeiro mês do escopo; exige --periodo-final",
    )
    parser.add_argument(
        "--periodo-final",
        metavar="MM/AAAA",
        help="último mês do escopo; exige --periodo-inicial",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output_path = args.saida or args.arquivo_efd.with_name(
        f"{args.arquivo_efd.stem}_analitico.csv"
    )
    indicator_stem = output_path.stem.removesuffix("_analitico")
    indicator_path = args.saida_indicadores or output_path.with_name(
        f"{indicator_stem}_indicadores.csv"
    )
    delimiter = "\t" if args.separador == "tab" else args.separador
    cfop_include = {code for group in args.cfop_incluir for code in group}
    cfop_exclude = {code for group in args.cfop_excluir for code in group}

    try:
        if (
            indicator_path.expanduser().resolve()
            == args.arquivo_efd.expanduser().resolve()
        ):
            raise ValueError("o CSV de indicadores não pode sobrescrever o arquivo EFD")
        result = convert_file(args.arquivo_efd, output_path, delimiter=delimiter)
        scope = build_scope(
            args.periodo_inicial,
            args.periodo_final,
            fallback_period=result.period,
        )
        validate_period_in_scope(result.period, scope)
        indicator_result = generate_indicator_csv(
            result.output_path,
            indicator_path,
            delimiter=delimiter,
            cfop_include=cfop_include,
            cfop_exclude=cfop_exclude,
            expected_periods=tuple(month.label for month in scope),
            scope_cnpj=result.cnpj,
        )
    except (EFDParseError, OSError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    details = ", ".join(f"{name}={count}" for name, count in result.by_record.items())
    print(
        f"CSV criado: {result.output_path} "
        f"(período={result.period or 'não informado'}; {result.rows} linhas; {details})"
    )
    indicator_details = ", ".join(
        f"{name}={count}" for name, count in indicator_result.by_indicator.items()
    )
    print(
        f"Indicadores criados: {indicator_result.output_path} "
        f"({indicator_result.rows} linhas agrupadas; {indicator_details})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
