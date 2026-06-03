"""Atualização de cotações e ganho/perda por período (Fase 13).

- Ações/FIIs/ETFs: preço atual via yfinance (Yahoo Finance). Só os símbolos
  (tickers) saem da máquina — nenhum dado pessoal.
- Renda fixa pós-fixada (CDI): estimativa por carrego, usando o CDI atual do
  Banco Central e a fórmula padrão de CDB pós (% do CDI capitalizado por dias
  úteis desde a aplicação).
- Histórico do valor total da carteira para o filtro de ganho/perda no tempo.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import numpy as np
from sqlalchemy import select

from core.db import get_session
from core.models import CarteiraHistorico
from services.investimentos import (
    carregar_snapshot,
    cotacao_usd_do_snapshot,
    listar_datas,
    salvar_snapshot,
    total_carteira,
)

CDI_PADRAO = 14.40  # fallback se o Banco Central não responder
TICKER_USD = "USDBRL=X"


# ---------------------------------------------------------------------------
# Fontes externas
# ---------------------------------------------------------------------------
def _yf_ticker(ticker: str, moeda: str) -> str:
    """Converte o ticker para o formato do Yahoo (B3 leva sufixo .SA)."""
    t = (ticker or "").strip().upper()
    if moeda == "USD" or "." in t or "=" in t:
        return t
    return t + ".SA"


def buscar_precos(tickers_yf: List[str]) -> Dict[str, Optional[float]]:
    """Preço atual de cada ticker (formato Yahoo). None quando falhar."""
    import yfinance as yf

    resultado: Dict[str, Optional[float]] = {}
    for t in tickers_yf:
        try:
            fi = yf.Ticker(t).fast_info
            preco = fi.get("last_price") or fi.get("lastPrice")
            resultado[t] = float(preco) if preco else None
        except Exception:
            resultado[t] = None
    return resultado


def buscar_dolar() -> Optional[float]:
    """Cotação atual USD→BRL (None se a fonte falhar)."""
    return buscar_precos([TICKER_USD]).get(TICKER_USD)


def buscar_cdi_anual() -> float:
    """CDI ao ano (%) da série 4389 do Banco Central. Fallback em CDI_PADRAO."""
    import urllib.request
    import json

    url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.4389/dados/ultimos/1?formato=json"
    try:
        with urllib.request.urlopen(url, timeout=8) as resp:
            dados = json.loads(resp.read().decode("utf-8"))
        return float(dados[-1]["valor"])
    except Exception:
        return CDI_PADRAO


# ---------------------------------------------------------------------------
# Estimativa de renda fixa (carrego)
# ---------------------------------------------------------------------------
def estimar_renda_fixa(
    base: float,
    taxa_pct: float,
    data_aplicacao: date,
    cdi_anual: float,
    hoje: Optional[date] = None,
) -> float:
    """Valor estimado de um pós-fixado: base capitalizada por % do CDI ao longo
    dos dias úteis desde a aplicação."""
    hoje = hoje or date.today()
    if not base or not data_aplicacao or data_aplicacao >= hoje:
        return float(base or 0.0)
    dias_uteis = int(np.busday_count(data_aplicacao, hoje))
    if dias_uteis <= 0:
        return float(base)
    cdi_diario = (1 + cdi_anual / 100.0) ** (1 / 252) - 1
    taxa_diaria = cdi_diario * (taxa_pct / 100.0)
    return float(base) * (1 + taxa_diaria) ** dias_uteis


# ---------------------------------------------------------------------------
# Atualização do snapshot
# ---------------------------------------------------------------------------
def atualizar_cotacoes(data_ref: Optional[date] = None) -> dict:
    """Atualiza preços (bolsa) e estimativas (CDI) do snapshot e registra o
    valor total no histórico. Retorna um resumo."""
    datas = listar_datas()
    if not datas:
        return {"erro": "Nenhum snapshot para atualizar."}
    data_ref = data_ref or datas[0]
    linhas = carregar_snapshot(data_ref)

    # Câmbio USD→BRL.
    cot_usd = cotacao_usd_do_snapshot(data_ref)
    precos_usd = buscar_precos([TICKER_USD])
    if precos_usd.get(TICKER_USD):
        cot_usd = precos_usd[TICKER_USD]

    # Preços de bolsa.
    mapa_yf = {}
    for ln in linhas:
        if ln.get("ticker"):
            mapa_yf[id(ln)] = _yf_ticker(ln["ticker"], ln.get("moeda") or "BRL")
    precos = buscar_precos(list(set(mapa_yf.values()))) if mapa_yf else {}

    cdi = buscar_cdi_anual()
    atualizados = falhas = rf_estimados = 0

    for ln in linhas:
        # 1) Ativos com ticker (bolsa).
        if ln.get("ticker"):
            preco = precos.get(mapa_yf[id(ln)])
            if preco:
                ln["preco_unitario"] = preco
                qtd = ln.get("quantidade")
                if qtd:
                    ln["valor_mercado"] = float(qtd) * preco
                else:
                    ln["valor_mercado"] = preco
                atualizados += 1
            else:
                falhas += 1
            continue
        # 2) Renda fixa pós-fixada no CDI (carrego).
        if (ln.get("indexador") or "").upper() == "CDI" and ln.get("taxa_indice") and ln.get("data_aplicacao"):
            base = ln.get("valor_investido") or ln.get("valor_mercado")
            ln["valor_mercado"] = estimar_renda_fixa(
                base, float(ln["taxa_indice"]), ln["data_aplicacao"], cdi
            )
            rf_estimados += 1

    salvar_snapshot(data_ref, linhas, cotacao_usd=cot_usd)
    total = total_carteira(data_ref)
    registrar_total(total)

    return {
        "momento": datetime.now(),
        "atualizados": atualizados,
        "falhas": falhas,
        "rf_estimados": rf_estimados,
        "cdi": cdi,
        "usd": cot_usd,
        "total": total,
    }


# ---------------------------------------------------------------------------
# Histórico do valor da carteira / ganho-perda
# ---------------------------------------------------------------------------
def registrar_total(total_brl: float) -> None:
    with get_session() as s:
        s.add(CarteiraHistorico(momento=datetime.now(), total_brl=float(total_brl)))


def evolucao_intradiaria(desde: Optional[datetime] = None) -> List[dict]:
    with get_session() as s:
        stmt = select(CarteiraHistorico).order_by(CarteiraHistorico.momento)
        if desde:
            stmt = stmt.where(CarteiraHistorico.momento >= desde)
        return [{"momento": h.momento, "total": h.total_brl} for h in s.scalars(stmt).all()]


_PERIODOS = {
    "Hoje": timedelta(days=1),
    "7 dias": timedelta(days=7),
    "30 dias": timedelta(days=30),
    "90 dias": timedelta(days=90),
}


def ganho_perda(periodo: str, agora: Optional[datetime] = None) -> Optional[dict]:
    """Ganho/perda da carteira no período, usando o histórico de valor total.

    Compara o valor mais recente com o primeiro registro dentro da janela.
    Retorna None se não há histórico suficiente."""
    agora = agora or datetime.now()
    registros = evolucao_intradiaria()
    if len(registros) < 2:
        return None
    atual = registros[-1]["total"]
    if periodo == "Desde o início":
        base_reg = registros[0]
    else:
        corte = agora - _PERIODOS.get(periodo, timedelta(days=7))
        dentro = [r for r in registros if r["momento"] >= corte]
        base_reg = dentro[0] if dentro else registros[0]
    base = base_reg["total"]
    ganho = atual - base
    pct = (ganho / base * 100.0) if base else 0.0
    return {
        "base": base,
        "atual": atual,
        "ganho": ganho,
        "percentual": pct,
        "momento_base": base_reg["momento"],
    }
