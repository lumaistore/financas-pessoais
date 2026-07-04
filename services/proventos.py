"""Proventos (dividendos, JCP, rendimentos de FII, amortização).

Leitura por IA de visão: o usuário sobe prints do extrato de proventos da
corretora e a IA extrai ticker + tipo + valor + data de cada provento.
Só os bytes da imagem saem da máquina; nada mais.
"""
from __future__ import annotations

import base64
import json
import re
from datetime import date
from typing import List, Optional, Tuple

from sqlalchemy import select

from core.cache import cache_leitura, invalida_cache
from core.db import get_session
from core.models import Provento

TIPOS_PROVENTO = ["dividendo", "jcp", "rendimento", "amortizacao", "outro"]
MODELO_IA = "claude-sonnet-4-5-20250929"

_PROMPT_SISTEMA = (
    "Você lê extratos de PROVENTOS de investimentos (apps de corretora, ex.: "
    "BTG) em português do Brasil. Extraia SOMENTE lançamentos que são proventos "
    "recebidos: Dividendos, Juros sobre Capital Próprio (JCP), Rendimentos de "
    "FII, e Amortização de FII/FIP. "
    "IGNORE completamente: 'Aquisição de Cotas' (aplicação), 'Resgate de Cotas', "
    "taxas ('Taxa de Carteira', 'Liq Bolsa taxa'), estornos, cashback, "
    "'Conta Remunerada'. Não invente nada."
)


def _prompt_usuario(ano: int) -> str:
    return (
        "Analise a imagem do extrato e liste os proventos. Para cada um:\n"
        "- data: use o cabeçalho de data (ex.: '30/Jun' ou '25/06/2026') acima "
        f"do lançamento; se faltar o ano, use {ano}. Formato AAAA-MM-DD.\n"
        "- ticker: o código do ativo (ex.: CMIG4, BBAS3, HGCR11, XLU, VIG). "
        "Em 'Dividendos de XLU', o ticker é XLU.\n"
        "- tipo: um de dividendo | jcp | rendimento | amortizacao "
        "('Juros S/ Capital' = jcp; 'Rendimentos' de FII = rendimento; "
        "'Amortizacao' = amortizacao; 'Dividendos' = dividendo).\n"
        "- valor: número positivo (valor BRUTO do provento, ex.: 69.68).\n"
        "- moeda: 'USD' se o valor usa '$' (ex.: Avenue); 'BRL' se usa 'R$'.\n"
        "- imposto: se houver uma linha 'Imposto sobre dividendo' do MESMO ativo "
        "e data logo ao lado, coloque o valor do imposto (positivo); senão null.\n\n"
        "IMPORTANTE: as linhas de 'Imposto' NÃO são proventos por si só — some-as "
        "ao campo 'imposto' do provento correspondente, não crie item separado.\n\n"
        'Responda APENAS um JSON array, sem markdown: '
        '[{"data":"AAAA-MM-DD","ticker":"XLU","tipo":"dividendo","valor":69.68,'
        '"moeda":"USD","imposto":20.90}]. '
        "Se não houver proventos na imagem, responda []."
    )


# ---------------------------------------------------------------------------
# Leitura por IA de visão
# ---------------------------------------------------------------------------
def ler_imagens(arquivos: List[Tuple[bytes, str]], ano: int) -> List[dict]:
    """Recebe [(bytes, mime), ...] e devolve a lista de proventos extraídos.
    Retorna [] se não houver chave de API ou nada for encontrado."""
    from core.config import get_anthropic_key

    chave = get_anthropic_key()
    if not chave:
        return []

    from anthropic import Anthropic
    client = Anthropic(api_key=chave)

    todos: List[dict] = []
    for dados, mime in arquivos:
        b64 = base64.standard_b64encode(dados).decode("utf-8")
        bloco = {"type": "image",
                 "source": {"type": "base64", "media_type": mime, "data": b64}}
        try:
            resp = client.messages.create(
                model=MODELO_IA,
                max_tokens=1500,
                system=_PROMPT_SISTEMA,
                messages=[{"role": "user",
                           "content": [bloco, {"type": "text", "text": _prompt_usuario(ano)}]}],
            )
            texto = "".join(b.text for b in resp.content
                            if getattr(b, "type", None) == "text").strip()
            texto = re.sub(r"^```(?:json)?\s*|\s*```$", "", texto, flags=re.S)
            m = re.search(r"\[.*\]", texto, re.S)
            itens = json.loads(m.group(0) if m else texto)
        except Exception:
            continue
        for it in itens or []:
            d = _parse_data(it.get("data"))
            valor = _parse_valor(it.get("valor"))
            ticker = (it.get("ticker") or "").strip().upper()
            if d and valor and ticker:
                moeda = (it.get("moeda") or "BRL").strip().upper()
                todos.append({
                    "data": d, "ticker": ticker,
                    "tipo": (it.get("tipo") or "dividendo").strip().lower(),
                    "valor": valor,
                    "moeda": "USD" if moeda == "USD" else "BRL",
                    "imposto": _parse_valor(it.get("imposto")) or 0.0,
                })
    # Dedup dentro do lote (prints costumam ter sobreposição).
    vistos = set()
    unicos = []
    for p in todos:
        k = (p["data"], p["ticker"], round(p["valor"], 2))
        if k not in vistos:
            vistos.add(k)
            unicos.append(p)
    unicos.sort(key=lambda x: (x["data"], x["ticker"]))
    return unicos


