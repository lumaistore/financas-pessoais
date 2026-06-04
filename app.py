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

# Diagnóstico de conexão (temporário) — confirma a qual banco o app conectou.
with st.expander("🔧 Diagnóstico de conexão", expanded=True):
    import os

    # 1) Quais segredos o Streamlit enxerga (só os NOMES, nunca os valores).
    try:
        nomes_secrets = list(st.secrets.keys())
    except Exception as exc:
        nomes_secrets = []
        st.write(f"st.secrets indisponível: {exc}")
    st.write(f"**Segredos visíveis (nomes):** {nomes_secrets or 'NENHUM'}")
    st.write(
        f"**DATABASE_URL** — em st.secrets: `{'DATABASE_URL' in nomes_secrets}` · "
        f"em variável de ambiente: `{bool(os.environ.get('DATABASE_URL'))}`"
    )

    # 2) A qual banco o app de fato conectou.
    try:
        from core.db import info_banco, get_session
        from core.models import InvestimentoSnapshot
        from sqlalchemy import func, select

        info = info_banco()
        with get_session() as s:
            n_inv = s.scalar(select(func.count()).select_from(InvestimentoSnapshot)) or 0
        if info["dialeto"].startswith("postgres"):
            st.success(f"✅ Conectado ao Postgres ({info['host']}). Posições de investimento: {n_inv}.")
        else:
            st.warning(
                f"⚠️ Usando banco local ({info['dialeto']}). Se 'DATABASE_URL em st.secrets' "
                "acima estiver `True`, basta **Reboot app**. Se estiver `False`, o segredo "
                "não foi salvo nas configurações DESTE app (Manage app → Settings → Secrets)."
            )
    except Exception as exc:
        st.error(f"Falha ao conectar no banco: {exc}")
