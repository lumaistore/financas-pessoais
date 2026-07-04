"""Dados agregados para o Painel Mensal 2.0.

Reúne indicadores de fluxo, patrimônio, comparativos com mês anterior,
alertas e pendências de todas as áreas do app.
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List, Optional

from sqlalchemy import select

from core.cache import cache_leitura
from core.db import get_session
from core.models import Fatura, Movimentacao, RetiradaLucro, Exame


def mes_anterior(mes_ref: str) -> str:
    """Retorna o AAAA-MM do mês anterior."""
    ano, mes = mes_ref.split("-")
    m = int(mes) - 1
    y = int(ano)
    if m == 0:
        m = 12
        y -= 1
    return f"{y:04d}-{m:02d}"


def _delta_pct(atual: float, anterior: float) -> Optional[float]:
    if not anterior:
        return None
    return (atual - anterior) / abs(anterior) * 100


# ---------------------------------------------------------------------------
# Fluxo do mês com comparativo
# ---------------------------------------------------------------------------
@cache_leitura
def fluxo_com_delta(mes_ref: str) -> Dict:
    """Resumo do mês + comparativo (delta %) com o mês anterior."""
    from services.cartao import gasto_total
    from services.compromissos import total_parcelas_mes
    from services.movimentacoes import resumo_mes

    r = resumo_mes(mes_ref)
    r_ant = resumo_mes(mes_anterior(mes_ref))

    gasto_cartao = gasto_total(mes_ref)
    gasto_cartao_ant = gasto_total(mes_anterior(mes_ref))

    parcelas = total_parcelas_mes(mes_ref)
    parcelas_ant = total_parcelas_mes(mes_anterior(mes_ref))

    receitas = r["receitas"]
    gasto_real = r["despesas"] + gasto_cartao
    gasto_real_ant = r_ant["despesas"] + gasto_cartao_ant

    sobra = receitas - gasto_real - parcelas - r["aplicacoes"] + r["resgates"]
    sobra_ant = (r_ant["receitas"] - gasto_real_ant - parcelas_ant
                 - r_ant["aplicacoes"] + r_ant["resgates"])

    taxa_poupanca = ((r["aplicacoes"] + max(sobra, 0)) / receitas * 100) if receitas else 0
    taxa_ant = ((r_ant["aplicacoes"] + max(sobra_ant, 0)) / r_ant["receitas"] * 100) if r_ant["receitas"] else 0

    return {
        "receitas": receitas,
        "receitas_delta": _delta_pct(receitas, r_ant["receitas"]),
        "gasto_real": gasto_real,
        "gasto_cartao": gasto_cartao,
        "gasto_movimentacoes": r["despesas"],
        "gasto_delta": _delta_pct(gasto_real, gasto_real_ant),
        "aplicacoes": r["aplicacoes"],
        "aplicacoes_delta": _delta_pct(r["aplicacoes"], r_ant["aplicacoes"]),
        "resgates": r["resgates"],
        "parcelas": parcelas,
        "sobra": sobra,
        "sobra_delta": _delta_pct(sobra, sobra_ant),
        "taxa_poupanca": taxa_poupanca,
        "taxa_poupanca_delta": _delta_pct(taxa_poupanca, taxa_ant),
    }


# ---------------------------------------------------------------------------
# Fluxo por conta bancária (Seção 4)
# ---------------------------------------------------------------------------
@cache_leitura
def fluxo_por_conta(mes_ref: str) -> List[Dict]:
    """Retorna entradas/saídas por conta no mês."""
    from services.contas import listar_contas

    contas = listar_contas()
    with get_session() as s:
        movs = s.scalars(
            select(Movimentacao).where(Movimentacao.mes_referencia == mes_ref)
        ).all()
        resultado = []
        for c in contas:
            entradas = sum(
                m.valor for m in movs
                if m.conta_id == c["id"] and m.tipo in ("receita", "resgate")
            )
            saidas = sum(
                m.valor for m in movs
                if m.conta_id == c["id"] and m.tipo in ("despesa", "aplicacao")
                and not m.lumai
            )
            resultado.append({
                "apelido": c["apelido"], "banco": c["banco"], "tipo": c["tipo"],
                "entradas": entradas, "saidas": saidas,
                "saldo_mes": entradas - saidas,
            })
        return resultado


# ---------------------------------------------------------------------------
# Top despesas do mês
# ---------------------------------------------------------------------------
@cache_leitura
def top_despesas(mes_ref: str, n: int = 5) -> List[Dict]:
    with get_session() as s:
        movs = s.scalars(
            select(Movimentacao)
            .where(Movimentacao.mes_referencia == mes_ref)
            .where(Movimentacao.tipo == "despesa")
            .where(Movimentacao.lumai.is_(False))
            .order_by(Movimentacao.valor.desc())
            .limit(n)
        ).all()
        return [
            {"data": m.data, "descricao": m.descricao, "valor": m.valor,
             "categoria": m.categoria.nome if m.categoria else "Outros"}
            for m in movs
        ]


# ---------------------------------------------------------------------------
# Comparativo de categorias entre 2 meses
# ---------------------------------------------------------------------------
@cache_leitura
def variacao_por_categoria(mes_ref: str) -> List[Dict]:
    """Compara gastos por categoria do mês atual vs anterior."""
    from services.movimentacoes import por_categoria

    atual = {c["categoria"]: c["total"] for c in por_categoria(mes_ref)}
    anterior = {c["categoria"]: c["total"] for c in por_categoria(mes_anterior(mes_ref))}
    todas_cats = set(atual) | set(anterior)
    linhas = []
    for cat in todas_cats:
        a = atual.get(cat, 0)
        b = anterior.get(cat, 0)
        linhas.append({
            "categoria": cat, "atual": a, "anterior": b,
            "delta_valor": a - b, "delta_pct": _delta_pct(a, b),
        })
    linhas.sort(key=lambda x: abs(x["delta_valor"]), reverse=True)
    return linhas


# ---------------------------------------------------------------------------
# Dividendos / rendimentos recebidos no mês
# ---------------------------------------------------------------------------
@cache_leitura
def media_gasto_meses(mes_ref: str, n: int = 3) -> Dict:
    """Média do gasto real (despesas + cartão, excl. LUMAI) dos `n` meses
    ANTERIORES ao mês de referência. Ignora o mês corrente/parcial.

    Retorna {'media': float, 'meses_usados': [AAAA-MM], 'atual_vs_media_pct': float|None}.
    """
    from services.movimentacoes import total_por_tipo

    def _gasto_mes(m: str) -> float:
        # Fonte única: movimentações (já incluem o cartão após o sync).
        # Não somar gasto_total do cartão aqui — isso duplicaria o valor.
        return total_por_tipo(m, "despesa", excluir_lumai=True)

    # Coleta os n meses anteriores ao mes_ref.
    meses = []
    cursor = mes_ref
    for _ in range(n):
        cursor = mes_anterior(cursor)
        meses.append(cursor)
    meses = sorted(meses)  # crescente

    valores = [_gasto_mes(m) for m in meses]
    # Só conta meses que tiveram algum gasto (evita puxar a média pra baixo com
    # meses vazios sem dados).
    com_gasto = [(m, v) for m, v in zip(meses, valores) if v > 0]
    if not com_gasto:
        return {"media": 0.0, "meses_usados": [], "atual_vs_media_pct": None}

    media = sum(v for _, v in com_gasto) / len(com_gasto)
    atual = _gasto_mes(mes_ref)
    vs = ((atual - media) / media * 100) if media else None
    return {
        "media": media,
        "meses_usados": [m for m, _ in com_gasto],
        "atual_vs_media_pct": vs,
    }


@cache_leitura
def gastos_categoria_pivot() -> Dict:
    """Gasto por categoria em CADA mês com dados (para tabela mês a mês).

    Retorna {'meses': [AAAA-MM em ordem crescente],
             'linhas': [{'categoria': str, 'por_mes': {AAAA-MM: total}}]}.
    """
    from services.movimentacoes import meses_disponiveis, por_categoria

    meses = sorted(meses_disponiveis())
    dados: Dict[str, Dict[str, float]] = {}
    for m in meses:
        for row in por_categoria(m, tipo="despesa", excluir_lumai=True):
            dados.setdefault(row["categoria"], {})[m] = row["total"]
    linhas = [{"categoria": cat, "por_mes": v} for cat, v in dados.items()]
    linhas.sort(key=lambda x: sum(x["por_mes"].values()), reverse=True)
    # Só meses que têm alguma despesa (evita colunas vazias de meses só-receita).
    meses_com_gasto = sorted({m for v in dados.values() for m in v})
    return {"meses": meses_com_gasto, "linhas": linhas}


@cache_leitura
def dividendos_mes(mes_ref: str) -> float:
    """Aproximação: soma resgates + receitas que contenham palavras-chave
    típicas de proventos."""
    import re
    padrao = re.compile(
        r"(divid|jcp|juros\s+sobre\s+capital|rendim|provent|dpv)",
        re.I,
    )
    with get_session() as s:
        movs = s.scalars(
            select(Movimentacao).where(Movimentacao.mes_referencia == mes_ref)
        ).all()
        total = 0.0
        for m in movs:
            if m.tipo == "resgate":
                total += m.valor
            elif m.tipo == "receita" and m.descricao and padrao.search(m.descricao):
                total += m.valor
        return total


# ---------------------------------------------------------------------------
# Aportes acumulados no ano
# ---------------------------------------------------------------------------
@cache_leitura
def aportes_ano(ano: int) -> float:
    with get_session() as s:
        movs = s.scalars(
            select(Movimentacao).where(Movimentacao.tipo == "aplicacao")
        ).all()
        return sum(m.valor for m in movs if m.data.year == ano)


# ---------------------------------------------------------------------------
# Evolução do patrimônio líquido (últimos 12 meses)
# ---------------------------------------------------------------------------
@cache_leitura
def evolucao_patrimonio_liquido() -> List[Dict]:
    """Combina snapshots de investimento + saldo devedor por data. Fica
    aproximado pra dívida (usa a atual em todos os pontos), mas dá a
    ideia da trajetória."""
    from services.compromissos import total_saldo_devedor
    from services.investimentos import evolucao

    saldo_dev_atual = total_saldo_devedor()
    return [
        {"data": e["data"], "carteira": e["total"],
         "saldo_devedor": saldo_dev_atual,
         "patrimonio_liquido": e["total"] - saldo_dev_atual}
        for e in evolucao()
    ]


# ---------------------------------------------------------------------------
# Alertas inteligentes
# ---------------------------------------------------------------------------
@cache_leitura
def alertas(mes_ref: str) -> List[Dict]:
    """Retorna lista de alertas que merecem atenção do usuário.
    Cada alerta: {tipo, titulo, descricao, pagina_alvo, prioridade}."""
    from services.cartao import listar_faturas, reembolso_lumai_por_fatura
    from services.movimentacoes import total_lumai_a_reembolsar
    from services.backup import listar_backups

    a: List[Dict] = []

    # LUMAI a reembolsar
    lumai_cart = sum(x["total"] for x in reembolso_lumai_por_fatura())
    lumai_movs = total_lumai_a_reembolsar()
    lumai_total = lumai_cart + lumai_movs
    if lumai_total > 0:
        a.append({
            "tipo": "info",
            "titulo": f"💼 R$ {lumai_total:,.2f} em reembolso LUMAI a receber",
            "descricao": (f"R$ {lumai_cart:,.2f} em faturas de cartão + "
                          f"R$ {lumai_movs:,.2f} em despesas."),
            "pagina_alvo": "Faturas_Cartao",
            "prioridade": 2,
        })

    # Faturas com pendências de revisão
    faturas = listar_faturas()
    pendentes = [f for f in faturas if f.get("pendentes_revisao", 0) > 0]
    if pendentes:
        total_pendentes = sum(f["pendentes_revisao"] for f in pendentes)
        a.append({
            "tipo": "warning",
            "titulo": f"📋 {total_pendentes} transação(ões) de cartão sem revisar",
            "descricao": f"Em {len(pendentes)} fatura(s). Revise categorias e marque LUMAI se for.",
            "pagina_alvo": "Faturas_Cartao",
            "prioridade": 1,
        })

    # Faturas ainda em aberto
    em_aberto = [f for f in faturas if not f.get("fechada")]
    if em_aberto:
        a.append({
            "tipo": "info",
            "titulo": f"🧾 {len(em_aberto)} fatura(s) em aberto",
            "descricao": "Anexe o comprovante do pagamento e o sistema confirma o fechamento.",
            "pagina_alvo": "Faturas_Cartao",
            "prioridade": 3,
        })

    # Backup: quantos dias desde o último
    bks = listar_backups()
    if not bks:
        a.append({
            "tipo": "warning",
            "titulo": "💾 Nenhum backup ainda",
            "descricao": "Faça o primeiro backup pra proteger seus dados.",
            "pagina_alvo": None,
            "prioridade": 2,
        })
    else:
        dias = (date.today() - bks[0]["modificado"].date()).days
        if dias > 30:
            a.append({
                "tipo": "warning",
                "titulo": f"💾 Último backup há {dias} dias",
                "descricao": "Faça um novo para não perder alterações recentes.",
                "pagina_alvo": None,
                "prioridade": 2,
            })

    # Retiradas de lucros sem assinatura
    with get_session() as s:
        retiradas_sem_assin = s.scalars(
            select(RetiradaLucro).where(RetiradaLucro.assinado.is_(False))
        ).all()
    if retiradas_sem_assin:
        a.append({
            "tipo": "warning",
            "titulo": f"✍️ {len(retiradas_sem_assin)} recibo(s) de retirada sem assinatura",
            "descricao": "Baixe o PDF, assine e devolva na aba de retirada.",
            "pagina_alvo": "Retirada_de_Lucros",
            "prioridade": 2,
        })

    # Exames sem análise
    with get_session() as s:
        exames_sem = s.scalars(
            select(Exame).where(Exame.analise_ia.is_(None))
        ).all()
    if exames_sem:
        a.append({
            "tipo": "info",
            "titulo": f"🧪 {len(exames_sem)} exame(s) sem análise por IA",
            "descricao": "Peça a análise educativa para levar dúvidas ao médico.",
            "pagina_alvo": "Exames",
            "prioridade": 3,
        })

    a.sort(key=lambda x: x["prioridade"])
    return a
