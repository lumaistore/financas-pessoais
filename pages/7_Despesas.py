"""Despesas manuais — PIX, boleto, débito, Caju etc. (Fase 8).

Para gastos que não vêm de fatura de cartão. Entram no painel mensal junto com
o cartão e podem ser marcados como LUMAI (reembolso).
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.cartao import listar_categorias
from services.despesas import (
    FORMAS,
    adicionar_despesa,
    excluir_despesa,
    listar_despesas,
    total_despesas,
    total_lumai_despesas,
)

init_db()

st.title("Despesas (PIX, boleto, Caju…)")
st.caption("Lance aqui os gastos que não estão na fatura do cartão. Marque LUMAI no que for reembolso da empresa.")

# --- Cadastro -------------------------------------------------------------
categorias = [c["nome"] for c in listar_categorias()]
with st.expander("➕ Nova despesa", expanded=True):
    with st.form("nova_despesa", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_ = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            forma = st.selectbox("Forma de pagamento", FORMAS)
        with col2:
            descricao = st.text_input("Descrição", placeholder="Ex.: Mercado, Uber, Almoço")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
        with col3:
            categoria = st.selectbox("Categoria", ["(sem categoria)"] + categorias)
            lumai = st.checkbox("É despesa LUMAI (reembolso)")

        enviado = st.form_submit_button("Adicionar despesa", type="primary")
        if enviado:
            if not descricao.strip():
                st.error("Informe a descrição.")
            elif valor <= 0:
                st.error("O valor deve ser maior que zero.")
            else:
                adicionar_despesa(
                    data_=data_,
                    descricao=descricao,
                    valor=float(valor),
                    forma=forma,
                    categoria=None if categoria == "(sem categoria)" else categoria,
                    lumai=lumai,
                )
                st.success("Despesa adicionada.")
                st.rerun()

st.divider()

# --- Filtro por mês -------------------------------------------------------
mes_ref = st.text_input("Mês de referência (AAAA-MM)", value=date.today().strftime("%Y-%m"))

t1, t2 = st.columns(2)
t1.metric("Total de despesas no mês", f"R$ {total_despesas(mes_ref):,.2f}")
t2.metric(
    "💼 Total LUMAI no mês (a reembolsar)",
    f"R$ {total_lumai_despesas(mes_ref):,.2f}",
    help="Soma das despesas manuais marcadas como LUMAI neste mês.",
)

# --- Lista ----------------------------------------------------------------
despesas = listar_despesas(mes_ref)
if not despesas:
    st.info("Nenhuma despesa manual neste mês.")
    st.stop()

df = pd.DataFrame(despesas)


def _pinta_lumai(row):
    cor = "background-color: #fff3cd" if row["lumai"] else ""
    return [cor] * len(row)


df_view = df[["data", "descricao", "categoria", "forma", "valor", "lumai"]].copy()
styler = (
    df_view.style.apply(_pinta_lumai, axis=1)
    .format({"valor": "R$ {:,.2f}"})
)
st.dataframe(
    styler,
    use_container_width=True,
    hide_index=True,
    column_config={
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "categoria": "Categoria",
        "forma": "Forma",
        "valor": "Valor (R$)",
        "lumai": st.column_config.CheckboxColumn("LUMAI"),
    },
)

# --- Excluir --------------------------------------------------------------
st.caption("Excluir uma despesa:")
opcoes = {
    f"{d['data'].strftime('%d/%m')} · {d['descricao']} · R$ {d['valor']:,.2f}": d["id"]
    for d in despesas
}
col_x, col_y = st.columns([3, 1])
with col_x:
    escolha = st.selectbox("Despesa", list(opcoes.keys()), label_visibility="collapsed")
with col_y:
    if st.button("Excluir", type="secondary"):
        excluir_despesa(opcoes[escolha])
        st.rerun()
