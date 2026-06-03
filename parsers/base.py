"""Estruturas e contrato comum dos parsers de fatura (Fase 3).

Cada banco tem um parser próprio (layouts diferentes). Todos retornam o mesmo
formato (`FaturaExtraida`), então o resto do sistema não precisa saber de qual
banco veio o PDF. Para adicionar um banco novo, crie um parser que implemente
`detectar` e `extrair` e registre em `parsers/registry.py`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Protocol


@dataclass
class TransacaoExtraida:
    data: date
    descricao: str
    valor: float  # positivo = gasto (débito); negativo = crédito/estorno
    parcela: Optional[str] = None  # ex.: "04/06" (parcela 4 de 6)
    categoria_sugerida: Optional[str] = None


@dataclass
class FaturaExtraida:
    banco: str
    transacoes: List[TransacaoExtraida] = field(default_factory=list)
    vencimento: Optional[date] = None
    mes_referencia: Optional[str] = None  # AAAA-MM


class ParserFatura(Protocol):
    banco: str

    def detectar(self, texto: str) -> bool:
        """Retorna True se este parser reconhece o banco pelo texto do PDF."""
        ...

    def extrair(self, pdf_path: str) -> FaturaExtraida:
        ...


# ---------------------------------------------------------------------------
# Utilitários compartilhados
# ---------------------------------------------------------------------------
def parse_valor_br(texto: str) -> float:
    """Converte '1.160,70' -> 1160.70 e '-2.231,05' -> -2231.05."""
    t = texto.strip().replace("R$", "").replace(" ", "")
    negativo = t.startswith("-")
    t = t.lstrip("-+")
    t = t.replace(".", "").replace(",", ".")
    valor = float(t)
    return -valor if negativo else valor


def inferir_ano(mes: int, vencimento: Optional[date]) -> int:
    """Datas das faturas vêm como DD/MM (sem ano). Infere o ano: se o mês da
    transação é maior que o do vencimento, assume o ano anterior."""
    if vencimento is None:
        hoje = date.today()
        ref_ano, ref_mes = hoje.year, hoje.month
    else:
        ref_ano, ref_mes = vencimento.year, vencimento.month
    return ref_ano - 1 if mes > ref_mes else ref_ano
