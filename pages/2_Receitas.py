"""Tela de Receitas — cadastro e listagem das entradas do mês."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.receitas import (
    TIPOS,
    adicionar_receita,
    excluir_receita,
    listar_receitas,
    total_recebido,
)

init_db()

st.title("Receitas")
st.caption("Registre salário e outras entradas de forma simples.")

with st.form("nova_receita", clear_on_submit=True):
    col1, col2, col3 = st.columns(3)
    with col1:
        data_ = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
        fonte = st.text_input("Fonte", placeholder="Ex.: Salário, Freela, Aluguel")
    with col2:
        tipo = st.selectbox("Tipo", TIPOS)
        valor = st.number_input("Valor (R$)", min_value=0.0, step=100.0, format="%.2f")
    with col3:
        descricao = st.text_area("Descrição (opcional)", height=100)

    enviado = st.form_submit_button("Adicionar receita", type="primary")
    if enviado:
        if not fonte.strip():
            st.error("Informe a fonte da receita.")
        elif valor <= 0:
            st.error("O valor deve ser maior que zero.")
        else:
            adicionar_receita(data_, fonte.strip(), float(valor), tipo, descricao.strip() or None)
            st.success(f"Receita de R$ {valor:,.2f} adicionada.")
            st.rerun()

st.divider()

# Filtro por mês.
hoje = date.today()
mes_default = hoje.strftime("%Y-%m")
col_a, col_b = st.columns([1, 3])
with col_a:
    filtrar = st.checkbox("Filtrar por mês", value=True)
    mes_ref = st.text_input("Mês (AAAA-MM)", value=mes_default) if filtrar else None

receitas = listar_receitas(mes_ref if filtrar else None)
total = total_recebido(mes_ref if filtrar else None)

st.metric("Total recebido" + (f" em {mes_ref}" if filtrar else ""), f"R$ {total:,.2f}")

if receitas:
    df = pd.DataFrame(receitas)
    df_view = df[["data", "fonte", "tipo", "valor", "descricao"]].copy()
    df_view.columns = ["Data", "Fonte", "Tipo", "Valor (R$)", "Descrição"]
    st.dataframe(df_view, use_container_width=True, hide_index=True)

    st.subheader("Excluir receita")
    opcoes = {f"#{r['id']} — {r['data']} · {r['fonte']} · R$ {r['valor']:,.2f}": r["id"] for r in receitas}
    escolha = st.selectbox("Selecione", list(opcoes.keys()))
    if st.button("Excluir", type="secondary"):
        excluir_receita(opcoes[escolha])
        st.success("Receita excluída.")
        st.rerun()
else:
    st.info("Nenhuma receita registrada para o período selecionado.")
