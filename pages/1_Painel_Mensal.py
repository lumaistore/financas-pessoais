"""Painel Mensal — visão consolidada.

Fluxo do mês (movimentações unificadas) + patrimônio + compromissos.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.backup import criar_backup, listar_backups
from services.cartao import gasto_total, reembolso_lumai_por_fatura
from services.compromissos import (
    contar_ativos,
    listar_compromissos,
    total_financiamento_a_contratar,
    total_parcelas_mes,
    total_saldo_devedor,
)
from services.cotacoes import buscar_dolar
from services.investimentos import (
    cotacao_usd_do_snapshot,
    evolucao,
    listar_datas,
    por_classe,
    rendimento,
    total_carteira,
)
from services.movimentacoes import (
    por_categoria,
    resumo_mes,
    total_lumai_a_reembolsar,
)

init_db()

st.title("Painel Mensal")
st.caption("Visão consolidada: fluxo do mês, patrimônio e compromissos.")

mes_ref = st.text_input("Mês de referência (AAAA-MM)", value=date.today().strftime("%Y-%m"))

# ---------------------------------------------------------------------------
# Fluxo do mês (movimentações)
# ---------------------------------------------------------------------------
st.subheader("Fluxo do mês")
r = resumo_mes(mes_ref)
gasto_cartao = gasto_total(mes_ref)  # ainda considera fatura de cartão
parcelas_mes = total_parcelas_mes(mes_ref)

recebido = r["receitas"]
# Gasto real = despesas suas (excluindo LUMAI) + gasto no cartão (via fatura)
gasto_total_mes = r["despesas"] + gasto_cartao
sobra = recebido - gasto_total_mes - parcelas_mes - r["aplicacoes"] + r["resgates"]

col1, col2 = st.columns(2)
col1.metric("Recebido", f"R$ {recebido:,.2f}",
            help="Receitas classificadas nas movimentações do mês.")
col2.metric(
    "Gasto (real)",
    f"R$ {gasto_total_mes:,.2f}",
    help=(f"Cartão R$ {gasto_cartao:,.2f} + despesas movimentações R$ {r['despesas']:,.2f}. "
          "Exclui LUMAI e transferências entre suas contas."),
)
col3, col4 = st.columns(2)
col3.metric("Parcelas/compromissos", f"R$ {parcelas_mes:,.2f}")
col4.metric(
    "Aplicado (investimentos)",
    f"R$ {r['aplicacoes']:,.2f}",
    help="Enviado para conta de aplicação (BTG etc.).",
)

st.metric(
    "💰 Sobra do mês",
    f"R$ {sobra:,.2f}",
    help="Recebido − Gasto − Parcelas − Aplicações + Resgates.",
)

# Reembolso LUMAI (a receber)
lumai_cartoes = sum(x["total"] for x in reembolso_lumai_por_fatura())
lumai_movs = total_lumai_a_reembolsar()
if lumai_cartoes or lumai_movs:
    st.info(
        f"💼 **Reembolso LUMAI a receber:** R\\$ {lumai_cartoes:,.2f} em faturas de cartão "
        f"+ R\\$ {lumai_movs:,.2f} em movimentações."
    )

st.divider()

# ---------------------------------------------------------------------------
# Patrimônio
# ---------------------------------------------------------------------------
st.subheader("Patrimônio")
datas_inv = listar_datas()
if datas_inv:
    data_inv = datas_inv[0]
    patrimonio = total_carteira(data_inv)
    rend = rendimento(data_inv)
    saldo_dev = total_saldo_devedor()
    financ = total_financiamento_a_contratar()
    patrimonio_liq = patrimonio - saldo_dev

    p1, p2 = st.columns(2)
    p1.metric("Carteira de investimentos", f"R$ {patrimonio:,.2f}",
              help=f"Posição de {data_inv.strftime('%d/%m/%Y')}.")
    p2.metric("Rendimento (custo conhecido)",
              f"R$ {rend['lucro']:,.2f}", f"{rend['percentual']:.2f}%")
    p3, p4 = st.columns(2)
    p3.metric("Saldo devedor (compromissos)", f"R$ {saldo_dev:,.2f}")
    p4.metric("Patrimônio líquido", f"R$ {patrimonio_liq:,.2f}",
              help="Carteira − saldo devedor.")
    if financ:
        st.caption(f"Além disso: R$ {financ:,.2f} de financiamento a contratar na entrega.")

    # Dólar
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

    # Evolução da carteira
    evo = evolucao()
    if len(evo) > 1:
        st.caption("Evolução da carteira:")
        df_evo = pd.DataFrame(evo)
        df_evo["data"] = df_evo["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
        st.line_chart(df_evo.set_index("data"))
else:
    st.caption("Nenhuma posição registrada. Cadastre em **Investimentos**.")

st.divider()

# ---------------------------------------------------------------------------
# Gasto por categoria (unificado)
# ---------------------------------------------------------------------------
st.subheader("Gasto por categoria")
por_cat = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
# Somar cartão por categoria (para consistência - vem da própria movimentação
# se você importou a fatura, senão fica só com movimentações do extrato).
if por_cat:
    df_cat = pd.DataFrame(por_cat)
    df_cat["total"] = df_cat["total"].astype(float)
    c1, c2 = st.columns([2, 1])
    with c1:
        st.bar_chart(df_cat.set_index("categoria"))
    with c2:
        df_show = df_cat.copy()
        df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
        df_show.columns = ["Categoria", "Total"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)
else:
    st.caption("Sem despesas nas movimentações deste mês. Importe um extrato em **Extrato Bancario**.")

# Distribuição por classe
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
# Compromissos
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
                f"saldo à vista R\\$ {c['saldo_devedor']:,.2f} · "
                f"financiamento R\\$ {c['financiamento']:,.2f} · próxima {prox}"
            )
        else:
            st.write(
                f"**{c['nome']}** — {c['parcelas_pagas']}/{c['total_parcelas']} pagas · "
                f"saldo R\\$ {c['saldo_devedor']:,.2f} · próxima {prox}"
            )
else:
    st.caption("Nenhum compromisso ativo.")

st.divider()

# ---------------------------------------------------------------------------
# Backup
# ---------------------------------------------------------------------------
with st.expander("💾 Backup dos dados"):
    if st.button("Fazer backup agora"):
        caminho = criar_backup()
        st.success(f"Backup criado: {caminho}")
    backups = listar_backups()
    if backups:
        df_bk = pd.DataFrame(backups)
        df_bk["modificado"] = df_bk["modificado"].apply(lambda d: d.strftime("%d/%m/%Y %H:%M"))
        df_bk.columns = ["Arquivo", "Tamanho (KB)", "Criado em"]
        st.dataframe(df_bk, use_container_width=True, hide_index=True)
