"""Finanças Pessoais — app local (Streamlit).

Ponto de entrada. As demais telas ficam em pages/ e o Streamlit as exibe
automaticamente na barra lateral.
"""
import streamlit as st

from core.db import init_db

st.set_page_config(page_title="Finanças Pessoais", page_icon="💰", layout="wide")

# Garante o banco e as tabelas na primeira execução.
init_db()

st.title("💰 Finanças Pessoais")
st.caption("Sistema privado, rodando 100% na sua máquina. Nenhum dado sai daqui.")

st.markdown(
    """
    Use o menu lateral (☰ no celular) para navegar pelas seções:

    - **Painel Mensal** — visão consolidada: fluxo, patrimônio, reserva e orçamento.
    - **Receitas** — entradas do mês.
    - **Faturas de Cartão** — importe o PDF, revise categorias e marque despesas LUMAI.
    - **Despesas** — PIX, boleto, Caju e outros gastos fora do cartão.
    - **Financiamentos** — parcelamentos, financiamentos e imóveis.
    - **Investimentos** — carteira por snapshot e rendimento.
    - **Orçamento** — metas de gasto por categoria.
    - **Fluxo de Caixa** — projeção das saídas comprometidas.
    - **Analisar Carteira** — leitura educativa por IA.
    """
)

st.info(
    "Privacidade: seus dados ficam só no seu banco (local ou na sua nuvem "
    "privada). O sistema nunca pede nem armazena senhas de bancos ou corretoras."
)

