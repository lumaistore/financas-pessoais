"""Movimentações — visão unificada de entradas e saídas do mês.

Substitui as abas separadas de Receitas e Despesas. Cada linha tem tipo
classificado automaticamente (receita/despesa/transferência/aplicação),
com detecção inteligente vinda do cadastro de contas.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.cartao import listar_categorias
from services.contas import listar_contas
from services.movimentacoes import (
    FORMAS,
    TIPOS,
    adicionar,
    atualizar,
    classificar,
    excluir,
    listar,
    por_categoria,
    resumo_mes,
    total_lumai_a_reembolsar,
)

init_db()

st.title("💰 Movimentações")
st.caption(
    "Todas as entradas e saídas do mês em um só lugar. "
    "Transferências entre suas contas e aplicações **não** contam no fluxo real."
)

mes_ref = st.text_input("Mês (AAAA-MM)", value=date.today().strftime("%Y-%m"))

# --- Resumo ----------------------------------------------------------------
r = resumo_mes(mes_ref)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Recebido", f"R$ {r['receitas']:,.2f}")
c2.metric("Gasto (real)", f"R$ {r['despesas']:,.2f}",
          help="Só despesas suas — exclui LUMAI e transferências entre contas.")
c3.metric("Aplicado", f"R$ {r['aplicacoes']:,.2f}",
          help="Enviado para conta de aplicação (BTG etc.).")
c4.metric("Saldo do mês", f"R$ {r['saldo']:,.2f}",
          help="Recebido − Gasto − Aplicado + Resgates.")

lumai_pend = total_lumai_a_reembolsar(mes_ref)
if lumai_pend:
    st.info(f"💼 R$ {lumai_pend:,.2f} em despesas LUMAI a reembolsar (não contam no gasto).")

st.divider()

# --- Nova movimentação -----------------------------------------------------
categorias = [c["nome"] for c in listar_categorias()]
contas = listar_contas()
opcoes_conta = {"(nenhuma)": None, **{c["apelido"]: c["id"] for c in contas}}

with st.expander("➕ Adicionar movimentação"):
    with st.form("nova_mov", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_ = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            descricao = st.text_input("Descrição", placeholder="Ex.: Mercado, Salário, PIX Maria")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
        with col2:
            tipo = st.selectbox("Tipo", TIPOS)
            forma = st.selectbox("Forma", ["(nenhuma)"] + FORMAS)
            conta_apelido = st.selectbox("Conta", list(opcoes_conta.keys()),
                                          help="Qual conta a movimentação afetou.")
        with col3:
            categoria = st.selectbox("Categoria", ["(sem)"] + categorias)
            lumai = st.checkbox("LUMAI (reembolsar)")
            obs = st.text_input("Observação")

        if st.form_submit_button("Adicionar", type="primary"):
            if not descricao.strip() or valor <= 0:
                st.error("Preencha descrição e valor.")
            else:
                adicionar(
                    data_=data_, descricao=descricao, valor=float(valor), tipo=tipo,
                    forma=None if forma == "(nenhuma)" else forma,
                    categoria=None if categoria == "(sem)" else categoria,
                    conta_id=opcoes_conta[conta_apelido],
                    lumai=lumai, observacao=obs, origem="manual",
                )
                st.success("Adicionada.")
                st.rerun()

# --- Lista + filtros -------------------------------------------------------
st.subheader(f"Movimentações em {mes_ref}")

filtros = st.multiselect(
    "Filtrar por tipo",
    TIPOS,
    default=["receita", "despesa", "aplicacao", "resgate"],
    help="Transferências ficam ocultas por padrão (não afetam o fluxo).",
)
movs = listar(mes_referencia=mes_ref, tipos=filtros)
if not movs:
    st.info("Sem movimentações neste filtro.")
    st.stop()

df = pd.DataFrame(movs)
df_view = df[["data", "descricao", "tipo", "categoria", "forma", "valor", "lumai", "origem"]].copy()
df_view["data"] = df_view["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
df_view["valor"] = df_view["valor"].apply(lambda v: f"R$ {v:,.2f}")
df_view["lumai"] = df_view["lumai"].map({True: "✅", False: ""})
df_view.columns = ["Data", "Descrição", "Tipo", "Categoria", "Forma", "Valor", "LUMAI", "Origem"]
st.dataframe(df_view, use_container_width=True, hide_index=True)

# --- Gasto por categoria ---------------------------------------------------
st.subheader("Gasto por categoria (só despesas suas)")
cats = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
if cats:
    df_cat = pd.DataFrame(cats).set_index("categoria")
    st.bar_chart(df_cat)

# --- Editar/excluir --------------------------------------------------------
st.divider()
st.subheader("Editar ou excluir")
opcoes = {
    f"{m['data'].strftime('%d/%m')} · {m['tipo']} · R$ {m['valor']:,.2f} · {m['descricao'][:40]}": m["id"]
    for m in movs
}
sel = st.selectbox("Movimentação", list(opcoes.keys()))
mid = opcoes[sel]
reg = next(m for m in movs if m["id"] == mid)

with st.container(border=True):
    e1, e2, e3 = st.columns(3)
    with e1:
        nd = st.date_input("Data", value=reg["data"], format="DD/MM/YYYY", key=f"ed_d_{mid}")
        ndes = st.text_input("Descrição", value=reg["descricao"], key=f"ed_ds_{mid}")
    with e2:
        nt = st.selectbox("Tipo", TIPOS, index=TIPOS.index(reg["tipo"]) if reg["tipo"] in TIPOS else 0, key=f"ed_t_{mid}")
        nf = st.selectbox("Forma", ["(nenhuma)"] + FORMAS,
                          index=(FORMAS.index(reg["forma"]) + 1) if reg["forma"] in FORMAS else 0,
                          key=f"ed_f_{mid}")
    with e3:
        nv = st.number_input("Valor", min_value=0.0, value=float(reg["valor"]), step=10.0, format="%.2f", key=f"ed_v_{mid}")
        nc = st.selectbox("Categoria", ["(sem)"] + categorias,
                          index=(categorias.index(reg["categoria"]) + 1) if reg["categoria"] in categorias else 0,
                          key=f"ed_c_{mid}")
        nl = st.checkbox("LUMAI", value=reg["lumai"], key=f"ed_l_{mid}")

    a1, a2 = st.columns(2)
    with a1:
        if st.button("💾 Salvar", key=f"sv_{mid}"):
            atualizar(mid, data=nd, descricao=ndes, valor=float(nv), tipo=nt,
                      forma=None if nf == "(nenhuma)" else nf,
                      categoria=None if nc == "(sem)" else nc, lumai=nl)
            st.rerun()
    with a2:
        if st.button("🗑️ Excluir", type="secondary", key=f"del_{mid}"):
            excluir(mid)
            st.rerun()
