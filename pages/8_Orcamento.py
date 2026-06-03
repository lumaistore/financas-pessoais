"""Orçamento mensal por categoria — metas/tetos de gasto (Fase 10)."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.cartao import listar_categorias
from services.orcamento import (
    definir_orcamento,
    excluir_orcamento,
    listar_orcamentos,
    status_orcamento,
)

init_db()

st.title("Orçamento do mês")
st.caption("Defina um teto de gasto por categoria. O painel acompanha quanto você já usou (cartão + despesas).")

# --- Definir/editar meta ---------------------------------------------------
categorias = [c["nome"] for c in listar_categorias()]
with st.expander("➕ Definir meta de uma categoria", expanded=not listar_orcamentos()):
    with st.form("nova_meta", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            categoria = st.selectbox("Categoria", categorias)
        with col2:
            limite = st.number_input("Teto mensal (R$)", min_value=0.0, step=100.0, format="%.2f")
        if st.form_submit_button("Salvar meta", type="primary"):
            if limite <= 0:
                st.error("O teto deve ser maior que zero.")
            else:
                definir_orcamento(categoria, float(limite))
                st.success(f"Meta de '{categoria}' definida em R$ {limite:,.2f}.")
                st.rerun()

st.divider()

# --- Acompanhamento do mês -------------------------------------------------
mes_ref = st.text_input("Mês de referência (AAAA-MM)", value=date.today().strftime("%Y-%m"))
status = status_orcamento(mes_ref)

if not status:
    st.info("Nenhuma meta definida ainda. Crie uma acima.")
    st.stop()

st.subheader("Acompanhamento")
for s in status:
    pct = s["percentual"]
    barra = min(pct / 100.0, 1.0)
    cor = "🔴" if s["estourou"] else ("🟡" if pct >= 80 else "🟢")
    st.write(
        f"{cor} **{s['categoria']}** — R\\$ {s['gasto']:,.2f} de R\\$ {s['limite']:,.2f} "
        f"({pct:.0f}%) · resta R\\$ {s['restante']:,.2f}"
    )
    st.progress(barra)

st.divider()

# --- Gerir metas existentes ------------------------------------------------
st.subheader("Metas cadastradas")
orcs = listar_orcamentos()
df = pd.DataFrame(orcs)
df["limite"] = df["limite"].apply(lambda v: f"R$ {v:,.2f}")
df.columns = ["Categoria", "Teto mensal"]
st.dataframe(df, use_container_width=True, hide_index=True)

col_x, col_y = st.columns([3, 1])
with col_x:
    alvo = st.selectbox("Excluir meta de", [o["categoria"] for o in orcs], label_visibility="collapsed")
with col_y:
    if st.button("Excluir meta", type="secondary"):
        excluir_orcamento(alvo)
        st.rerun()
