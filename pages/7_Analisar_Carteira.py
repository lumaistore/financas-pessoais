"""Analisar minha carteira — análise educativa via IA (Fase 6).

Envia APENAS números agregados (totais, percentuais, classes) para a API da
Anthropic e devolve uma leitura educativa. A chave é lida da variável de
ambiente ANTHROPIC_API_KEY (arquivo .env local) — nunca fica no código.
"""
from datetime import date

import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo, cabecalho_pagina
from services.analise_ia import (
    DISCLAIMER,
    NOME_VARIAVEL,
    IAIndisponivelError,
    analisar_carteira,
    chave_configurada,
    contexto_para_texto,
    montar_contexto,
)

init_db()
aplicar_estilo()

cabecalho_pagina("Analisar minha carteira", icone="🔍")
st.caption(
    "Uma leitura educativa das suas finanças feita por IA. Só números agregados "
    "saem da máquina — nada de senhas, CPF, números de conta ou de contrato."
)

mes_ref = st.text_input("Mês de referência (AAAA-MM)", value=date.today().strftime("%Y-%m"))

# --- Estado da chave ------------------------------------------------------
if not chave_configurada():
    st.warning(
        f"**Chave da API não configurada.** Para usar esta aba, crie um arquivo "
        f"`.env` na pasta do projeto (ao lado de `app.py`) com a linha abaixo e "
        f"reinicie o app:\n\n```\n{NOME_VARIAVEL}=sua-chave-aqui\n```\n\n"
        "Você pegou essa chave no console da Anthropic. Ela fica só na sua "
        "máquina e nunca é versionada (o `.env` está no `.gitignore`)."
    )

# --- Prévia do que será enviado ------------------------------------------
with st.expander("👀 Ver exatamente o que será enviado para a IA"):
    try:
        ctx = montar_contexto(mes_ref)
        st.code(contexto_para_texto(ctx), language="markdown")
    except Exception as exc:  # não deve quebrar a tela
        st.error(f"Não consegui montar o panorama: {exc}")

pergunta_extra = st.text_area(
    "Quer focar em algo específico? (opcional)",
    placeholder="Ex.: Estou muito concentrado em renda variável? Como está minha reserva?",
    height=80,
)

# --- Disparo --------------------------------------------------------------
if st.button("Analisar minha carteira", type="primary", disabled=not chave_configurada()):
    with st.spinner("Conversando com a IA..."):
        try:
            resultado = analisar_carteira(mes_ref, pergunta_extra)
            st.session_state["analise_resultado"] = resultado
        except IAIndisponivelError as exc:
            st.session_state.pop("analise_resultado", None)
            st.error(str(exc))

# --- Resultado ------------------------------------------------------------
if st.session_state.get("analise_resultado"):
    st.divider()
    st.markdown(st.session_state["analise_resultado"])
    st.divider()
    st.info(DISCLAIMER)
