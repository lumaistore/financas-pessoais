"""Cadastro de contas financeiras — usado para detectar transferências
entre próprias contas e aplicações a partir de extratos."""
import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo, cabecalho_pagina
from core.auth import exigir_senha
from services.contas import (
    TIPOS_CONTA,
    adicionar_conta,
    aplicar_pix_conhecidos,
    atualizar_conta,
    excluir_conta,
    listar_contas,
    semear_contas_padrao,
)

init_db()
aplicar_estilo()
exigir_senha()

cabecalho_pagina("Contas financeiras", icone="🏦")
st.caption(
    "Cadastre suas contas bancárias e de aplicação. O sistema usa isso pra "
    "**identificar transferências entre você mesmo** (Itaú ↔ C6) e "
    "**aplicações** (PIX pro BTG) — assim o painel não conta duas vezes."
)

st.info(
    "**Como funciona:** ao importar um extrato, se um lançamento tem no "
    "texto o nome/apelido de uma conta cadastrada, o sistema classifica "
    "automaticamente como *transferência* (não conta) ou *aplicação* "
    "(vai pra investimentos)."
)

# --- Semear padrões na primeira vez ---------------------------------------
contas = listar_contas(apenas_ativas=False)
if not contas:
    with st.expander("💡 Começar rápido: cadastrar contas padrão", expanded=True):
        st.write("Cria Itaú, C6 (correntes) e BTG (aplicação) com base no seu perfil.")
        if st.button("Cadastrar contas padrão"):
            n = semear_contas_padrao()
            st.success(f"{n} conta(s) cadastrada(s). Ajuste os identificadores abaixo se precisar.")
            st.rerun()

# --- Chaves PIX (para detecção de transferências) -------------------------
if contas:
    with st.expander("🔑 Chaves PIX das suas contas (melhora a detecção de transferências)"):
        st.caption(
            "Cole a chave PIX de cada conta. Quando um lançamento do extrato tiver "
            "essa chave no texto, o sistema reconhece que foi transferência pra essa "
            "conta (não conta como gasto). As chaves ficam **só no seu banco de dados**."
        )
        with st.form("pix_form"):
            pc1, pc2, pc3 = st.columns(3)
            with pc1:
                pix_c6 = st.text_input("PIX C6", placeholder="telefone/CPF/e-mail/chave")
            with pc2:
                pix_itau = st.text_input("PIX Itaú", placeholder="telefone/CPF/e-mail/chave")
            with pc3:
                pix_btg = st.text_input("PIX BTG", placeholder="telefone/CPF/e-mail/chave")
            if st.form_submit_button("Aplicar chaves PIX", type="primary"):
                mapa = {"C6": pix_c6, "Itaú": pix_itau, "BTG": pix_btg}
                mapa = {k: v for k, v in mapa.items() if v.strip()}
                if not mapa:
                    st.warning("Preencha ao menos uma chave.")
                else:
                    n = aplicar_pix_conhecidos(mapa)
                    st.success(f"{n} chave(s) adicionada(s) aos identificadores das contas.")
                    st.rerun()

# --- Nova conta ------------------------------------------------------------
with st.expander("➕ Adicionar conta", expanded=not contas):
    with st.form("nova_conta", clear_on_submit=True):
        c1, c2 = st.columns(2)
        with c1:
            apelido = st.text_input("Apelido", placeholder="Ex.: Itaú CC, BTG Aplicação")
            banco = st.text_input("Banco", placeholder="Ex.: Itaú, C6, BTG")
        with c2:
            tipo = st.selectbox("Tipo", TIPOS_CONTA,
                                help="'aplicação' faz o PIX ir para investimentos, não como despesa.")
            identificadores = st.text_input(
                "Identificadores (separados por vírgula)",
                placeholder="Ex.: LUCAS GUEIROS, BTG PACTUAL, LGF",
                help="Palavras que aparecem no extrato para identificar essa conta.",
            )
        if st.form_submit_button("Cadastrar", type="primary"):
            if not apelido.strip():
                st.error("Informe um apelido.")
            else:
                adicionar_conta(apelido, banco, tipo, identificadores)
                st.success(f"'{apelido}' cadastrada.")
                st.rerun()

# --- Lista + edição --------------------------------------------------------
if not contas:
    st.stop()

st.subheader("Suas contas")
for c in contas:
    with st.container(border=True):
        col1, col2 = st.columns([3, 1])
        with col1:
            st.markdown(f"**{c['apelido']}** — {c['banco'] or '(sem banco)'} · _{c['tipo']}_"
                        + (" · ⏸️ inativa" if not c["ativa"] else ""))
            ids = c["identificadores"] or "(nenhum)"
            st.caption(f"Identificadores: {ids}")
        with col2:
            if st.button("✏️ Editar", key=f"ed_{c['id']}"):
                st.session_state[f"editing_{c['id']}"] = True

        if st.session_state.get(f"editing_{c['id']}"):
            with st.form(f"form_ed_{c['id']}"):
                a1, a2 = st.columns(2)
                with a1:
                    ap = st.text_input("Apelido", value=c["apelido"])
                    bk = st.text_input("Banco", value=c["banco"] or "")
                with a2:
                    tp = st.selectbox("Tipo", TIPOS_CONTA,
                                       index=TIPOS_CONTA.index(c["tipo"]) if c["tipo"] in TIPOS_CONTA else 0)
                    ids2 = st.text_input("Identificadores", value=c["identificadores"] or "")
                ativa = st.checkbox("Ativa", value=c["ativa"])
                cs, cd = st.columns(2)
                with cs:
                    if st.form_submit_button("💾 Salvar", type="primary"):
                        atualizar_conta(c["id"], ap, bk, tp, ids2, ativa)
                        st.session_state.pop(f"editing_{c['id']}", None)
                        st.rerun()
                with cd:
                    if st.form_submit_button("🗑️ Excluir"):
                        excluir_conta(c["id"])
                        st.rerun()
