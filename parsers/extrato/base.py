"""Estruturas comuns dos parsers de extrato bancário."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import List, Optional


@dataclass
class LancamentoExtrato:
    data: date
    descricao: str
    valor: float  # positivo = crédito (recebimento); negativo = débito (despesa)


@dataclass
class ExtratoLido:
    banco: str
    lancamentos: List[LancamentoExtrato]


def _parse_valor_br(t: str) -> Optional[float]:
    """Converte '1.234,56' ou '-1.234,56' para float."""
    t = (t or "").strip().replace("R$", "").replace(" ", "")
    if not t:
        return None
    negativo = t.startswith("-")
    t = t.lstrip("-+")
    t = t.replace(".", "").replace(",", ".")
    try:
        return -float(t) if negativo else float(t)
    except ValueError:
        return None
