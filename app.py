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

    - **Painel Mensal** — visão consolidada: fluxo, patrimônio, compromissos.
    - **🏦 Contas** — suas contas (Itaú, C6, BTG) para detectar transferências.
    - **💰 Movimentações** — todas entradas e saídas do mês, unificadas.
    - **Faturas de Cartão** — importe o PDF, revise categorias e marque LUMAI.
    - **Financiamentos** — parcelamentos, financiamentos e imóveis.
    - **Investimentos** — carteira por snapshot, rendimento e cotações ao vivo.
    - **Analisar Carteira** / **Assessor Investimentos** — análises por IA.
    - **Retirada de Lucros**, **Despesas Médicas**, **Exames** — controles específicos.
    - **Extrato Bancario** — importe PDF/OFX e classifique automático.
    """
)

st.info(
    "Privacidade: seus dados ficam só no seu banco (local ou na sua nuvem "
    "privada). O sistema nunca pede nem armazena senhas de bancos ou corretoras."
)

