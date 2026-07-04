"""Regras de negócio das despesas manuais (Fase 8).

Gastos que não vêm de fatura de cartão: PIX, boleto, débito, dinheiro, Caju
(vale-alimentação) etc. São lançados à mão e entram no painel mensal junto
com os gastos de cartão. Também podem ser marcados como LUMAI (reembolso).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import func, select

from core.db import get_session
from core.models import Categoria, DespesaManual

FORMAS = ["pix", "boleto", "débito", "dinheiro", "caju", "outros"]


def _id_categoria(s, nome: Optional[str]) -> Optional[int]:
    if not nome:
        return None
    cat = s.scalar(select(Categoria).where(Categoria.nome == nome))
    if not cat:
        cat = Categoria(nome=nome)
        s.add(cat)
        s.flush()
    return cat.id


def _mes_ref(d: date) -> str:
    return d.strftime("%Y-%m")


def adicionar_despesa(
    data_: date,
    descricao: str,
    valor: float,
    forma: str = "pix",
    categoria: Optional[str] = None,
    lumai: bool = False,
) -> int:
    with get_session() as s:
        d = DespesaManual(
            data=data_,
            descricao=descricao.strip(),
            valor=float(valor),
            forma=forma if forma in FORMAS else "outros",
            categoria_id=_id_categoria(s, categoria),
            mes_referencia=_mes_ref(data_),
            lumai=bool(lumai),
        )
        s.add(d)
        s.flush()
        return d.id


def listar_despesas(mes_referencia: Optional[str] = None) -> List[dict]:
    with get_session() as s:
        stmt = select(DespesaManual).order_by(DespesaManual.data.desc())
        if mes_referencia:
            stmt = stmt.where(DespesaManual.mes_referencia == mes_referencia)
        return [
            {
                "id": d.id,
                "data": d.data,
                "descricao": d.descricao,
                "valor": d.valor,
                "forma": d.forma,
                "categoria": d.categoria.nome if d.categoria else "Outros",
                "lumai": bool(d.lumai),
                "reembolsado": d.reembolsado_em is not None,
                "reembolsado_em": d.reembolsado_em,
                "mes_referencia": d.mes_referencia,
            }
            for d in s.scalars(stmt).all()
        ]


def marcar_despesa_reembolsada(despesa_id: int) -> None:
    from datetime import date as _date
    with get_session() as s:
        d = s.get(DespesaManual, despesa_id)
        if d and d.reembolsado_em is None:
            d.reembolsado_em = _date.today()


def desfazer_reembolso_despesa(despesa_id: int) -> None:
    with get_session() as s:
        d = s.get(DespesaManual, despesa_id)
        if d:
            d.reembolsado_em = None


def excluir_despesa(despesa_id: int) -> None:
    with get_session() as s:
        d = s.get(DespesaManual, despesa_id)
        if d:
            s.delete(d)


def total_despesas(mes_referencia: Optional[str] = None) -> float:
    with get_session() as s:
        stmt = select(func.coalesce(func.sum(DespesaManual.valor), 0.0))
        if mes_referencia:
            stmt = stmt.where(DespesaManual.mes_referencia == mes_referencia)
        return float(s.scalar(stmt) or 0.0)


def despesas_por_categoria(mes_referencia: Optional[str] = None) -> List[dict]:
    with get_session() as s:
        stmt = (
            select(Categoria.nome, func.sum(DespesaManual.valor))
            .select_from(DespesaManual)
            .outerjoin(Categoria, DespesaManual.categoria_id == Categoria.id)
            .group_by(Categoria.nome)
            .order_by(func.sum(DespesaManual.valor).desc())
        )
        if mes_referencia:
            stmt = stmt.where(DespesaManual.mes_referencia == mes_referencia)
        return [{"categoria": nome or "Outros", "total": float(tot or 0.0)} for nome, tot in s.execute(stmt)]


def total_lumai_despesas(mes_referencia: Optional[str] = None,
                         incluir_pagos: bool = False) -> float:
    """Soma das despesas manuais LUMAI a reembolsar (não pagas por padrão)."""
    with get_session() as s:
        stmt = (
            select(func.coalesce(func.sum(DespesaManual.valor), 0.0))
            .where(DespesaManual.lumai.is_(True))
        )
        if not incluir_pagos:
            stmt = stmt.where(DespesaManual.reembolsado_em.is_(None))
        if mes_referencia:
            stmt = stmt.where(DespesaManual.mes_referencia == mes_referencia)
        return float(s.scalar(stmt) or 0.0)
