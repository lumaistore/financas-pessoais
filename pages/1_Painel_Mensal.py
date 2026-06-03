"""Painel Mensal — visão consolidada (Fase 5).

Reúne num só lugar o fluxo do mês (receitas, gastos de cartão, parcelas),
o patrimônio (carteira de investimentos + rendimento) e os compromissos em
andamento (parcelamentos, financiamentos e imóveis). Tudo calculado a partir
dos dados locais — nada sai da máquina.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.cartao import gasto_por_categoria, gasto_total, reembolso_lumai_por_fatura
from services.compromissos import (
    contar_ativos,
    listar_compromissos,
    total_financiamento_a_contratar,
    total_parcelas_mes,
    total_saldo_devedor,
)
from services.despesas import (
    despesas_por_categoria,
    total_despesas,
    total_lumai_despesas,
)
from services.investimentos import (
    cotacao_usd_do_snapshot,
    evolucao,
    listar_datas,
    por_classe,
    rendimento,
    total_carteira,
)
from services.cotacoes import buscar_dolar
from services.orcamento import status_orcamento
from services.planejamento import reserva_meses
from services.backup import criar_backup, listar_backups
from services.receitas import total_recebido

init_db()

st.title("Painel Mensal")
st.caption("Visão consolidada das suas finanças — fluxo do mês, patrimônio e compromissos.")

mes_ref = st.text_input("Mês de referência (AAAA-MM)", value=date.today().strftime("%Y-%m"))

# ---------------------------------------------------------------------------
# Fluxo do mês
# ---------------------------------------------------------------------------
st.subheader("Fluxo do mês")
recebido = total_recebido(mes_ref)
gasto_cartao = gasto_total(mes_ref)
gasto_manual = total_despesas(mes_ref)
gasto = gasto_cartao + gasto_manual
parcelas_mes = total_parcelas_mes(mes_ref)
saldo_mes = recebido - gasto - parcelas_mes

col1, col2 = st.columns(2)
col1.metric("Recebido", f"R$ {recebido:,.2f}")
col2.metric(
    "Gasto (cartão + despesas)",
    f"R$ {gasto:,.2f}",
    help=f"Cartão R$ {gasto_cartao:,.2f} + despesas (PIX/boleto/Caju) R$ {gasto_manual:,.2f}.",
)
col3, col4 = st.columns(2)
col3.metric("Parcelas/compromissos", f"R$ {parcelas_mes:,.2f}")
col4.metric(
    "Sobra do mês",
    f"R$ {saldo_mes:,.2f}",
    help="Recebido − gasto (cartão + despesas) − parcelas do mês (não inclui aportes em investimentos).",
)

# Reembolso LUMAI (despesas da empresa a recuperar).
lumai_cartoes = sum(r["total"] for r in reembolso_lumai_por_fatura())
lumai_despesas_mes = total_lumai_despesas(mes_ref)
if lumai_cartoes or lumai_despesas_mes:
    st.info(
        f"💼 **Reembolso LUMAI a receber:** R\\$ {lumai_cartoes:,.2f} em faturas de cartão "
        f"(todas) + R\\$ {lumai_despesas_mes:,.2f} em despesas deste mês."
    )

st.divider()

# ---------------------------------------------------------------------------
# Patrimônio
# ---------------------------------------------------------------------------
st.subheader("Patrimônio")
datas_inv = listar_datas()
if datas_inv:
    data_inv = datas_inv[0]  # snapshot mais recente
    patrimonio = total_carteira(data_inv)
    rend = rendimento(data_inv)
    saldo_dev = total_saldo_devedor()
    financ = total_financiamento_a_contratar()
    patrimonio_liq = patrimonio - saldo_dev

    p1, p2 = st.columns(2)
    p1.metric(
        "Carteira de investimentos",
        f"R$ {patrimonio:,.2f}",
        help=f"Posição de {data_inv.strftime('%d/%m/%Y')}.",
    )
    p2.metric(
        "Rendimento (custo conhecido)",
        f"R$ {rend['lucro']:,.2f}",
        f"{rend['percentual']:.2f}%",
    )
    p3, p4 = st.columns(2)
    p3.metric("Saldo devedor (compromissos)", f"R$ {saldo_dev:,.2f}")
    p4.metric(
        "Patrimônio líquido",
        f"R$ {patrimonio_liq:,.2f}",
        help="Carteira de investimentos − saldo devedor dos compromissos.",
    )
    if financ:
        st.caption(
            f"Além disso, há R$ {financ:,.2f} de financiamento imobiliário a "
            "contratar na entrega das chaves (fora do saldo mensal)."
        )

    # Dólar do momento (última cotação conhecida; botão busca a atual).
    dolar = st.session_state.get("dolar_agora") or float(cotacao_usd_do_snapshot(data_inv))
    d1, d2 = st.columns([1, 3])
    d1.metric("💵 Dólar (USD→BRL)", f"R$ {dolar:,.4f}")
    with d2:
        st.write("")
        if st.button("Atualizar dólar"):
            v = buscar_dolar()
            if v:
                st.session_state["dolar_agora"] = v
            st.rerun()

    # Reserva de emergência: quantos meses de gasto a parte líquida cobre.
    rm = reserva_meses()
    if rm["reserva"]:
        meses_cobertos = rm["meses"]
        nivel = "🟢" if meses_cobertos >= 6 else ("🟡" if meses_cobertos >= 3 else "🔴")
        r1, r2, r3 = st.columns(3)
        r1.metric(
            "Reserva de emergência",
            f"R$ {rm['reserva']:,.2f}",
            help="Soma das classes líquidas da carteira (Caixa + Renda Fixa).",
        )
        r2.metric("Gasto médio mensal", f"R$ {rm['gasto_medio']:,.2f}")
        r3.metric(
            f"{nivel} Cobertura",
            f"{meses_cobertos:.1f} meses",
            help="Quantos meses de gasto médio a sua reserva cobre. O ideal costuma ser 6+ meses.",
        )

    # Evolução da carteira ao longo dos snapshots.
    evo = evolucao()
    if len(evo) > 1:
        st.caption("Evolução da carteira (por snapshot):")
        df_evo = pd.DataFrame(evo)
        df_evo["data"] = df_evo["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
        st.line_chart(df_evo.set_index("data"))
else:
    st.caption("Nenhuma posição de investimento registrada. Cadastre em **Investimentos**.")

st.divider()

# ---------------------------------------------------------------------------
# Gasto por categoria
# ---------------------------------------------------------------------------
st.subheader("Gasto por categoria")
# Junta cartão + despesas manuais na mesma visão.
_acc: dict = {}
for item in gasto_por_categoria(mes_ref) + despesas_por_categoria(mes_ref):
    _acc[item["categoria"]] = _acc.get(item["categoria"], 0.0) + item["total"]
por_cat = sorted(
    [{"categoria": k, "total": v} for k, v in _acc.items()],
    key=lambda x: x["total"],
    reverse=True,
)
if por_cat:
    df_cat = pd.DataFrame(por_cat)
    c1, c2 = st.columns([2, 1])
    with c1:
        st.bar_chart(df_cat.set_index("categoria"))
    with c2:
        df_show = df_cat.copy()
        df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
        df_show.columns = ["Categoria", "Total"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
else:
    st.caption("Sem gastos importados para este mês. Importe uma fatura em **Faturas de Cartão**.")

# ---------------------------------------------------------------------------
# Orçamento do mês (metas por categoria)
# ---------------------------------------------------------------------------
status_orc = status_orcamento(mes_ref)
if status_orc:
    st.subheader("Orçamento do mês")
    estourados = [s for s in status_orc if s["estourou"]]
    if estourados:
        nomes = ", ".join(s["categoria"] for s in estourados)
        st.warning(f"⚠️ Estourou o orçamento em: **{nomes}**.")
    for s in status_orc:
        cor = "🔴" if s["estourou"] else ("🟡" if s["percentual"] >= 80 else "🟢")
        st.write(
            f"{cor} **{s['categoria']}** — R\\$ {s['gasto']:,.2f} de R\\$ {s['limite']:,.2f} "
            f"({s['percentual']:.0f}%)"
        )
        st.progress(min(s["percentual"] / 100.0, 1.0))
    st.caption("Defina ou ajuste as metas em **Orçamento**.")

# ---------------------------------------------------------------------------
# Distribuição da carteira por classe
# ---------------------------------------------------------------------------
if datas_inv:
    st.subheader("Distribuição da carteira por classe")
    classes = por_classe(datas_inv[0])
    if classes:
        df_cls = pd.DataFrame(classes)
        cc1, cc2 = st.columns([2, 1])
        with cc1:
            st.bar_chart(df_cls.set_index("classe"))
        with cc2:
            df_show = df_cls.copy()
            df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
            df_show.columns = ["Classe", "Total"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Compromissos em andamento
# ---------------------------------------------------------------------------
st.subheader("Compromissos em andamento")
ativos = listar_compromissos(apenas_ativos=True)
if ativos:
    c1, c2 = st.columns(2)
    c1.metric("Compromissos ativos", contar_ativos())
    c2.metric("Saldo devedor total", f"R$ {total_saldo_devedor():,.2f}")
    for c in ativos:
        prox = c["proxima_data"].strftime("%d/%m/%Y") if c["proxima_data"] else "—"
        if c.get("eh_imovel"):
            st.write(
                f"🏢 **{c['nome']}** — {c['progresso']*100:.0f}% do plano pago · "
                f"saldo à vista R$ {c['saldo_devedor']:,.2f} · "
                f"financiamento R$ {c['financiamento']:,.2f} · próxima {prox}"
            )
        else:
            st.write(
                f"**{c['nome']}** — {c['parcelas_pagas']}/{c['total_parcelas']} pagas · "
                f"saldo R$ {c['saldo_devedor']:,.2f} · próxima {prox}"
            )
else:
    st.caption("Nenhum compromisso ativo. Cadastre em **Financiamentos**.")

st.divider()

# ---------------------------------------------------------------------------
# Backup dos dados
# ---------------------------------------------------------------------------
with st.expander("💾 Backup dos dados"):
    st.caption(
        "Cria uma cópia de segurança do banco local (`financas.db`) em "
        "`data/backups/`. Tudo continua só na sua máquina."
    )
    if st.button("Fazer backup agora"):
        caminho = criar_backup()
        st.success(f"Backup criado: {caminho}")
    backups = listar_backups()
    if backups:
        df_bk = pd.DataFrame(backups)
        df_bk["modificado"] = df_bk["modificado"].apply(lambda d: d.strftime("%d/%m/%Y %H:%M"))
        df_bk.columns = ["Arquivo", "Tamanho (KB)", "Criado em"]
        st.dataframe(df_bk, use_container_width=True, hide_index=True)
