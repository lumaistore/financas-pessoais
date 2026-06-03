"""Orçamento mensal por categoria — metas/tetos de gasto (Fase 10).

Define um limite por categoria e compara com o gasto real do mês (cartão +
despesas manuais). Vira a base dos alertas no painel.
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import Categoria, Orcamento
from services.cartao import gasto_por_categoria
from services.despesas import despesas_por_categoria


def _id_categoria(s, nome: str) -> Optional[int]:
    cat = s.scalar(select(Categoria).where(Categoria.nome == nome))
    if not cat:
        cat = Categoria(nome=nome)
        s.add(cat)
        s.flush()
    return cat.id


def definir_orcamento(categoria: str, limite_mensal: float) -> None:
    """Cria ou atualiza o teto mensal de uma categoria."""
    with get_session() as s:
        cat_id = _id_categoria(s, categoria)
        orc = s.scalar(select(Orcamento).where(Orcamento.categoria_id == cat_id))
        if orc:
            orc.limite_mensal = float(limite_mensal)
        else:
            s.add(Orcamento(categoria_id=cat_id, limite_mensal=float(limite_mensal)))


def excluir_orcamento(categoria: str) -> None:
    with get_session() as s:
        cat = s.scalar(select(Categoria).where(Categoria.nome == categoria))
        if not cat:
            return
        orc = s.scalar(select(Orcamento).where(Orcamento.categoria_id == cat.id))
        if orc:
            s.delete(orc)


def listar_orcamentos() -> List[dict]:
    with get_session() as s:
        stmt = select(Orcamento)
        return [
            {"categoria": o.categoria.nome if o.categoria else "Outros", "limite": o.limite_mensal}
            for o in s.scalars(stmt).all()
        ]


def _gasto_por_categoria_total(mes_referencia: str) -> dict:
    """Gasto do mês por categoria, juntando cartão + despesas manuais."""
    acc: dict = {}
    for item in gasto_por_categoria(mes_referencia) + despesas_por_categoria(mes_referencia):
        acc[item["categoria"]] = acc.get(item["categoria"], 0.0) + item["total"]
    return acc


def status_orcamento(mes_referencia: str) -> List[dict]:
    """Para cada categoria com orçamento: limite, gasto, restante e % usado."""
    gastos = _gasto_por_categoria_total(mes_referencia)
    resultado = []
    for orc in listar_orcamentos():
        gasto = gastos.get(orc["categoria"], 0.0)
        limite = orc["limite"] or 0.0
        pct = (gasto / limite * 100.0) if limite else 0.0
        resultado.append(
            {
                "categoria": orc["categoria"],
                "limite": limite,
                "gasto": gasto,
                "restante": limite - gasto,
                "percentual": pct,
                "estourou": gasto > limite,
            }
        )
    resultado.sort(key=lambda x: x["percentual"], reverse=True)
    return resultado
