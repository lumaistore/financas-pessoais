"""Importar extrato bancário — filtra por mês e vira despesas manuais."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo, cabecalho_pagina
from services.cartao import listar_categorias
from services.contas import listar_contas
from services.movimentacoes import FORMAS, TIPOS
from services.extrato import (
    filtrar,
    importar,
    ler_extrato,
    marcar_duplicatas,
    meses_disponiveis,
    pdf_pede_senha,
)

init_db()
aplicar_estilo()

cabecalho_pagina("Importar extrato bancário", icone="🏦")
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

# --- Conta de origem (importante pra detecção de transferências) ----------
contas = listar_contas()
if not contas:
    st.warning(
        "⚠️ Você não tem contas cadastradas. Vá em **🏦 Contas** para cadastrar "
        "suas contas (Itaú, C6, BTG…) — isso permite ao sistema identificar "
        "transferências entre suas contas e aplicações automaticamente."
    )
opcoes_conta = {c["apelido"]: c["id"] for c in contas}
apelido_conta = st.selectbox(
    "De qual conta é este extrato?",
    ["(selecionar)"] + list(opcoes_conta.keys()),
    help="Identifica a conta origem para o sistema não classificar como transferência pra ela mesma.",
)
conta_origem_id = opcoes_conta.get(apelido_conta) if apelido_conta != "(selecionar)" else None

# --- Filtro de mês ---------------------------------------------------------
meses = meses_disponiveis(extrato.lancamentos)
if not meses:
    st.warning("Nenhum lançamento com data reconhecida.")
    st.stop()

col_mes, col_tipo = st.columns([2, 2])
with col_mes:
    mes_escolhido = st.selectbox(
        "Mês a importar",
        meses,
        index=0,
        help="O extrato pode trazer vários meses. Aqui você escolhe qual importar.",
    )
with col_tipo:
    incluir_receitas = st.checkbox(
        "Incluir entradas (receitas / resgates)",
        value=True,
        help="Se marcado, receitas e resgates também são classificados e importados.",
    )

filtrados = filtrar(extrato.lancamentos, mes_escolhido,
                    apenas_debitos=not incluir_receitas)
if not filtrados:
    st.info(f"Nenhum lançamento em **{mes_escolhido}** com esse filtro.")
    st.stop()

st.write(f"**{len(filtrados)} lançamento(s) em {mes_escolhido}** — total "
         f"R$ {sum(abs(l.valor) for l in filtrados):,.2f}.")

# --- Prepara linhas para revisão -------------------------------------------
chave_ses = f"{mes_escolhido}_{conta_origem_id}"
if st.session_state.get("extr_mes") != chave_ses or "extr_linhas" not in st.session_state:
    st.session_state["extr_linhas"] = marcar_duplicatas(
        filtrados, mes_escolhido, conta_origem_id=conta_origem_id
    )
    st.session_state["extr_mes"] = chave_ses

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

# Alerta sobre auto-classificação
n_transf = sum(1 for l in linhas if l["tipo"] == "transferencia")
n_apli = sum(1 for l in linhas if l["tipo"] == "aplicacao")
if n_transf or n_apli:
    partes = []
    if n_transf:
        partes.append(f"{n_transf} **transferência(s) interna(s)** (não vão ser importadas)")
    if n_apli:
        partes.append(f"{n_apli} **aplicação(ões)** (vão para Investimentos, não como despesa)")
    st.info("🔍 Detectei: " + " · ".join(partes))

df = pd.DataFrame(linhas)
edit = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    disabled=["duplicado", "conta_destino_id"],
    column_config={
        "conta_destino_id": None,
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
        "tipo": st.column_config.SelectboxColumn("Tipo", options=TIPOS, required=True,
                                                  help="Classificação automática. Ajuste se necessário."),
        "forma": st.column_config.SelectboxColumn("Forma", options=FORMAS, required=True),
        "categoria": st.column_config.SelectboxColumn("Categoria", options=categorias, required=True),
        "lumai": st.column_config.CheckboxColumn("LUMAI"),
        "importar": st.column_config.CheckboxColumn("Importar"),
        "duplicado": st.column_config.CheckboxColumn("Dup?", help="Já cadastrado."),
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
    _falta_conta = bool(contas) and conta_origem_id is None
    if _falta_conta:
        st.info("👆 Selecione a **conta de origem** no topo para vincular estas "
                "movimentações à conta (preenche a 'Movimentação por conta' no Painel).")
    if st.button("📥 Importar como movimentações", type="primary",
                 disabled=marcados == 0 or _falta_conta):
        with st.spinner("Importando..."):
            origem = f"extrato:{extrato.banco}:{mes_escolhido}"
            n = importar(edit.to_dict("records"),
                          conta_origem_id=conta_origem_id,
                          origem_texto=origem)
        st.success(f"{n} movimentação(ões) importada(s) em {mes_escolhido}!")
        for k in ("extr_chave", "extr_dados", "extr_linhas", "extr_mes"):
            st.session_state.pop(k, None)
        st.rerun()
