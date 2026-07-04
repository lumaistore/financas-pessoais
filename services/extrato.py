"""Importação de extrato bancário como despesas manuais.

Filtra por mês, sugere categoria por palavras-chave (aproveitando o
categorizador do cartão) e evita importar duplicatas (data + valor + descrição).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import Movimentacao
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
    """Chaves das movimentações já cadastradas no mês (evita duplicar)."""
    with get_session() as s:
        stmt = select(Movimentacao).where(Movimentacao.mes_referencia == mes_ref)
        return {
            _chave(d.data, d.valor, d.descricao)
            for d in s.scalars(stmt).all()
        }


def marcar_duplicatas(lancamentos: List[LancamentoExtrato], mes_ref: str,
                      conta_origem_id: Optional[int] = None) -> List[dict]:
    """Devolve os lançamentos como dicts prontos para revisão na UI, com:
    - detecção de duplicata (mesmo do modelo antigo)
    - classificação automática (receita/despesa/transferência/aplicação)
      baseada nas contas cadastradas do usuário.
    """
    from services.movimentacoes import classificar, existe as existe_mov

    ja_tem = existentes(mes_ref)
    saida = []
    for l in lancamentos:
        chave = _chave(l.data, l.valor, l.descricao)
        # Classificação inteligente unificada (inclui "FATURA PAGA")
        tipo, destino_id = classificar(l.descricao, l.valor, conta_origem_id)
        # Checa duplicata também na nova tabela Movimentacao
        dup_nova = existe_mov(l.data, abs(l.valor), l.descricao)
        saida.append({
            "data": l.data,
            "descricao": l.descricao,
            "valor": abs(l.valor),
            "tipo": tipo,
            "forma": _forma_provavel(l.descricao),
            "categoria": sugerir_categoria(l.descricao) or "Outros",
            "importar": (chave not in ja_tem) and (not dup_nova) and tipo != "transferencia",
            "duplicado": (chave in ja_tem) or dup_nova,
            "conta_destino_id": destino_id,
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
def importar(linhas: List[dict], conta_origem_id: Optional[int] = None,
             origem_texto: str = "extrato") -> int:
    """Insere no banco as linhas marcadas com importar=True como
    Movimentacao (com tipo classificado). Retorna quantas foram inseridas."""
    from services.movimentacoes import adicionar

    n = 0
    for ln in linhas:
        if not ln.get("importar"):
            continue
        adicionar(
            data_=ln["data"],
            descricao=ln["descricao"],
            valor=float(ln["valor"]),
            tipo=ln.get("tipo") or "despesa",
            forma=ln.get("forma") or None,
            categoria=(ln.get("categoria") or None) if ln.get("categoria") not in (None, "(sem)") else None,
            conta_id=conta_origem_id,
            conta_destino_id=ln.get("conta_destino_id"),
            lumai=bool(ln.get("lumai")),
            origem=origem_texto,
        )
        n += 1
    return n
