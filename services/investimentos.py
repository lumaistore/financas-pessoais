"""Regras de negócio dos investimentos (Fase 4).

A carteira é registrada como *snapshots*: cada `data` guarda a foto completa
das posições. Comparando snapshots de datas diferentes obtemos a evolução e o
rendimento do período.

A entrada de dados é manual/estruturada (tabela editável na tela), porque a
origem real são prints de corretora — não há arquivo padronizado para parsear.
O primeiro snapshot já vem pré-preenchido com as posições extraídas dos prints
enviados pelo usuário (01/06/2026), para ele apenas conferir/ajustar.

Ativos em dólar (ex.: ETFs VIG/XLU) guardam `moeda="USD"` e uma `cotacao`
USD→BRL; o valor em reais é sempre `valor_mercado * cotacao`.
"""
from __future__ import annotations

from datetime import date
from typing import List, Optional

from sqlalchemy import distinct, select

from core.db import get_session
from core.models import InvestimentoSnapshot

# Classes usadas para agrupar a carteira no painel.
CLASSES = [
    "Renda Fixa",
    "Renda Variável",
    "FII",
    "Ação",
    "ETF",
    "Internacional",
    "Caixa",
    "Outros",
]

MOEDAS = ["BRL", "USD"]

# Cotação USD→BRL sugerida no primeiro snapshot (o usuário ajusta na tela).
COTACAO_USD_PADRAO = 5.40

DATA_SNAPSHOT_INICIAL = date(2026, 6, 1)

# ---------------------------------------------------------------------------
# Posições iniciais de exemplo (privacidade): nenhuma carteira real fica no
# código. Os dados reais ficam só no banco (local SQLite ou Postgres na nuvem),
# nunca versionados. Para começar do zero, cadastre as posições direto na tela
# de Investimentos (tabela editável). Cada item:
# (ativo, classe, moeda, quantidade, preco_unitario, valor_mercado, valor_investido)
# ---------------------------------------------------------------------------
POSICOES_INICIAIS: List[tuple] = []


# Metadados de cotação inferidos do nome do ativo (Fase 13). Cada item:
# (trecho_no_nome, {ticker | indexador+taxa_indice}). A busca é por substring.
METADADOS_CONHECIDOS = [
    # FIIs / ações / ETFs (B3) e BDRs — o ticker já aparece no nome.
    ("AUVP11", {"ticker": "AUVP11"}),
    ("AUPO11", {"ticker": "AUPO11"}),
    ("MCCI11", {"ticker": "MCCI11"}),
    ("HGCR11", {"ticker": "HGCR11"}),
    ("COPN11", {"ticker": "COPN11"}),
    ("BTLG11", {"ticker": "BTLG11"}),
    ("RBVA11", {"ticker": "RBVA11"}),
    ("HODL11", {"ticker": "HODL11"}),
    ("MELI34", {"ticker": "MELI34"}),
    ("BBAS3", {"ticker": "BBAS3"}),
    ("SAPR4", {"ticker": "SAPR4"}),
    ("CMIG4", {"ticker": "CMIG4"}),
    ("TAEE11", {"ticker": "TAEE11"}),
    ("EGIE3", {"ticker": "EGIE3"}),
    # ETFs internacionais (USD).
    ("VIG", {"ticker": "VIG"}),
    ("XLU", {"ticker": "XLU"}),
    # Renda fixa pós-fixada (estimativa por carrego no CDI).
    ("102% CDI", {"indexador": "CDI", "taxa_indice": 102.0}),
    ("Tesouro Selic", {"indexador": "CDI", "taxa_indice": 100.0}),
    ("Yield DI", {"indexador": "CDI", "taxa_indice": 100.0}),
]


def _valor_brl(valor_mercado: float, cotacao: Optional[float]) -> float:
    return float(valor_mercado) * float(cotacao or 1.0)


