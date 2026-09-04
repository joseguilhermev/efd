from __future__ import annotations


def cnpj_root(cnpj: str) -> str:
    """Retorna a raiz de oito posições do CNPJ informado no SPED."""

    return cnpj.strip()[:8]
