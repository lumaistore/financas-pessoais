"""Assessor de Investimentos — conversa com o Ricardo (IA) e sua equipe."""
from datetime import datetime

import streamlit as st

from core.db import init_db
from services.assessor import (
    DISCLAIMER,
    carregar_consulta,
    conversar,
    criar_consulta,
    excluir_consulta,
    listar_consultas,
    montar_contexto_carteira,
    salvar_conversa,
)

init_db()

st.title("👔 Assessor de Investimentos")
st.caption(
    "Converse com o **Ricardo** — assessor sênior com equipe multi-mercado "
    "(BR, EUA, China, Europa). Foco em longo prazo."
)
st.info(DISCLAIMER)

# ---------------------------------------------------------------------------
# Seletor de sessão: nova consulta ou retomar uma
# ---------------------------------------------------------------------------
consultas = listar_consultas()

col_sel, col_new = st.columns([3, 1])
with col_sel:
    opcoes = ["➕ Nova consulta"] + [
        f"#{c['id']} · {c['titulo']} · {c['criada_em'].strftime('%d/%m/%Y %H:%M')}"
        for c in consultas
    ]
    escolha = st.selectbox("Sessão", opcoes, key="sel_consulta")
with col_new:
    st.write("")
    st.write("")
    if escolha != "➕ Nova consulta" and st.button("🗑️ Excluir sessão"):
        cid_del = int(escolha.split("·")[0].strip().lstrip("#"))
        excluir_consulta(cid_del)
        st.rerun()

# ---------------------------------------------------------------------------
# Nova consulta
# ---------------------------------------------------------------------------
if escolha == "➕ Nova consulta":
    st.subheader("Nova consulta ao assessor")

    contexto = montar_contexto_carteira()
    with st.expander("📊 Contexto que o Ricardo vai receber (sua carteira atual)"):
        st.markdown(contexto)

    valor = st.number_input(
        "Quanto você quer investir agora? (R$)",
        min_value=0.0,
        step=500.0,
        format="%.2f",
        help="Aporte deste mês. Pode ficar em 0 se quiser só uma revisão da carteira.",
    )
    titulo = st.text_input(
        "Título da consulta (opcional)",
        placeholder="Ex.: Aporte de outubro/2026",
    )
    pergunta_inicial = st.text_area(
        "O que você quer discutir com o Ricardo?",
        value=(
            "Fiz um aporte novo este mês. Considerando minha carteira e o "
            "cenário macro global, para onde faz sentido alocar pensando "
            "em longo prazo (5-10 anos)?"
        ) if valor else (
            "Faça uma leitura da minha carteira: pontos fortes, concentrações "
            "e o que ajustar pensando em longo prazo."
        ),
        height=110,
    )

    if st.button("🎙️ Consultar o Ricardo", type="primary"):
        if not pergunta_inicial.strip():
            st.error("Escreva sua pergunta.")
        else:
            with st.spinner("Ricardo consultando a equipe e preparando a resposta..."):
                try:
                    cid = criar_consulta(
                        valor if valor > 0 else None,
                        contexto,
                        titulo or f"Aporte {datetime.now().strftime('%m/%Y')}",
                    )
                    resposta = conversar(
                        valor if valor > 0 else None,
                        contexto,
                        conversa=[],
                        nova_mensagem=pergunta_inicial.strip(),
                    )
                    salvar_conversa(cid, [
                        {"role": "user", "content": pergunta_inicial.strip()},
                        {"role": "assistant", "content": resposta},
                    ])
                    st.session_state["consulta_ativa"] = cid
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao consultar o assessor: {e}")

    # Se acabou de criar uma consulta, redireciona
    if "consulta_ativa" in st.session_state:
        cid = st.session_state.pop("consulta_ativa")
        # A próxima renderização já vai listar essa consulta.
        st.rerun()

else:
    # -----------------------------------------------------------------------
    # Sessão existente: exibe conversa e permite continuar
    # -----------------------------------------------------------------------
    cid = int(escolha.split("·")[0].strip().lstrip("#"))
    dados = carregar_consulta(cid)
    if not dados:
        st.error("Consulta não encontrada.")
        st.stop()

    st.subheader(dados["titulo"])
    if dados["valor_investir"]:
        st.caption(f"💰 Aporte desta consulta: R$ {dados['valor_investir']:,.2f}")
    with st.expander("📊 Carteira usada como contexto"):
        st.markdown(dados["contexto_carteira"] or "_(sem contexto)_")

    st.divider()

    # Exibe a conversa
    for msg in dados["conversa"]:
        with st.chat_message("user" if msg["role"] == "user" else "assistant",
                             avatar="🧑" if msg["role"] == "user" else "👔"):
            st.markdown(msg["content"])

    # Input para continuar
    nova = st.chat_input("Continue a conversa com o Ricardo — questione, peça detalhes, ajuste…")
    if nova:
        # Adiciona pergunta e chama modelo
        with st.chat_message("user", avatar="🧑"):
            st.markdown(nova)
        with st.chat_message("assistant", avatar="👔"):
            with st.spinner("Ricardo pensando..."):
                try:
                    resposta = conversar(
                        dados["valor_investir"],
                        dados["contexto_carteira"] or "",
                        conversa=dados["conversa"],
                        nova_mensagem=nova,
                    )
                    st.markdown(resposta)
                    nova_conversa = dados["conversa"] + [
                        {"role": "user", "content": nova},
                        {"role": "assistant", "content": resposta},
                    ]
                    salvar_conversa(cid, nova_conversa)
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha: {e}")

    st.divider()
    st.caption(DISCLAIMER)