def _parse_data(s) -> Optional[date]:
    if not s:
        return None
    m = re.match(r"\s*(\d{4})-(\d{1,2})-(\d{1,2})", str(s))
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    return None


def _parse_valor(v) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return abs(float(v))
    s = str(v).replace("R$", "").strip().replace(".", "").replace(",", ".")
    try:
        return abs(float(s))
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def _existe(s, d: date, ticker: str, valor: float) -> bool:
    rs = s.scalars(
        select(Provento)
        .where(Provento.data == d)
        .where(Provento.ticker == ticker)
        .where(Provento.valor.between(valor - 0.005, valor + 0.005))
    ).all()
    return len(rs) > 0


@invalida_cache
def registrar_proventos(itens: List[dict]) -> int:
    """Salva vários proventos, ignorando duplicatas (data+ticker+valor).
    Cada item: {data, ticker, tipo, valor, moeda?, cotacao?, imposto?}."""
    n = 0
    with get_session() as s:
        for it in itens:
            d = it["data"]
            ticker = (it["ticker"] or "").strip().upper()
            valor = float(it["valor"])
            if not ticker or valor <= 0:
                continue
            if _existe(s, d, ticker, valor):
                continue
            moeda = (it.get("moeda") or "BRL").upper()
            cotacao = float(it.get("cotacao") or (1.0 if moeda == "BRL" else 0.0))
            s.add(Provento(
                data=d, ticker=ticker,
                tipo=(it.get("tipo") or "dividendo"),
                valor=valor, moeda=moeda, cotacao=cotacao,
                imposto=float(it.get("imposto") or 0.0) or None,
                observacao=(it.get("observacao") or None),
            ))
            n += 1
    return n


def _valor_brl(p) -> float:
    """Valor em reais: BRL usa valor direto; USD multiplica pela cotação."""
    if (p.moeda or "BRL").upper() == "USD":
        return float(p.valor) * float(p.cotacao or 0.0)
    return float(p.valor)


@cache_leitura
def listar_proventos(mes_referencia: Optional[str] = None) -> List[dict]:
    with get_session() as s:
        rs = s.scalars(select(Provento).order_by(Provento.data.desc())).all()
        out = []
        for p in rs:
            if mes_referencia and p.data.strftime("%Y-%m") != mes_referencia:
                continue
            out.append({
                "id": p.id, "data": p.data, "ticker": p.ticker, "tipo": p.tipo,
                "valor": p.valor, "moeda": p.moeda or "BRL",
                "cotacao": p.cotacao or 1.0, "imposto": p.imposto,
                "valor_brl": _valor_brl(p), "observacao": p.observacao,
                "mes_referencia": p.data.strftime("%Y-%m"),
            })
        return out


@invalida_cache
def excluir_provento(pid: int) -> None:
    with get_session() as s:
        p = s.get(Provento, pid)
        if p:
            s.delete(p)


@cache_leitura
def total_proventos_mes(mes_referencia: str) -> float:
    return sum(p["valor_brl"] for p in listar_proventos(mes_referencia))


@cache_leitura
def por_ticker_mes(mes_referencia: str) -> List[dict]:
    acc: dict = {}
    for p in listar_proventos(mes_referencia):
        acc[p["ticker"]] = acc.get(p["ticker"], 0.0) + p["valor_brl"]
    itens = [{"ticker": k, "total": v} for k, v in acc.items()]
    itens.sort(key=lambda x: x["total"], reverse=True)
    return itens
