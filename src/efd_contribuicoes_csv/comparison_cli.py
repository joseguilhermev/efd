from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from .comparison import EFDComparisonError, compare_efd_files


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="efd-comparar-notas",
        description=(
            "Compara as notas C100 distintas da EFD Contribuições com a EFD ICMS/IPI."
        ),
    )
    parser.add_argument("efd_contribuicoes", type=Path)
    parser.add_argument("efd_icms", type=Path)
    parser.add_argument(
        "-o",
        "--saida",
        type=Path,
        help="CSV de saída (padrão: <efd_contribuicoes>_comparacao_icms.csv)",
    )
    parser.add_argument(
        "--separador",
        choices=(";", ",", "tab"),
        default=";",
        help="separador do CSV (padrão: ';')",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    output = args.saida or args.efd_contribuicoes.with_name(
        f"{args.efd_contribuicoes.stem}_comparacao_icms.csv"
    )
    delimiter = "\t" if args.separador == "tab" else args.separador

    try:
        result = compare_efd_files(
            args.efd_contribuicoes,
            args.efd_icms,
            output,
            delimiter=delimiter,
        )
    except (EFDComparisonError, OSError, ValueError) as exc:
        print(f"erro: {exc}", file=sys.stderr)
        return 2

    details = ", ".join(
        f"{status}={count}" for status, count in result.by_status.items()
    )
    print(
        f"Comparação criada: {result.output_path} "
        f"({result.rows} notas distintas; {details})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
