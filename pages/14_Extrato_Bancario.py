"""Importar extrato bancário — filtra por mês e vira despesas manuais."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.cartao import listar_categorias
from services.despesas import FORMAS
from services.extrato import (
    filtrar,
    importar,
    ler_extrato,
    marcar_duplicatas,
    meses_disponiveis,
    pdf_pede_senha,
)

init_db()

st.title("Importar extrato bancário")
st.caption(
    "Suba o extrato do banco (PDF/OFX/Excel). O sistema **filtra por mês** — "
    "assim, mesmo que o extrato traga vários meses, você importa só o que quer."
)

arq = st.file_uploader(
    "Extrato bancário",
    type=["pdf", "ofx", "xlsx", "xls", "csv"],
    key="extrato_up",
)

if arq is None:
    st.stop()

# Senha (para PDFs protegidos - Itaú/C6/Nubank frequentemente exigem).
# Mostro SEMPRE o campo pra PDF - se não precisar, deixa em branco.
senha = ""
if arq.name.lower().endswith(".pdf"):
    st.caption(
        "🔐 **PDF com senha?** (comum em Itaú/C6/Nubank) — digite abaixo. "
        "Se o extrato não pedir senha, deixe em branco e clique fora."
    )
    senha = st.text_input(
        "Senha do PDF (opcional)",
        type="password",
        key=f"senha_{arq.name}",
        help="Geralmente CPF ou senha específica do arquivo. Usada só localmente.",
    )

# Lê o arquivo uma vez e guarda em session_state (não relê a cada rerun)
chave_arquivo = f"{arq.name}_{len(arq.getvalue())}_{senha}"
if st.session_state.get("extr_chave") != chave_arquivo:
    with st.spinner("Lendo o extrato..."):
        try:
            extrato = ler_extrato(arq.getvalue(), arq.name, senha=senha)
            erro = None
        except Exception as e:
            erro = str(e) or type(e).__name__
            extrato = None
    st.session_state["extr_chave"] = chave_arquivo
    st.session_state["extr_dados"] = extrato
    st.session_state["extr_erro"] = erro

erro = st.session_state.get("extr_erro")
if erro:
    if "password" in erro.lower() or "encrypt" in erro.lower() or "decrypt" in erro.lower():
        st.error(f"🔐 O PDF pede senha ou a senha está incorreta. Detalhe: {erro}")
    else:
        st.error(f"Não consegui ler o arquivo. Detalhe: {erro}")
    st.stop()

extrato = st.session_state.get("extr_dados")
if extrato is None or not extrato.lancamentos:
    st.error(
        "Não consegui reconhecer este arquivo. Pode ser um PDF de imagem "
        "(escaneado), ou um formato de banco que ainda não temos parser. "
        "Se puder, tente exportar como **.OFX** que é universal."
    )
    st.stop()

st.success(
    f"✅ Banco: **{extrato.banco}** · **{len(extrato.lancamentos)}** lançamentos lidos."
)

# --- Filtro de mês ---------------------------------------------------------
meses = meses_disponiveis(extrato.lancamentos)
if not meses:
    st.warning("Nenhum lançamento com data reconhecida.")
    st.stop()

col_mes, col_deb = st.columns([2, 1])
with col_mes:
    mes_escolhido = st.selectbox(
        "Mês a importar",
        meses,
        index=0,
        help="O extrato pode trazer vários meses. Aqui você escolhe qual importar.",
    )
with col_deb:
    apenas_deb = st.checkbox(
        "Apenas despesas (débitos)",
        value=True,
        help="Se marcado, ignora recebimentos (créditos, transferências recebidas, rendimentos).",
    )

filtrados = filtrar(extrato.lancamentos, mes_escolhido, apenas_debitos=apenas_deb)
if not filtrados:
    st.info(f"Nenhum lançamento em **{mes_escolhido}** com esse filtro.")
    st.stop()

st.write(f"**{len(filtrados)} lançamento(s) em {mes_escolhido}** — total "
         f"R$ {sum(abs(l.valor) for l in filtrados):,.2f}.")

# --- Prepara linhas para revisão -------------------------------------------
if st.session_state.get("extr_mes") != mes_escolhido or "extr_linhas" not in st.session_state:
    st.session_state["extr_linhas"] = marcar_duplicatas(filtrados, mes_escolhido)
    st.session_state["extr_mes"] = mes_escolhido

linhas = st.session_state["extr_linhas"]
n_dup = sum(1 for l in linhas if l["duplicado"])
if n_dup:
    st.info(
        f"ℹ️ {n_dup} lançamento(s) parecem **duplicados** de despesas já "
        "cadastradas neste mês. Foram desmarcados automaticamente — reveja "
        "abaixo e marque se quiser importar mesmo assim."
    )

st.markdown("**Revise antes de importar** — edite categoria, forma, marque LUMAI e desmarque o que não quiser importar:")

categorias = [c["nome"] for c in listar_categorias()]
df = pd.DataFrame(linhas)
edit = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    disabled=["duplicado"],
    column_config={
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
        "forma": st.column_config.SelectboxColumn("Forma", options=FORMAS, required=True),
        "categoria": st.column_config.SelectboxColumn("Categoria", options=categorias, required=True),
        "lumai": st.column_config.CheckboxColumn("LUMAI"),
        "importar": st.column_config.CheckboxColumn("Importar"),
        "duplicado": st.column_config.CheckboxColumn("Dup?", help="Detectado como duplicado."),
    },
    key=f"editor_extr_{mes_escolhido}",
)

marcados = int(edit["importar"].sum())
total_marcado = float(edit[edit["importar"] == True]["valor"].sum())  # noqa: E712

c1, c2 = st.columns([2, 1])
c1.metric("Serão importados", f"{marcados} lançamento(s)", f"R$ {total_marcado:,.2f}")
with c2:
    st.write("")
    st.write("")
    if st.button("📥 Importar despesas selecionadas", type="primary",
                 disabled=marcados == 0):
        with st.spinner("Importando..."):
            n = importar(edit.to_dict("records"))
        st.success(f"{n} despesa(s) importada(s) em {mes_escolhido}!")
        for k in ("extr_chave", "extr_dados", "extr_linhas", "extr_mes"):
            st.session_state.pop(k, None)
        st.rerun()
