"""Regras de negócio das receitas (Fase 1)."""
from __future__ import annotations

from datetime import date

from sqlalchemy import select

from core.db import get_session
from core.models import Receita

TIPOS = ["salario", "outros"]


def adicionar_receita(
    data_: date, fonte: str, valor: float, tipo: str = "outros", descricao: str | None = None
) -> int:
    with get_session() as s:
        r = Receita(data=data_, fonte=fonte, valor=valor, tipo=tipo, descricao=descricao)
        s.add(r)
        s.flush()
        return r.id


def excluir_receita(receita_id: int) -> None:
    with get_session() as s:
        r = s.get(Receita, receita_id)
        if r:
            s.delete(r)


def listar_receitas(mes_referencia: str | None = None) -> list[dict]:
    """Lista receitas. mes_referencia no formato 'AAAA-MM' filtra por mês."""
    with get_session() as s:
        stmt = select(Receita).order_by(Receita.data.desc())
        receitas = s.scalars(stmt).all()
        resultado = []
        for r in receitas:
            if mes_referencia and r.data.strftime("%Y-%m") != mes_referencia:
                continue
            resultado.append(
                {
                    "id": r.id,
                    "data": r.data,
                    "fonte": r.fonte,
                    "tipo": r.tipo,
                    "valor": r.valor,
                    "descricao": r.descricao or "",
                }
            )
        return resultado


def total_recebido(mes_referencia: str | None = None) -> float:
    return sum(r["valor"] for r in listar_receitas(mes_referencia))