def preencher_metadados_conhecidos(data_ref: date) -> int:
    """Preenche ticker/índice das posições reconhecidas pelo nome, sem
    sobrescrever o que já estiver definido. Retorna quantas linhas preencheu.

    A data de aplicação da renda fixa NÃO é inferida — o usuário informa."""
    linhas = carregar_snapshot(data_ref)
    if not linhas:
        return 0
    n = 0
    for ln in linhas:
        if ln.get("ticker") or ln.get("indexador"):
            continue  # já configurado
        nome = ln.get("ativo") or ""
        for trecho, meta in METADADOS_CONHECIDOS:
            if trecho.lower() in nome.lower():
                ln.update(meta)
                n += 1
                break
    if n:
        salvar_snapshot(data_ref, linhas, cotacao_usd=cotacao_usd_do_snapshot(data_ref))
    return n


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def listar_datas() -> List[date]:
    """Datas que possuem snapshot, da mais recente para a mais antiga."""
    with get_session() as s:
        datas = s.scalars(
            select(distinct(InvestimentoSnapshot.data)).order_by(InvestimentoSnapshot.data.desc())
        ).all()
        return list(datas)


def existe_snapshot() -> bool:
    with get_session() as s:
        return s.scalar(select(InvestimentoSnapshot.id).limit(1)) is not None


def criar_snapshot_inicial() -> bool:
    """Grava o snapshot pré-preenchido se a carteira ainda estiver vazia.

    Retorna True se criou, False se já existia algum snapshot.
    """
    if existe_snapshot() or not POSICOES_INICIAIS:
        return False
    linhas = [
        {
            "ativo": ativo,
            "classe_ativo": classe,
            "moeda": moeda,
            "quantidade": qtd,
            "preco_unitario": pu,
            "valor_mercado": vm,
            "valor_investido": vi,
        }
        for (ativo, classe, moeda, qtd, pu, vm, vi) in POSICOES_INICIAIS
    ]
    salvar_snapshot(DATA_SNAPSHOT_INICIAL, linhas, cotacao_usd=COTACAO_USD_PADRAO)
    return True


def carregar_snapshot(data_ref: date) -> List[dict]:
    with get_session() as s:
        stmt = (
            select(InvestimentoSnapshot)
            .where(InvestimentoSnapshot.data == data_ref)
            .order_by(InvestimentoSnapshot.classe_ativo, InvestimentoSnapshot.ativo)
        )
        return [
            {
                "ativo": p.ativo,
                "classe_ativo": p.classe_ativo,
                "moeda": p.moeda,
                "quantidade": p.quantidade,
                "preco_unitario": p.preco_unitario,
                "valor_mercado": p.valor_mercado,
                "valor_investido": p.valor_investido,
                "ticker": p.ticker,
                "indexador": p.indexador,
                "taxa_indice": p.taxa_indice,
                "data_aplicacao": p.data_aplicacao,
            }
            for p in s.scalars(stmt).all()
        ]


def cotacao_usd_do_snapshot(data_ref: date) -> float:
    """Recupera a cotação USD usada num snapshot (a dos ativos em USD)."""
    with get_session() as s:
        c = s.scalar(
            select(InvestimentoSnapshot.cotacao)
            .where(InvestimentoSnapshot.data == data_ref)
            .where(InvestimentoSnapshot.moeda == "USD")
            .limit(1)
        )
        return float(c) if c else COTACAO_USD_PADRAO


