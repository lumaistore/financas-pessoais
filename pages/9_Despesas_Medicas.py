"""Despesas Médicas — controle anual para Imposto de Renda."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo, cabecalho_pagina
from core.auth import exigir_senha
from services.despesas_medicas import (
    TIPOS,
    adicionar,
    anexar_comprovante,
    atualizar,
    comprovante,
    excluir,
    gerar_excel_ir,
    listar,
    pendentes_cnpj,
    por_paciente,
    por_tipo,
    total_dedutivel,
    total_pago,
    total_reembolsado,
)
from services.leitor_nf import ler_nf
from services.perfil import get_perfil, lista_pacientes, paciente_padrao, salvar_perfil

init_db()
aplicar_estilo()
exigir_senha()

cabecalho_pagina("Despesas Médicas", icone="🩺")
st.caption(
    "Junte os comprovantes de saúde do ano para o Imposto de Renda. "
    "O sistema soma só o **valor dedutível** (pago − reembolsado pelo plano)."
)
st.info(
    "ℹ️ A Receita exige **CPF/CNPJ do prestador** e **nome do paciente**. "
    "**Medicamentos comprados em farmácia NÃO são dedutíveis** — só remédios "
    "incluídos em conta de internação hospitalar."
)

# ---------------------------------------------------------------------------
# Perfil (paciente padrão e dependentes)
# ---------------------------------------------------------------------------
perfil = get_perfil()
with st.expander("👤 Meus dados (paciente padrão e dependentes)",
                 expanded=not perfil["nome"]):
    st.caption(
        "Cadastre seu nome para o sistema preencher o paciente automaticamente "
        "em toda despesa. Dependentes (separados por vírgula) aparecem como "
        "sugestão no campo paciente."
    )
    pn = st.text_input("Seu nome", value=perfil["nome"], placeholder="Ex.: Lucas Gueiros…")
    pc = st.text_input("CPF (opcional)", value=perfil["cpf"], placeholder="000.000.000-00")
    pd_ = st.text_input("Dependentes (separados por vírgula)", value=perfil["dependentes"],
                        placeholder="Ex.: Esposa, Filho João")
    if st.button("Salvar meus dados"):
        salvar_perfil(pn, pc, pd_)
        st.success("Salvo.")
        st.rerun()

# ---------------------------------------------------------------------------
# Filtro por ano
# ---------------------------------------------------------------------------
ano = int(st.number_input("Ano-base", min_value=2020, max_value=2100, value=date.today().year, step=1))

# ---------------------------------------------------------------------------
# Nova despesa — sobe a NF e o sistema lê os campos automaticamente
# ---------------------------------------------------------------------------
st.subheader("➕ Adicionar despesa médica")
st.caption(
    "Suba a nota fiscal/recibo (PDF ou foto). O sistema lê data, valor, "
    "prestador e CNPJ sozinho — você só confere e ajusta o que faltar."
)

arq = st.file_uploader(
    "Nota fiscal / recibo (PDF ou imagem)",
    type=["pdf", "png", "jpg", "jpeg", "webp"],
    key="nf_upload",
)

# Quando muda o arquivo, lê e guarda em session_state.
if arq is not None:
    if st.session_state.get("nf_nome_atual") != arq.name:
        with st.spinner("Lendo a nota fiscal..."):
            st.session_state["nf_lido"] = ler_nf(arq.getvalue(), arq.name)
            st.session_state["nf_bytes"] = arq.getvalue()
            st.session_state["nf_nome_atual"] = arq.name
    lido = st.session_state.get("nf_lido", {})
    achados = [
        f"📅 {lido['data'].strftime('%d/%m/%Y')}" if lido.get("data") else None,
        f"💰 R$ {lido['valor_pago']:,.2f}" if lido.get("valor_pago") else None,
        f"🏥 {lido['prestador']}" if lido.get("prestador") else None,
        f"📄 {lido['cnpj_cpf']}" if lido.get("cnpj_cpf") else None,
    ]
    achados = [a for a in achados if a]
    if achados:
        st.success("Li do documento: " + " · ".join(achados))
    else:
        st.info("Não consegui ler automaticamente — preencha os campos abaixo.")

lido = st.session_state.get("nf_lido") or {}

with st.form("nova_med", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        data_ = st.date_input("Data", value=lido.get("data") or date.today(), format="DD/MM/YYYY")
        tipo_default = lido.get("tipo") if lido.get("tipo") in TIPOS else "Outros"
        tipo = st.selectbox("Tipo", TIPOS, index=TIPOS.index(tipo_default))
    with c2:
        paciente = st.text_input(
            "Paciente",
            value=lido.get("paciente") or (paciente_padrao() or ""),
            placeholder="Você mesmo ou nome do dependente",
            help="Você pode trocar pelo nome de um dependente. Configure os seus dados em 'Meus dados' acima.",
        )
        prestador = st.text_input("Prestador", value=lido.get("prestador") or "",
                                  placeholder="Médico / clínica / hospital / plano")
    with c3:
        cnpj_cpf = st.text_input("CNPJ/CPF do prestador", value=lido.get("cnpj_cpf") or "",
                                 placeholder="exigido pela Receita")
        valor_pago = st.number_input("Valor pago (R$)", min_value=0.0, step=50.0, format="%.2f",
                                     value=float(lido.get("valor_pago") or 0.0))
    c4, c5 = st.columns([1, 2])
    with c4:
        valor_reemb = st.number_input("Reembolsado pelo plano (R$)", min_value=0.0, step=50.0, format="%.2f")
    with c5:
        obs = st.text_input("Observação (opcional)")

    if st.form_submit_button("Adicionar despesa", type="primary"):
        if not paciente.strip() or not prestador.strip():
            st.error("Informe o paciente e o prestador.")
        elif valor_pago <= 0:
            st.error("Informe o valor pago.")
        else:
            adicionar(
                data_, tipo, paciente, prestador, cnpj_cpf,
                float(valor_pago), float(valor_reemb), obs,
                st.session_state.get("nf_nome_atual") if arq else None,
                st.session_state.get("nf_bytes") if arq else None,
            )
            # Limpa o cache do upload para a próxima despesa.
            for k in ("nf_lido", "nf_bytes", "nf_nome_atual"):
                st.session_state.pop(k, None)
            st.success("Despesa registrada.")
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Resumo do ano
# ---------------------------------------------------------------------------
st.subheader(f"Resumo do ano {ano}")
m1, m2, m3 = st.columns(3)
m1.metric("Total pago", f"R$ {total_pago(ano):,.2f}")
m2.metric("Reembolsado pelo plano", f"R$ {total_reembolsado(ano):,.2f}")
m3.metric(
    "💰 Total dedutível no IR",
    f"R$ {total_dedutivel(ano):,.2f}",
    help="Soma do (pago − reembolsado) de cada despesa. É o que entra na declaração.",
)

# Aviso de pendências (sem CNPJ)
pendentes = pendentes_cnpj(ano)
if pendentes:
    st.warning(
        f"⚠️ **{len(pendentes)}** despesa(s) sem CPF/CNPJ do prestador — "
        "a Receita exige preencher antes da declaração."
    )

# Por tipo / paciente
col_t, col_p = st.columns(2)
with col_t:
    st.markdown("**Por tipo**")
    df_t = pd.DataFrame(por_tipo(ano))
    if not df_t.empty:
        df_t["pago"] = df_t["pago"].apply(lambda v: f"R$ {v:,.2f}")
        df_t["dedutivel"] = df_t["dedutivel"].apply(lambda v: f"R$ {v:,.2f}")
        df_t.columns = ["Tipo", "Qtd", "Pago", "Dedutível"]
        st.dataframe(df_t, use_container_width=True, hide_index=True)
    else:
        st.caption("Sem despesas neste ano.")
with col_p:
    st.markdown("**Por paciente**")
    df_p = pd.DataFrame(por_paciente(ano))
    if not df_p.empty:
        df_p["dedutivel"] = df_p["dedutivel"].apply(lambda v: f"R$ {v:,.2f}")
        df_p.columns = ["Paciente", "Qtd", "Dedutível"]
        st.dataframe(df_p, use_container_width=True, hide_index=True)
    else:
        st.caption("Sem despesas neste ano.")

st.divider()

# ---------------------------------------------------------------------------
# Lista do ano
# ---------------------------------------------------------------------------
st.subheader(f"Despesas em {ano}")
despesas = listar(ano)
if not despesas:
    st.info("Nenhuma despesa neste ano.")
else:
    df = pd.DataFrame(despesas)
    df_view = df[["data", "tipo", "paciente", "prestador", "cnpj_cpf",
                  "valor_pago", "valor_reembolsado", "dedutivel", "tem_comprovante"]].copy()
    df_view["data"] = df_view["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
    for c in ("valor_pago", "valor_reembolsado", "dedutivel"):
        df_view[c] = df_view[c].apply(lambda v: f"R$ {v:,.2f}")
    df_view["tem_comprovante"] = df_view["tem_comprovante"].map({True: "📎", False: "—"})
    df_view["cnpj_cpf"] = df_view["cnpj_cpf"].fillna("⚠️ falta")
    df_view.columns = ["Data", "Tipo", "Paciente", "Prestador", "CNPJ/CPF",
                       "Pago", "Reembolso", "Dedutível", "Anexo"]
    st.dataframe(df_view, use_container_width=True, hide_index=True)

    # Relatório anual para o IR
    if st.button("📊 Gerar planilha do ano para o IR (.xlsx)"):
        st.session_state["med_xlsx"] = gerar_excel_ir(ano)
    if st.session_state.get("med_xlsx"):
        st.download_button(
            f"📥 Baixar planilha {ano}",
            data=st.session_state["med_xlsx"],
            file_name=f"despesas_medicas_{ano}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )

st.divider()

# ---------------------------------------------------------------------------
# Editar / baixar / excluir uma despesa
# ---------------------------------------------------------------------------
todas = listar()  # de qualquer ano, p/ caso o usuário queira editar antigos
if todas:
    st.subheader("✏️ Gerenciar uma despesa")
    opcoes = {
        f"{r['data'].strftime('%d/%m/%Y')} · {r['tipo']} · {r['paciente']} · R$ {r['valor_pago']:,.2f}": r["id"]
        for r in todas
    }
    sel = st.selectbox("Selecione", list(opcoes.keys()))
    did = opcoes[sel]
    reg = next(r for r in todas if r["id"] == did)

    with st.container(border=True):
        ec1, ec2, ec3 = st.columns(3)
        with ec1:
            nd = st.date_input("Data", value=reg["data"], format="DD/MM/YYYY", key=f"ed_d_{did}")
            nt = st.selectbox("Tipo", TIPOS,
                              index=TIPOS.index(reg["tipo"]) if reg["tipo"] in TIPOS else 0,
                              key=f"ed_t_{did}")
        with ec2:
            np_ = st.text_input("Paciente", value=reg["paciente"], key=f"ed_p_{did}")
            npr = st.text_input("Prestador", value=reg["prestador"], key=f"ed_pr_{did}")
        with ec3:
            ncn = st.text_input("CNPJ/CPF", value=reg["cnpj_cpf"] or "", key=f"ed_cn_{did}")
            nvp = st.number_input("Pago (R$)", min_value=0.0, value=float(reg["valor_pago"]),
                                  step=50.0, format="%.2f", key=f"ed_vp_{did}")
        ec4, ec5 = st.columns([1, 2])
        with ec4:
            nvr = st.number_input("Reembolso (R$)", min_value=0.0,
                                  value=float(reg["valor_reembolsado"]),
                                  step=50.0, format="%.2f", key=f"ed_vr_{did}")
        with ec5:
            nob = st.text_input("Observação", value=reg["observacao"] or "", key=f"ed_o_{did}")

        a1, a2, a3 = st.columns(3)
        with a1:
            if st.button("💾 Salvar alterações", key=f"ed_save_{did}"):
                atualizar(did, nd, nt, np_, npr, ncn, float(nvp), float(nvr), nob)
                st.success("Alterações salvas.")
                st.rerun()
        with a2:
            if reg["tem_comprovante"]:
                nome_a, dados_a = comprovante(did)
                st.download_button(
                    "📎 Baixar comprovante", data=dados_a, file_name=nome_a,
                    key=f"dl_{did}",
                )
        with a3:
            if st.button("🗑️ Excluir", type="secondary", key=f"del_{did}"):
                excluir(did)
                st.rerun()

        # Anexar/substituir comprovante
        if not reg["tem_comprovante"]:
            st.caption("**Anexar comprovante** (nota fiscal ou recibo):")
            up = st.file_uploader("Arquivo", type=["pdf", "png", "jpg", "jpeg"],
                                  key=f"upn_{did}", label_visibility="collapsed")
            if up is not None and st.button("Anexar", key=f"upb_{did}"):
                anexar_comprovante(did, up.name, up.getvalue())
                st.rerun()
        else:
            with st.expander("Substituir comprovante"):
                up = st.file_uploader("Novo arquivo", type=["pdf", "png", "jpg", "jpeg"],
                                      key=f"ups_{did}")
                if up is not None and st.button("Substituir", key=f"upsb_{did}"):
                    anexar_comprovante(did, up.name, up.getvalue())
                    st.rerun()
