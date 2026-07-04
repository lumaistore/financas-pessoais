"""Movimentações financeiras unificadas — substitui receitas + despesas.

Um único fluxo: cada linha é uma entrada OU saída, com tipo classificado:
- receita         : entrou dinheiro real (salário, LUMAI, venda)
- despesa         : saiu dinheiro real
- transferencia   : entre próprias contas (ignorada em totais do painel)
- aplicacao       : PIX/TED para conta de aplicação (vai para investimentos)
- resgate         : volta de aplicação (crédito recebido)
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import func, select

from core.db import get_session
from core.models import Categoria, Movimentacao
from services.contas import detectar_conta

TIPOS = ["receita", "despesa", "transferencia", "aplicacao", "resgate"]
FORMAS = ["pix", "boleto", "débito", "cartão", "dinheiro", "caju", "outros"]

# Tipos que contam no fluxo real do mês (transferência interna não conta).
TIPOS_REAIS = ("receita", "despesa", "aplicacao", "resgate")


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _id_categoria(s, nome: Optional[str]) -> Optional[int]:
    if not nome:
        return None
    cat = s.scalar(select(Categoria).where(Categoria.nome == nome))
    if not cat:
        cat = Categoria(nome=nome.strip())
        s.add(cat)
        s.flush()
    return cat.id


def _mes_ref(d: date) -> str:
    return d.strftime("%Y-%m")


import re as _re

# Padrão pra reconhecer pagamento de fatura de cartão no extrato bancário.
# Ex.: "FATURA PAGA AZUL ITAU IN", "PAG FATURA CARTAO", "PGTO FATURA".
_PAGAMENTO_FATURA = _re.compile(
    r"\b(fatura\s+paga|pag(amento)?\s+fatura|pgto\s+fatura|pagto\s+cartao)\b",
    _re.I,
)


def classificar(descricao: str, valor: float, conta_origem_id: Optional[int] = None) -> tuple:
    """A partir do texto do lançamento + valor, sugere (tipo, conta_destino_id).
    Regras:
    - "Fatura paga X" → transferencia (pagamento de cartão; o gasto está nas
      transações do cartão, não conta duas vezes)
    - Descrição bate com uma conta de aplicação cadastrada → aplicacao
    - Bate com outra conta corrente/poupança sua → transferencia
    - Valor > 0 → receita; < 0 → despesa
    """
    if descricao and _PAGAMENTO_FATURA.search(descricao):
        return "transferencia", None
    tipo_detectado, cid = detectar_conta(descricao, conta_origem_id)
    if tipo_detectado in ("transferencia", "aplicacao"):
        return tipo_detectado, cid
    if valor > 0:
        return "receita", None
    return "despesa", None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def adicionar(
    data_: date,
    descricao: str,
    valor: float,
    tipo: str = "despesa",
    forma: Optional[str] = None,
    categoria: Optional[str] = None,
    conta_id: Optional[int] = None,
    conta_destino_id: Optional[int] = None,
    lumai: bool = False,
    observacao: Optional[str] = None,
    origem: str = "manual",
) -> int:
    with get_session() as s:
        m = Movimentacao(
            data=data_,
            descricao=descricao.strip(),
            valor=float(abs(valor)),  # sempre positivo; direção vem do tipo
            tipo=tipo if tipo in TIPOS else "despesa",
            forma=forma or None,
            categoria_id=_id_categoria(s, categoria),
            conta_id=conta_id,
            conta_destino_id=conta_destino_id,
            lumai=bool(lumai),
            observacao=(observacao or "").strip() or None,
            mes_referencia=_mes_ref(data_),
            origem=origem,
        )
        s.add(m)
        s.flush()
        return m.id


def atualizar(mid: int, **campos) -> None:
    with get_session() as s:
        m = s.get(Movimentacao, mid)
        if not m:
            return
        if "data" in campos:
            m.data = campos["data"]
            m.mes_referencia = _mes_ref(campos["data"])
        if "descricao" in campos:
            m.descricao = campos["descricao"].strip()
        if "valor" in campos:
            m.valor = float(abs(campos["valor"]))
        if "tipo" in campos:
            m.tipo = campos["tipo"] if campos["tipo"] in TIPOS else "despesa"
        if "forma" in campos:
            m.forma = campos["forma"] or None
        if "categoria" in campos:
            m.categoria_id = _id_categoria(s, campos["categoria"])
        if "conta_id" in campos:
            m.conta_id = campos["conta_id"]
        if "conta_destino_id" in campos:
            m.conta_destino_id = campos["conta_destino_id"]
        if "lumai" in campos:
            m.lumai = bool(campos["lumai"])
        if "observacao" in campos:
            m.observacao = (campos["observacao"] or "").strip() or None


def excluir(mid: int) -> None:
    with get_session() as s:
        m = s.get(Movimentacao, mid)
        if m:
            s.delete(m)


def listar(mes_referencia: Optional[str] = None,
           tipos: Optional[List[str]] = None) -> List[dict]:
    with get_session() as s:
        stmt = select(Movimentacao).order_by(Movimentacao.data.desc())
        if mes_referencia:
            stmt = stmt.where(Movimentacao.mes_referencia == mes_referencia)
        if tipos:
            stmt = stmt.where(Movimentacao.tipo.in_(tipos))
        return [
            {
                "id": m.id, "data": m.data, "descricao": m.descricao,
                "valor": m.valor, "tipo": m.tipo, "forma": m.forma,
                "categoria": m.categoria.nome if m.categoria else "Outros",
                "conta_id": m.conta_id, "conta_destino_id": m.conta_destino_id,
                "lumai": bool(m.lumai),
                "reembolsado": m.reembolsado_em is not None,
                "observacao": m.observacao, "origem": m.origem,
                "mes_referencia": m.mes_referencia,
            }
            for m in s.scalars(stmt).all()
        ]


# ---------------------------------------------------------------------------
# Agregações
# ---------------------------------------------------------------------------
def meses_disponiveis() -> List[str]:
    """Meses (AAAA-MM) que têm ao menos uma movimentação, do mais recente ao
    mais antigo."""
    with get_session() as s:
        stmt = select(Movimentacao.mes_referencia).distinct()
        ms = [m for m in s.scalars(stmt).all() if m]
    return sorted(ms, reverse=True)


def total_por_tipo(mes_referencia: str, tipo: str, excluir_lumai: bool = True) -> float:
    """Total de um tipo no mês. Se `excluir_lumai=True` e for despesa,
    ignora as marcadas como LUMAI (não são gasto seu)."""
    with get_session() as s:
        stmt = (
            select(func.coalesce(func.sum(Movimentacao.valor), 0.0))
            .where(Movimentacao.mes_referencia == mes_referencia)
            .where(Movimentacao.tipo == tipo)
        )
        if tipo == "despesa" and excluir_lumai:
            stmt = stmt.where(Movimentacao.lumai.is_(False))
        return float(s.scalar(stmt) or 0.0)


def resumo_mes(mes_referencia: str) -> dict:
    """Resumo do mês: receitas, despesas (excluindo LUMAI), aplicações,
    saldo real."""
    receitas = total_por_tipo(mes_referencia, "receita")
    despesas = total_por_tipo(mes_referencia, "despesa", excluir_lumai=True)
    aplicacoes = total_por_tipo(mes_referencia, "aplicacao")
    resgates = total_por_tipo(mes_referencia, "resgate")
    return {
        "receitas": receitas,
        "despesas": despesas,
        "aplicacoes": aplicacoes,
        "resgates": resgates,
        "saldo": receitas - despesas - aplicacoes + resgates,
    }


def por_categoria(mes_referencia: str, tipo: str = "despesa",
                  excluir_lumai: bool = True) -> List[dict]:
    with get_session() as s:
        stmt = (
            select(Categoria.nome, func.sum(Movimentacao.valor))
            .select_from(Movimentacao)
            .outerjoin(Categoria, Movimentacao.categoria_id == Categoria.id)
            .where(Movimentacao.mes_referencia == mes_referencia)
            .where(Movimentacao.tipo == tipo)
            .group_by(Categoria.nome)
            .order_by(func.sum(Movimentacao.valor).desc())
        )
        if tipo == "despesa" and excluir_lumai:
            stmt = stmt.where(Movimentacao.lumai.is_(False))
        return [
            {"categoria": nome or "Outros", "total": float(tot or 0.0)}
            for nome, tot in s.execute(stmt)
        ]


def por_dia(mes_referencia: str, tipo: str = "despesa",
            excluir_lumai: bool = True) -> List[dict]:
    """Soma diária de um tipo no mês, para gráfico de evolução."""
    with get_session() as s:
        stmt = (
            select(Movimentacao.data, func.sum(Movimentacao.valor))
            .where(Movimentacao.mes_referencia == mes_referencia)
            .where(Movimentacao.tipo == tipo)
            .group_by(Movimentacao.data)
            .order_by(Movimentacao.data)
        )
        if tipo == "despesa" and excluir_lumai:
            stmt = stmt.where(Movimentacao.lumai.is_(False))
        return [{"data": d, "total": float(t or 0.0)} for d, t in s.execute(stmt)]


def por_fonte(mes_referencia: str, tipo: str = "receita") -> List[dict]:
    """Top fontes/descrições de um tipo — para gráfico de origem das
    receitas ou destinos das despesas."""
    linhas = listar(mes_referencia=mes_referencia, tipos=[tipo])
    acc: dict = {}
    for m in linhas:
        chave = m["descricao"][:40] or "(sem descrição)"
        acc[chave] = acc.get(chave, 0.0) + m["valor"]
    itens = [{"fonte": k, "total": v} for k, v in acc.items()]
    itens.sort(key=lambda x: x["total"], reverse=True)
    return itens


def total_lumai_a_reembolsar(mes_referencia: Optional[str] = None) -> float:
    """Soma das despesas LUMAI ainda não reembolsadas."""
    with get_session() as s:
        stmt = (
            select(func.coalesce(func.sum(Movimentacao.valor), 0.0))
            .where(Movimentacao.lumai.is_(True))
            .where(Movimentacao.reembolsado_em.is_(None))
        )
        if mes_referencia:
            stmt = stmt.where(Movimentacao.mes_referencia == mes_referencia)
        return float(s.scalar(stmt) or 0.0)


# ---------------------------------------------------------------------------
# Bulk (usado pelo importador de extrato)
# ---------------------------------------------------------------------------
def existe(data_: date, valor_abs: float, descricao: str) -> bool:
    """Detector de duplicata: mesma data + valor + início da descrição."""
    chave = descricao.strip().lower()[:40]
    with get_session() as s:
        rs = s.scalars(
            select(Movimentacao)
            .where(Movimentacao.data == data_)
            .where(Movimentacao.valor.between(valor_abs - 0.005, valor_abs + 0.005))
        ).all()
        for m in rs:
            if (m.descricao or "").strip().lower()[:40] == chave:
                return True
        return False