def salvar_snapshot(data_ref: date, linhas: List[dict], cotacao_usd: float) -> None:
    """Substitui todas as posições da data por `linhas`.

    Cada linha: {ativo, classe_ativo, moeda, quantidade, preco_unitario,
    valor_mercado, valor_investido}. A cotação USD→BRL é aplicada às linhas
    em USD; linhas em BRL ficam com cotacao=1.0.
    """
    with get_session() as s:
        antigas = s.scalars(
            select(InvestimentoSnapshot).where(InvestimentoSnapshot.data == data_ref)
        ).all()
        for p in antigas:
            s.delete(p)
        s.flush()

        for ln in linhas:
            ativo = (ln.get("ativo") or "").strip()
            vm = ln.get("valor_mercado")
            if not ativo or vm in (None, ""):
                continue  # ignora linhas em branco da tabela editável
            moeda = (ln.get("moeda") or "BRL").upper()
            cot = float(cotacao_usd) if moeda == "USD" else 1.0
            ticker = (ln.get("ticker") or "").strip().upper() or None
            indexador = (ln.get("indexador") or "").strip().upper() or None
            s.add(
                InvestimentoSnapshot(
                    data=data_ref,
                    ativo=ativo,
                    classe_ativo=ln.get("classe_ativo") or "Outros",
                    moeda=moeda,
                    quantidade=ln.get("quantidade"),
                    preco_unitario=ln.get("preco_unitario"),
                    valor_mercado=float(vm),
                    cotacao=cot,
                    valor_investido=ln.get("valor_investido"),
                    ticker=ticker,
                    indexador=indexador,
                    taxa_indice=ln.get("taxa_indice"),
                    data_aplicacao=ln.get("data_aplicacao"),
                )
            )


def adicionar_posicao(linha: dict, data_ref: Optional[date] = None) -> date:
    """Acrescenta UMA posição ao snapshot informado (ou ao mais recente; se não
    houver nenhum, cria um para hoje). Retorna a data do snapshot afetado."""
    datas = listar_datas()
    if data_ref is None:
        data_ref = datas[0] if datas else date.today()
    existe = data_ref in datas
    linhas = carregar_snapshot(data_ref) if existe else []
    linhas.append(linha)
    cot = cotacao_usd_do_snapshot(data_ref) if existe else COTACAO_USD_PADRAO
    salvar_snapshot(data_ref, linhas, cotacao_usd=cot)
    return data_ref


def excluir_snapshot(data_ref: date) -> None:
    with get_session() as s:
        for p in s.scalars(
            select(InvestimentoSnapshot).where(InvestimentoSnapshot.data == data_ref)
        ).all():
            s.delete(p)


# ---------------------------------------------------------------------------
# Agregações
# ---------------------------------------------------------------------------
def total_carteira(data_ref: date) -> float:
    """Patrimônio total em BRL na data (converte USD pela cotação gravada)."""
    with get_session() as s:
        posicoes = s.scalars(
            select(InvestimentoSnapshot).where(InvestimentoSnapshot.data == data_ref)
        ).all()
        return sum(_valor_brl(p.valor_mercado, p.cotacao) for p in posicoes)


def por_classe(data_ref: date) -> List[dict]:
    """Soma em BRL por classe de ativo, da maior para a menor."""
    with get_session() as s:
        posicoes = s.scalars(
            select(InvestimentoSnapshot).where(InvestimentoSnapshot.data == data_ref)
        ).all()
        acc: dict = {}
        for p in posicoes:
            acc[p.classe_ativo or "Outros"] = acc.get(p.classe_ativo or "Outros", 0.0) + _valor_brl(
                p.valor_mercado, p.cotacao
            )
    itens = [{"classe": k, "total": v} for k, v in acc.items()]
    itens.sort(key=lambda x: x["total"], reverse=True)
    return itens


def rendimento(data_ref: date) -> dict:
    """Rendimento em BRL (valor_mercado - valor_investido) das posições que
    têm custo conhecido. Retorna {investido, mercado, lucro, percentual}."""
    with get_session() as s:
        posicoes = s.scalars(
            select(InvestimentoSnapshot)
            .where(InvestimentoSnapshot.data == data_ref)
            .where(InvestimentoSnapshot.valor_investido.is_not(None))
        ).all()
        investido = sum(_valor_brl(p.valor_investido, p.cotacao) for p in posicoes)
        mercado = sum(_valor_brl(p.valor_mercado, p.cotacao) for p in posicoes)
    lucro = mercado - investido
    pct = (lucro / investido * 100.0) if investido else 0.0
    return {"investido": investido, "mercado": mercado, "lucro": lucro, "percentual": pct}


def evolucao() -> List[dict]:
    """Patrimônio total (BRL) por data de snapshot, em ordem cronológica."""
    datas = sorted(listar_datas())
    return [{"data": d, "total": total_carteira(d)} for d in datas]
