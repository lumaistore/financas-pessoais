"""Tela de Parcelamentos, Financiamentos e Imóveis (Fase 2)."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.compromissos import (
    TIPOS,
    adicionar_compromisso,
    contar_ativos,
    definir_parcelas_pagas,
    excluir_compromisso,
    listar_compromissos,
    proximas_parcelas,
    registrar_pagamento,
    total_financiamento_a_contratar,
    total_saldo_devedor,
)

init_db()

st.title("Financiamentos e Imóveis")
st.caption("Acompanhe saldo devedor, próximas parcelas e datas dos seus compromissos.")

# --- Cadastro -------------------------------------------------------------
with st.expander("➕ Novo compromisso", expanded=not listar_compromissos()):
    with st.form("novo_compromisso", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            nome = st.text_input("Nome", placeholder="Ex.: Carro, Notebook")
            tipo = st.selectbox("Tipo", ["parcelado", "financiamento"])
        with col2:
            valor_parcela = st.number_input("Valor da parcela (R$)", min_value=0.0, step=100.0, format="%.2f")
            total_parcelas = st.number_input("Total de parcelas", min_value=1, step=1, value=40)
        with col3:
            parcelas_pagas = st.number_input("Parcelas já pagas", min_value=0, step=1, value=0)
            usar_data = st.checkbox("Tenho a data da 1ª parcela", value=True)

        if usar_data:
            primeira_data = st.date_input("Data da 1ª parcela", value=date.today(), format="DD/MM/YYYY")
            dia_venc = None
        else:
            primeira_data = None
            dia_venc = st.number_input("Dia do vencimento", min_value=1, max_value=31, value=10)

        enviado = st.form_submit_button("Adicionar compromisso", type="primary")
        if enviado:
            if not nome.strip():
                st.error("Informe o nome do compromisso.")
            elif valor_parcela <= 0:
                st.error("O valor da parcela deve ser maior que zero.")
            elif parcelas_pagas > total_parcelas:
                st.error("Parcelas pagas não podem exceder o total.")
            else:
                adicionar_compromisso(
                    nome=nome.strip(),
                    valor_parcela=float(valor_parcela),
                    total_parcelas=int(total_parcelas),
                    parcelas_pagas=int(parcelas_pagas),
                    tipo=tipo,
                    primeira_data=primeira_data,
                    dia_vencimento=int(dia_venc) if dia_venc else None,
                )
                st.success(f"Compromisso '{nome}' adicionado.")
                st.rerun()

st.divider()

# --- Resumo geral ---------------------------------------------------------
compromissos = listar_compromissos()

col_a, col_b, col_c = st.columns(3)
col_a.metric("Compromissos ativos", contar_ativos())
col_b.metric("Saldo devedor total", f"R$ {total_saldo_devedor():,.2f}")
col_c.metric(
    "Financiamento a contratar",
    f"R$ {total_financiamento_a_contratar():,.2f}",
    help="Soma dos 'balões' de financiamento dos imóveis, contratados na entrega das chaves. Não entra no saldo mensal.",
)

if not compromissos:
    st.info("Nenhum compromisso cadastrado ainda.")
    st.stop()


# --- Renderização de um imóvel -------------------------------------------
def _brl(v: float) -> str:
    """Formata em reais escapando o '$' para o Streamlit não tratar como LaTeX."""
    return f"R\\$ {v:,.2f}"


def render_imovel(c: dict) -> None:
    with st.container(border=True):
        st.subheader(f"🏢 {c['nome']}")
        if c.get("descricao"):
            # Escapa '$' para o texto não virar fórmula matemática (itálico).
            st.caption(c["descricao"].replace("$", "\\$"))
        st.progress(min(c["progresso"], 1.0), text=f"{c['progresso']*100:.0f}% do plano pago")

        # 2 x 2 para os números aparecerem inteiros (sem cortar com "...").
        m1, m2 = st.columns(2)
        m1.metric("Valor total do plano", f"R$ {c['valor_total']:,.2f}")
        m2.metric("Já pago", f"R$ {c['valor_pago']:,.2f}")
        m3, m4 = st.columns(2)
        m3.metric(
            "Saldo a pagar (à vista)",
            f"R$ {c['saldo_devedor']:,.2f}",
            help="Total do plano − financiamento − já pago. É o que falta pagar de parcelas até a entrega.",
        )
        m4.metric(
            "Financiamento (balão)",
            f"R$ {c['financiamento']:,.2f}",
            help="A contratar na entrega das chaves — fora do saldo mensal.",
        )

        # Linhas extras, cada uma na sua linha (mais legível que tudo junto).
        linhas = []
        if c.get("valor_corretagem"):
            linhas.append(f"**Corretagem:** {_brl(c['valor_corretagem'])}")
        if c.get("data_contrato"):
            linhas.append(f"**Contrato:** {c['data_contrato'].strftime('%d/%m/%Y')}")
        if c.get("proxima_data"):
            linhas.append(
                f"**Próxima parcela:** {c['proxima_data'].strftime('%d/%m/%Y')} "
                f"({_brl(c['valor_parcela'])})"
            )
        for ln in linhas:
            st.markdown(f"- {ln}")

        prox = proximas_parcelas(c["id"], n=12)
        if prox:
            df = pd.DataFrame(prox)
            df["data"] = df["data"].apply(lambda d: d.strftime("%d/%m/%Y") if d else "—")
            df["valor"] = df["valor"].apply(lambda v: f"R$ {v:,.2f}")
            df = df[["tipo", "data", "valor"]]
            df.columns = ["Tipo", "Vencimento", "Valor"]
            with st.expander("Próximas parcelas"):
                st.dataframe(df, use_container_width=True, hide_index=True)

        if st.button("Excluir", key=f"del_{c['id']}", type="secondary"):
            excluir_compromisso(c["id"])
            st.rerun()


# --- Renderização de um compromisso uniforme ------------------------------
def render_uniforme(c: dict) -> None:
    status = "✅ Quitado" if not c["ativo"] else f"{c['parcelas_pagas']}/{c['total_parcelas']} pagas"
    with st.container(border=True):
        st.subheader(f"{c['nome']}  ·  {status}")
        st.progress(c["progresso"], text=f"{c['progresso']*100:.0f}% pago")

        m1, m2 = st.columns(2)
        m1.metric("Valor da parcela", f"R$ {c['valor_parcela']:,.2f}")
        m2.metric("Saldo devedor", f"R$ {c['saldo_devedor']:,.2f}")
        m3, m4 = st.columns(2)
        m3.metric("Pago / Total", f"R$ {c['valor_pago']:,.0f} / {c['valor_total']:,.0f}")
        if c["proxima_data"]:
            m4.metric(
                f"Próxima (parcela {c['proxima_parcela_numero']})",
                c["proxima_data"].strftime("%d/%m/%Y"),
            )
        else:
            m4.metric("Próxima parcela", "—")

        if c["ativo"]:
            prox = proximas_parcelas(c["id"], n=6)
            if prox:
                df = pd.DataFrame(prox)
                df["data"] = df["data"].apply(lambda d: d.strftime("%d/%m/%Y") if d else "—")
                df["valor"] = df["valor"].apply(lambda v: f"R$ {v:,.2f}")
                df = df[["numero", "data", "valor"]]
                df.columns = ["Parcela nº", "Vencimento", "Valor"]
                with st.expander("Próximas parcelas"):
                    st.dataframe(df, use_container_width=True, hide_index=True)

        a1, a2, a3 = st.columns([1, 2, 1])
        with a1:
            if c["ativo"] and st.button("Registrar pagamento", key=f"pg_{c['id']}"):
                registrar_pagamento(c["id"])
                st.rerun()
        with a2:
            nova = st.number_input(
                "Ajustar parcelas pagas",
                min_value=0,
                max_value=c["total_parcelas"],
                value=c["parcelas_pagas"],
                key=f"adj_{c['id']}",
            )
            if nova != c["parcelas_pagas"]:
                definir_parcelas_pagas(c["id"], int(nova))
                st.rerun()
        with a3:
            if st.button("Excluir", key=f"del_{c['id']}", type="secondary"):
                excluir_compromisso(c["id"])
                st.rerun()


# --- Detalhe de cada compromisso -----------------------------------------
for c in compromissos:
    if c.get("eh_imovel"):
        render_imovel(c)
    else:
        render_uniforme(c)
