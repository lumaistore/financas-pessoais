"""Fluxo de caixa projetado — saídas comprometidas nos próximos meses (Fase 12).

Mostra quanto você já tem comprometido a desembolsar mês a mês: parcelas,
financiamentos e tranches de imóveis (evolução de obra). Não inclui gastos
futuros de cartão (que ainda não aconteceram) nem o balão de financiamento
imobiliário a contratar na entrega.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.compromissos import total_financiamento_a_contratar
from services.planejamento import projecao_fluxo

init_db()

st.title("Fluxo de caixa projetado")
st.caption("Suas saídas já comprometidas nos próximos meses — para planejar com antecedência.")

meses = st.slider("Quantos meses projetar", min_value=3, max_value=24, value=12)
proj = projecao_fluxo(meses)

df = pd.DataFrame(proj)
total_periodo = df["compromissos"].sum()

c1, c2 = st.columns(2)
c1.metric("Total comprometido no período", f"R$ {total_periodo:,.2f}")
c2.metric(
    "Média por mês",
    f"R$ {total_periodo / len(df):,.2f}" if len(df) else "R$ 0,00",
)

# Gráfico de barras por mês.
df_chart = df.copy()
df_chart["Mês"] = df_chart["mes"]
df_chart = df_chart.set_index("Mês")[["compromissos"]]
df_chart.columns = ["A pagar (R$)"]
st.bar_chart(df_chart)

# Tabela detalhada.
df_show = df.copy()
df_show["compromissos"] = df_show["compromissos"].apply(lambda v: f"R$ {v:,.2f}")
df_show.columns = ["Mês", "Comprometido"]
st.dataframe(df_show, use_container_width=True, hide_index=True)

financ = total_financiamento_a_contratar()
if financ:
    st.info(
        f"ℹ️ Além disso, há **R\\$ {financ:,.2f}** de financiamento imobiliário a "
        "contratar na entrega das chaves — fora desta projeção mensal."
    )
