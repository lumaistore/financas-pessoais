"""Sincroniza dados existentes (faturas de cartão + tabelas antigas de
receitas/despesas) para a estrutura nova de Movimentacao.

Idempotente: usa (data + valor + descrição) como chave de duplicata, então
pode rodar quantas vezes quiser sem gerar linhas duplicadas.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Dict, Optional

from sqlalchemy import inspect, select, text

from core.db import get_engine, get_session
from core.models import Fatura, Movimentacao, TransacaoCartao


def _para_data(v) -> Optional[date]:
    """Normaliza qualquer resultado de coluna DATE (SQLAlchemy varia entre
    date/datetime/string dependendo do dialeto)."""
    if v is None:
        return None
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, str):
        try:
            return date.fromisoformat(v[:10])
        except ValueError:
            return None
    return None


def _tabela_existe(nome: str) -> bool:
    eng = get_engine()
    return nome in inspect(eng).get_table_names()


def _ja_existe(s, data_, valor_abs, descricao) -> bool:
    """Detector de duplicata por (data, valor, desc)."""
    chave = (descricao or "").strip().lower()[:40]
    rs = s.scalars(
        select(Movimentacao)
        .where(Movimentacao.data == data_)
        .where(Movimentacao.valor.between(valor_abs - 0.005, valor_abs + 0.005))
    ).all()
    for m in rs:
        if (m.descricao or "").strip().lower()[:40] == chave:
            return True
    return False


# ---------------------------------------------------------------------------
# Transações de cartão → movimentações (despesa)
# ---------------------------------------------------------------------------
def sincronizar_cartao() -> int:
    """Cria uma Movimentacao para cada transação de cartão que ainda não tem
    equivalente na tabela nova. A data usada é o `mes_referencia` da fatura
    (mês em que você paga), não a data original da compra."""
    n = 0
    with get_session() as s:
        faturas = s.scalars(select(Fatura)).all()
        for f in faturas:
            origem = f"cartao:{f.banco or '?'}:{f.mes_referencia or '?'}"
            for t in f.transacoes:
                if _ja_existe(s, t.data, abs(t.valor), t.descricao):
                    continue
                m = Movimentacao(
                    data=t.data,
                    descricao=t.descricao,
                    valor=abs(t.valor),
                    tipo="despesa",
                    forma="cartão",
                    categoria_id=t.categoria_id,
                    mes_referencia=(f.mes_referencia
                                    or t.data.strftime("%Y-%m")),
                    lumai=bool(t.lumai),
                    reembolsado_em=t.reembolsado_em,
                    origem=origem,
                )
                s.add(m)
                n += 1
    return n


# ---------------------------------------------------------------------------
# Receita e DespesaManual antigas (se as tabelas ainda existirem)
# ---------------------------------------------------------------------------
def _sincronizar_receitas_antigas() -> int:
    if not _tabela_existe("receitas"):
        return 0
    n = 0
    eng = get_engine()
    with eng.connect() as conn:
        try:
            linhas = conn.execute(text(
                "SELECT data, fonte, valor, tipo, descricao FROM receitas"
            )).all()
        except Exception:
            return 0
    with get_session() as s:
        for data_v, fonte, valor, _tipo, descricao in linhas:
            data_ = _para_data(data_v)
            if not data_:
                continue
            desc = (descricao or fonte or "Receita").strip()
            if _ja_existe(s, data_, abs(float(valor)), desc):
                continue
            m = Movimentacao(
                data=data_,
                descricao=desc,
                valor=abs(float(valor)),
                tipo="receita",
                mes_referencia=data_.strftime("%Y-%m"),
                origem="migracao:receitas",
            )
            s.add(m)
            n += 1
    return n


def _sincronizar_despesas_antigas() -> int:
    if not _tabela_existe("despesas_manuais"):
        return 0
    n = 0
    eng = get_engine()
    with eng.connect() as conn:
        try:
            linhas = conn.execute(text(
                "SELECT data, descricao, valor, forma, categoria_id, "
                "lumai, reembolsado_em FROM despesas_manuais"
            )).all()
        except Exception:
            return 0
    with get_session() as s:
        for row in linhas:
            data_v, desc, valor, forma, cat_id, lumai, reemb = row
            data_ = _para_data(data_v)
            if not data_:
                continue
            desc_str = (desc or "").strip() or "Despesa"
            if _ja_existe(s, data_, abs(float(valor)), desc_str):
                continue
            m = Movimentacao(
                data=data_,
                descricao=desc_str,
                valor=abs(float(valor)),
                tipo="despesa",
                forma=forma or None,
                categoria_id=cat_id,
                mes_referencia=data_.strftime("%Y-%m"),
                lumai=bool(lumai),
                reembolsado_em=_para_data(reemb),
                origem="migracao:despesas_manuais",
            )
            s.add(m)
            n += 1
    return n


# ---------------------------------------------------------------------------
# Sincronização completa
# ---------------------------------------------------------------------------
def sincronizar_tudo() -> Dict[str, int]:
    """Roda todas as sincronizações. Retorna quantas linhas criou de cada."""
    return {
        "cartão": sincronizar_cartao(),
        "receitas antigas": _sincronizar_receitas_antigas(),
        "despesas antigas": _sincronizar_despesas_antigas(),
    }
