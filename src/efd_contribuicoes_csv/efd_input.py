"""Leitura da escrituração sem o conteúdo anexado após o encerramento."""

import re
from pathlib import Path


def read_efd_bytes(path: Path) -> bytes:
    raw = path.read_bytes()
    closing = re.search(rb"(?m)^\|?9999\|[0-9]+\|?\r?$", raw)
    # Cortar antes de decodificar evita que bytes da assinatura alterem a
    # detecção de UTF-8 do texto fiscal.
    return raw[:closing.end()] if closing else raw
