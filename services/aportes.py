"""Histórico de compras/aportes de investimento.

Cada compra registrada aqui:
1. Vira uma linha no histórico (CompraInvestimento), com data/qtd/preço.
2. Cria uma Movimentacao do tipo 'aplicacao' naquela data — para contar no
   "Aplicado" do mês (Painel/Movimentações).
3. Opcionalmente soma a posição à carteira (snapshot mais recente).
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import select

from core.cache import cache_leitura, invalida_cache
from core.db import get_session
from core.models import CompraInvestimento


def _descricao(qtd: Optional[float], ativo: str) -> str:
    if qtd:
        q = f"{qtd:g}"
        return f"Compra {q} {ativo}"
    return f"Aporte {ativo}"


@invalida_cache
def registrar_compra(
    data_: date,
    ativo: str,
    valor_total: float,
    ticker: Optional[str] = None,
    classe: Optional[str] = None,
    quantidade: Optional[float] = None,
    preco_unitario: Optional[float] = None,
    moeda: str = "BRL",
    observacao: Optional[str] = None,
    somar_carteira: bool = True,
) -> int:
    """Registra uma compra: cria a Movimentacao (aplicacao) + o histórico +
    (opcional) soma à carteira. Retorna o id da compra."""
    from services.movimentacoes import adicionar as add_mov

    # 1) Movimentação de aplicação (conta no fluxo do mês).
    mov_id = add_mov(
        data_=data_,
        descricao=_descricao(quantidade, ativo),
        valor=float(valor_total),
        tipo="aplicacao",
        origem="investimento:compra",
        observacao=observacao,
    )

    # 2) Registro no histórico.
    with get_session() as s:
        c = CompraInvestimento(
            data=data_,
            ativo=ativo.strip(),
            ticker=(ticker or "").strip().upper() or None,
            classe=classe or None,
            quantidade=quantidade or None,
            preco_unitario=preco_unitario or None,
            valor_total=float(valor_total),
            moeda=moeda or "BRL",
            observacao=(observacao or "").strip() or None,
            movimentacao_id=mov_id,
        )
        s.add(c)
        s.flush()
        compra_id = c.id

    # 3) Soma à carteira (posição no snapshot mais recente), se pedido.
    if somar_carteira:
        from services.investimentos import adicionar_posicao
        linha = {
            "ativo": ativo.strip(),
            "classe_ativo": classe or "Outros",
            "moeda": moeda or "BRL",
            "quantidade": quantidade or None,
            "preco_unitario": preco_unitario or None,
            "valor_mercado": float(valor_total),
            "valor_investido": float(valor_total),
            "ticker": (ticker or "").strip().upper() or None,
        }
        try:
            adicionar_posicao(linha)
        except Exception:
            pass  # não bloqueia o registro da compra se a carteira falhar

    return compra_id


@cache_leitura
def listar_compras(mes_referencia: Optional[str] = None) -> List[dict]:
    """Histórico de compras, da mais recente para a mais antiga."""
    with get_session() as s:
        stmt = select(CompraInvestimento).order_by(CompraInvestimento.data.desc())
        compras = s.scalars(stmt).all()
        resultado = []
        for c in compras:
            if mes_referencia and c.data.strftime("%Y-%m") != mes_referencia:
                continue
            resultado.append({
                "id": c.id, "data": c.data, "ativo": c.ativo, "ticker": c.ticker,
                "classe": c.classe, "quantidade": c.quantidade,
                "preco_unitario": c.preco_unitario, "valor_total": c.valor_total,
                "moeda": c.moeda, "observacao": c.observacao,
                "movimentacao_id": c.movimentacao_id,
                "mes_referencia": c.data.strftime("%Y-%m"),
            })
        return resultado


@invalida_cache
def excluir_compra(compra_id: int) -> None:
    """Remove a compra e a movimentação de aplicação vinculada."""
    from services.movimentacoes import excluir as excluir_mov

    with get_session() as s:
        c = s.get(CompraInvestimento, compra_id)
        if not c:
            return
        mov_id = c.movimentacao_id
        s.delete(c)
    if mov_id:
        excluir_mov(mov_id)


@cache_leitura
def total_aportes_mes(mes_referencia: str) -> float:
    return sum(c["valor_total"] for c in listar_compras(mes_referencia))
