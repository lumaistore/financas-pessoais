"""Finanças Pessoais — app local (Streamlit).

Ponto de entrada. As demais telas ficam em pages/ e o Streamlit as exibe
automaticamente na barra lateral.
"""
import streamlit as st

from core.db import init_db
from core.ui import COR, aplicar_estilo
from core.auth import exigir_senha

st.set_page_config(page_title="Finanças Pessoais", page_icon="💰", layout="wide")

# Garante o banco e as tabelas na primeira execução.
init_db()
aplicar_estilo()
exigir_senha()

st.markdown(
    f"""
    <div style="display:flex;align-items:center;gap:14px;margin-bottom:6px">
      <div style="width:46px;height:46px;border-radius:13px;background:{COR['primaria_bg']};
                  display:flex;align-items:center;justify-content:center;font-size:24px">💰</div>
      <div>
        <div style="font-size:28px;font-weight:600;letter-spacing:-0.03em;color:{COR['texto']};
                    line-height:1.1">Finanças Pessoais</div>
        <div style="color:{COR['texto_2']};font-size:14px;margin-top:2px">
          Sistema privado, rodando na sua nuvem. Nenhum dado sai daqui.</div>
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)

st.write("")

# --- Cards de navegação por seção ---
SECOES = [
    ("📊", "Painel Mensal", "Visão consolidada: fluxo, patrimônio, alertas."),
    ("🏦", "Contas", "Itaú, C6, BTG — para detectar transferências."),
    ("💰", "Movimentações", "Todas as entradas e saídas do mês, unificadas."),
    ("🧾", "Faturas de Cartão", "Importe o PDF, revise categorias, marque LUMAI."),
    ("🏠", "Financiamentos", "Parcelamentos, financiamentos e imóveis."),
    ("📈", "Investimentos", "Carteira, rendimento e cotações ao vivo."),
    ("👔", "Assessor / Carteira", "Análises e recomendações por IA."),
    ("🧮", "Retirada de Lucros", "Recibos de distribuição LUMAI."),
    ("🩺", "Despesas Médicas / Exames", "Controles de saúde para o IR."),
    ("🏦", "Extrato Bancário", "Importe PDF/OFX e classifique automático."),
]

cols = st.columns(2)
for i, (ico, titulo, desc) in enumerate(SECOES):
    with cols[i % 2]:
        st.markdown(
            f"""
            <div style="background:{COR['superficie']};border:0.5px solid {COR['borda']};
                        border-radius:14px;padding:16px 18px;margin-bottom:12px;
                        display:flex;align-items:flex-start;gap:12px">
              <div style="font-size:22px;line-height:1">{ico}</div>
              <div>
                <div style="font-weight:600;font-size:15px;color:{COR['texto']}">{titulo}</div>
                <div style="color:{COR['texto_2']};font-size:13px;margin-top:2px">{desc}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

st.write("")
st.markdown(
    f"""
    <div style="background:{COR['primaria_bg']};border-radius:12px;padding:14px 16px;
                display:flex;align-items:center;gap:10px">
      <span style="font-size:18px">🔒</span>
      <span style="color:{COR['texto']};font-size:13.5px">
        <b>Privacidade:</b> seus dados ficam só no seu banco. O sistema nunca
        pede nem armazena senhas de bancos ou corretoras.</span>
    </div>
    """,
    unsafe_allow_html=True,
)
