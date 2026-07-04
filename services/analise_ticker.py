"""Análise técnica/fundamentalista de um ticker via yfinance.

Retorna todos os indicadores que um assessor usa para embasar uma tese:
DY, P/VP, P/L, ROE, volatilidade 1a/5a, máxima/mínima/média histórica,
liquidez, market cap, e a série histórica de preços para gerar o gráfico.
"""
from __future__ import annotations

import warnings
from datetime import date, datetime
from typing import Dict, Optional

warnings.filterwarnings("ignore")


def _yf_ticker(ticker: str, moeda: str = "BRL") -> str:
    """B3 leva sufixo '.SA'. US direto."""
    t = (ticker or "").strip().upper()
    if not t:
        return ""
    if moeda == "USD" or "." in t or "=" in t:
        return t
    return t + ".SA"


def _volatilidade_anualizada(retornos_diarios) -> float:
    """Std dos retornos diários × sqrt(252) — em %."""
    import numpy as np
    if len(retornos_diarios) < 5:
        return 0.0
    return float(retornos_diarios.std() * np.sqrt(252) * 100)


def _brl(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"R$ {v:,.2f}"


def _cache(func=None, **kw):
    """Wrapper opcional de cache (só ativa sob Streamlit)."""
    from core.cache import cache_leitura
    return cache_leitura(func, **kw) if func else cache_leitura(**kw)


@_cache(ttl=1800)  # download de 5 anos é pesado; cacheia por 30 min
def analisar(ticker: str, moeda: str = "BRL") -> Optional[Dict]:
    """Retorna um dicionário com todos os indicadores + série histórica.
    Retorna None se o ticker não foi encontrado."""
    import yfinance as yf

    tk = _yf_ticker(ticker, moeda)
    if not tk:
        return None
    try:
        obj = yf.Ticker(tk)
        info = obj.info or {}
        hist_5a = obj.history(period="5y", auto_adjust=True)
        hist_1a = obj.history(period="1y", auto_adjust=True)
    except Exception:
        return None

    if hist_5a.empty:
        return None

    fechamento_5a = hist_5a["Close"]
    fechamento_1a = hist_1a["Close"] if not hist_1a.empty else fechamento_5a.tail(252)

    preco_atual = float(fechamento_1a.iloc[-1])
    maxima_5a = float(fechamento_5a.max())
    minima_5a = float(fechamento_5a.min())
    media_5a = float(fechamento_5a.mean())
    maxima_1a = float(fechamento_1a.max())
    minima_1a = float(fechamento_1a.min())
    media_1a = float(fechamento_1a.mean())

    # Retornos diários para volatilidade.
    retornos_5a = fechamento_5a.pct_change().dropna()
    retornos_1a = fechamento_1a.pct_change().dropna()
    vol_5a = _volatilidade_anualizada(retornos_5a)
    vol_1a = _volatilidade_anualizada(retornos_1a)

    # Onde está o preço na régua histórica?
    posicao_5a = ((preco_atual - minima_5a) / (maxima_5a - minima_5a) * 100) if maxima_5a > minima_5a else 50

    # Retorno acumulado 5a e 1a.
    retorno_5a = ((preco_atual / float(fechamento_5a.iloc[0])) - 1) * 100 if len(fechamento_5a) else 0
    retorno_1a = ((preco_atual / float(fechamento_1a.iloc[0])) - 1) * 100 if len(fechamento_1a) else 0

    # Fundamentals (yfinance pode retornar None em muitos)
    dy = info.get("dividendYield")
    dy_pct = float(dy * 100) if dy and dy < 1 else float(dy) if dy else None
    pvp = info.get("priceToBook")
    pl = info.get("trailingPE")
    roe = info.get("returnOnEquity")
    roe_pct = float(roe * 100) if roe else None
    mkt = info.get("marketCap")
    setor = info.get("sector") or info.get("industry")
    nome = info.get("longName") or info.get("shortName") or ticker

    # Dividendos últimos 12 meses (mais confiável que dividendYield do yf)
    div_12m = None
    try:
        divs = obj.dividends
        if not divs.empty:
            um_ano_atras = datetime.now(divs.index.tz).replace(microsecond=0) if divs.index.tz else datetime.now()
            recentes = divs[divs.index >= (divs.index.max() - (divs.index.max() - divs.index.min()) / 5)]
            recentes_12m = divs.tail(52)  # até 52 pagamentos no ano (semanal seria excesso; mas é margem)
            # Melhor: filtra pelos últimos 365 dias
            corte = divs.index.max() - (divs.index.max() - divs.index.min()).__class__(days=365)
            recentes_12m = divs[divs.index >= corte]
            div_12m = float(recentes_12m.sum())
    except Exception:
        pass

    dy_calculado = (div_12m / preco_atual * 100) if div_12m and preco_atual else None

    # Distância pra máxima/mínima
    dist_max = ((maxima_5a - preco_atual) / preco_atual * 100)
    dist_min = ((preco_atual - minima_5a) / minima_5a * 100)

    return {
        "ticker": ticker.upper(),
        "yf_ticker": tk,
        "nome": nome,
        "setor": setor,
        "preco_atual": preco_atual,
        "moeda": "USD" if moeda == "USD" else "BRL",

        # Fundamentals
        "dy": dy_pct,               # do yfinance
        "dy_calculado": dy_calculado,  # calculado dos últimos 12m (mais confiável)
        "div_12m": div_12m,
        "pvp": pvp,
        "pl": pl,
        "roe": roe_pct,
        "market_cap": mkt,

        # Preço 5a
        "maxima_5a": maxima_5a,
        "minima_5a": minima_5a,
        "media_5a": media_5a,
        "posicao_5a_pct": posicao_5a,   # 0 = mínima, 100 = máxima
        "dist_max_pct": dist_max,       # quanto tem que subir p/ máxima
        "dist_min_pct": dist_min,       # quanto tem que cair p/ mínima
        "retorno_5a_pct": retorno_5a,
        "vol_5a_pct": vol_5a,

        # Preço 1a
        "maxima_1a": maxima_1a,
        "minima_1a": minima_1a,
        "media_1a": media_1a,
        "retorno_1a_pct": retorno_1a,
        "vol_1a_pct": vol_1a,

        # Série pra gráfico
        "serie_5a": fechamento_5a,
    }


# ---------------------------------------------------------------------------
# Gráfico Plotly no estilo "research report"
# ---------------------------------------------------------------------------
def gerar_grafico(dados: Dict):
    import plotly.graph_objects as go

    serie = dados["serie_5a"]
    moeda_simb = "US$" if dados["moeda"] == "USD" else "R$"

    fig = go.Figure()

    # Linha do preço
    fig.add_trace(go.Scatter(
        x=serie.index,
        y=serie.values,
        mode="lines",
        name="Preço",
        line=dict(color="#1f77b4", width=2),
        hovertemplate="%{x|%d/%m/%Y}<br>" + moeda_simb + " %{y:,.2f}<extra></extra>",
    ))

    # Máxima 5a
    fig.add_hline(
        y=dados["maxima_5a"],
        line_dash="dot",
        line_color="#2ca02c",
        annotation_text=f"Máx 5a: {moeda_simb} {dados['maxima_5a']:,.2f}",
        annotation_position="top right",
    )

    # Mínima 5a
    fig.add_hline(
        y=dados["minima_5a"],
        line_dash="dot",
        line_color="#d62728",
        annotation_text=f"Mín 5a: {moeda_simb} {dados['minima_5a']:,.2f}",
        annotation_position="bottom right",
    )

    # Média 5a
    fig.add_hline(
        y=dados["media_5a"],
        line_dash="dash",
        line_color="#7f7f7f",
        annotation_text=f"Média 5a: {moeda_simb} {dados['media_5a']:,.2f}",
        annotation_position="top left",
    )

    # Preço atual (marker)
    fig.add_trace(go.Scatter(
        x=[serie.index[-1]],
        y=[dados["preco_atual"]],
        mode="markers+text",
        name="Preço atual",
        marker=dict(size=12, color="#ff7f0e", symbol="circle"),
        text=[f"{moeda_simb} {dados['preco_atual']:,.2f}"],
        textposition="top center",
        showlegend=False,
    ))

    fig.update_layout(
        title=dict(
            text=f"<b>{dados['ticker']}</b> — {dados['nome']}",
            font=dict(size=16),
        ),
        xaxis_title="",
        yaxis_title=f"Preço ({dados['moeda']})",
        hovermode="x unified",
        height=380,
        margin=dict(l=40, r=40, t=60, b=40),
        showlegend=False,
        template="simple_white",
    )
    return fig


# ---------------------------------------------------------------------------
# Comparativo em tabela (para o assessor)
# ---------------------------------------------------------------------------
def linha_comparativo(dados: Dict) -> Dict:
    """Devolve uma linha resumida para tabela comparativa entre vários tickers."""
    return {
        "Ticker": dados["ticker"],
        "Setor": dados.get("setor") or "—",
        "Preço": dados["preco_atual"],
        "DY %": dados.get("dy_calculado") or dados.get("dy") or None,
        "P/VP": dados.get("pvp"),
        "P/L": dados.get("pl"),
        "ROE %": dados.get("roe"),
        "Vol 1a %": dados["vol_1a_pct"],
        "Vol 5a %": dados["vol_5a_pct"],
        "Ret 1a %": dados["retorno_1a_pct"],
        "Ret 5a %": dados["retorno_5a_pct"],
        "Máx 5a": dados["maxima_5a"],
        "Mín 5a": dados["minima_5a"],
        "Média 5a": dados["media_5a"],
        "% da faixa": dados["posicao_5a_pct"],  # 0 = mín, 100 = máx
    }
