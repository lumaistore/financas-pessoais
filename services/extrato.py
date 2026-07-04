"""Importação de extrato bancário como despesas manuais.

Filtra por mês, sugere categoria por palavras-chave (aproveitando o
categorizador do cartão) e evita importar duplicatas (data + valor + descrição).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import DespesaManual
from parsers.categorizador import CATEGORIAS_PADRAO, sugerir_categoria
from parsers.extrato.base import LancamentoExtrato
from parsers.extrato.registry import extrair as _extrair


def ler_extrato(dados: bytes, nome_arquivo: str, senha: str = ""):
    """Extrai lançamentos de um arquivo de extrato. Devolve o objeto
    ExtratoLido (com banco e lista) ou None se não reconhecer o formato.
    `senha` só é usada em PDFs protegidos."""
    return _extrair(dados, nome_arquivo, senha=senha)


def pdf_pede_senha(dados: bytes) -> bool:
    from parsers.extrato.registry import pdf_pede_senha as _p
    return _p(dados)


def meses_disponiveis(lancamentos: List[LancamentoExtrato]) -> List[str]:
    """Meses AAAA-MM presentes nos lançamentos, do mais recente ao mais antigo."""
    ms = sorted({l.data.strftime("%Y-%m") for l in lancamentos}, reverse=True)
    return ms


def filtrar(lancamentos: List[LancamentoExtrato], mes_ref: str,
            apenas_debitos: bool = True) -> List[LancamentoExtrato]:
    """Aplica os filtros: mês (AAAA-MM) e opcionalmente só débitos (despesa)."""
    out = []
    for l in lancamentos:
        if l.data.strftime("%Y-%m") != mes_ref:
            continue
        if apenas_debitos and l.valor >= 0:
            continue
        out.append(l)
    return out


# ---------------------------------------------------------------------------
# Duplicatas
# ---------------------------------------------------------------------------
def _chave(d: date, valor: float, desc: str) -> str:
    return f"{d.isoformat()}|{round(abs(valor), 2)}|{desc.strip().lower()[:40]}"


def existentes(mes_ref: str) -> set:
    """Chaves das despesas já cadastradas no mês (para evitar duplicar)."""
    with get_session() as s:
        stmt = select(DespesaManual).where(DespesaManual.mes_referencia == mes_ref)
        return {
            _chave(d.data, d.valor, d.descricao)
            for d in s.scalars(stmt).all()
        }


def marcar_duplicatas(lancamentos: List[LancamentoExtrato], mes_ref: str) -> List[dict]:
    """Devolve os lançamentos como dicts prontos para revisão na UI, marcando
    quem parece duplicado do que já está no banco."""
    ja_tem = existentes(mes_ref)
    saida = []
    for l in lancamentos:
        chave = _chave(l.data, l.valor, l.descricao)
        saida.append({
            "data": l.data,
            "descricao": l.descricao,
            "valor": abs(l.valor),  # despesa é sempre positivo no cadastro
            "forma": _forma_provavel(l.descricao),
            "categoria": sugerir_categoria(l.descricao) or "Outros",
            "importar": chave not in ja_tem,
            "duplicado": chave in ja_tem,
            "lumai": False,
        })
    return saida


def _forma_provavel(desc: str) -> str:
    """Chuta a forma pelo texto (PIX/boleto/débito/outros)."""
    d = (desc or "").lower()
    if "pix" in d:
        return "pix"
    if "boleto" in d or "cobranca" in d:
        return "boleto"
    if any(x in d for x in ("compra", "debito", "débito", "cartao")):
        return "débito"
    return "outros"


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------
def importar(linhas: List[dict]) -> int:
    """Insere no banco as linhas marcadas com importar=True. Retorna quantas
    foram inseridas."""
    from services.despesas import adicionar_despesa

    n = 0
    for ln in linhas:
        if not ln.get("importar"):
            continue
        adicionar_despesa(
            data_=ln["data"],
            descricao=ln["descricao"],
            valor=float(ln["valor"]),
            forma=ln.get("forma") or "outros",
            categoria=(ln.get("categoria") or None) if ln.get("categoria") != "(sem)" else None,
            lumai=bool(ln.get("lumai")),
        )
        n += 1
    return n
