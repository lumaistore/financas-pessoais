"""Retirada de Lucros — gerar recibo, devolver assinado, controle por mês."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.lucros import (
    adicionar_retirada,
    arquivo_assinado,
    arquivo_retirada,
    atualizar_retirada,
    config_completa,
    excluir_retirada,
    gerar_recibo_pdf,
    get_config,
    ler_recibo_pdf,
    listar_retiradas,
    registrar_assinado,
    remover_assinado,
    retiradas_por_mes,
    salvar_config,
    total_retiradas,
)

init_db()

st.title("Retirada de Lucros")
st.caption(
    "Gere o recibo preenchido, baixe para assinar e devolva a versão assinada. "
    "Acompanhe por mês o que já foi feito e o que falta."
)

# ---------------------------------------------------------------------------
# Dados fixos
# ---------------------------------------------------------------------------
cfg = get_config()
with st.expander("🏢 Dados da empresa e do beneficiário", expanded=not config_completa()):
    with st.form("config_lucros"):
        c1, c2 = st.columns(2)
        with c1:
            empresa = st.text_input("Empresa", value=cfg["empresa"])
            cnpj = st.text_input("CNPJ", value=cfg["cnpj"], placeholder="00.000.000/0001-00")
            cidade = st.text_input("Cidade (local do recibo)", value=cfg["cidade"], placeholder="Ex.: São Paulo")
        with c2:
            beneficiario = st.text_input("Beneficiário (nome)", value=cfg["beneficiario"])
            cpf = st.text_input("CPF/CNPJ do beneficiário", value=cfg["cpf"], placeholder="000.000.000-00")
        if st.form_submit_button("Salvar dados", type="primary"):
            salvar_config(empresa, cnpj, beneficiario, cpf, cidade)
            st.success("Dados salvos.")
            st.rerun()

if not config_completa():
    st.warning("Preencha os dados da empresa e do beneficiário acima para gerar recibos.")

st.divider()

# ---------------------------------------------------------------------------
# Nova retirada (gera recibo)
# ---------------------------------------------------------------------------
st.subheader("1. Nova retirada — gerar recibo")
with st.form("nova_retirada", clear_on_submit=True):
    r1, r2 = st.columns(2)
    with r1:
        data_dist = st.date_input("Data da distribuição", value=date.today(), format="DD/MM/YYYY")
    with r2:
        valor = st.number_input("Valor distribuído (R$)", min_value=0.0, step=100.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", placeholder="Ex.: Lucros referentes a maio/2026")
    if st.form_submit_button("Gerar recibo e registrar", type="primary", disabled=not config_completa()):
        if valor <= 0:
            st.error("Informe um valor maior que zero.")
        else:
            pdf = gerar_recibo_pdf(data_dist, float(valor))
            nome = f"recibo_lucros_{data_dist.strftime('%Y-%m-%d')}.pdf"
            rid = adicionar_retirada(data_dist, float(valor), nome, pdf, obs.strip() or None)
            st.session_state["ultimo_recibo"] = {"bytes": pdf, "nome": nome, "valor": float(valor)}
            st.success(f"Recibo gerado (R$ {valor:,.2f}). Baixe abaixo, assine e devolva na seção 4.")
            st.rerun()

ult = st.session_state.get("ultimo_recibo")
if ult:
    st.download_button(
        f"📄 Baixar recibo para assinar (R$ {ult['valor']:,.2f})",
        data=ult["bytes"], file_name=ult["nome"], mime="application/pdf",
    )

st.divider()

# ---------------------------------------------------------------------------
# Anexar recibo (antigo / já assinado) — lê valor e data
# ---------------------------------------------------------------------------
st.subheader("2. Anexar recibo já feito (lê valor e data sozinho)")
up = st.file_uploader("Recibo em PDF", type=["pdf"], key="anexo_pdf")
if up is not None:
    lido = ler_recibo_pdf(up.getvalue())
    if lido["valor"] is None and lido["data"] is None:
        st.info("Não consegui ler automaticamente (PDF pode ser uma imagem). Preencha à mão abaixo.")
    else:
        st.success(
            f"Li do PDF: data **{lido['data'].strftime('%d/%m/%Y') if lido['data'] else '—'}** · "
            f"valor **R$ {lido['valor']:,.2f}**" if lido["valor"] else "Li parcialmente — confira abaixo."
        )
    k = up.name
    ac1, ac2 = st.columns(2)
    with ac1:
        d_lida = st.date_input("Data", value=lido["data"] or date.today(), format="DD/MM/YYYY", key=f"ad_{k}")
    with ac2:
        v_lida = st.number_input("Valor (R$)", min_value=0.0, value=float(lido["valor"] or 0.0), step=100.0, format="%.2f", key=f"av_{k}")
    assinado_chk = st.checkbox("Este recibo já está assinado", value=True, key=f"as_{k}")
    obs_a = st.text_input("Observação (opcional)", key=f"ao_{k}")
    if st.button("Salvar este recibo"):
        if v_lida <= 0:
            st.error("Informe o valor.")
        else:
            if assinado_chk:
                rid = adicionar_retirada(d_lida, float(v_lida), observacao=obs_a.strip() or None)
                registrar_assinado(rid, up.name, up.getvalue())
            else:
                rid = adicionar_retirada(d_lida, float(v_lida), up.name, up.getvalue(), obs_a.strip() or None)
            st.success("Recibo anexado ao controle.")
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Resumo por mês (o que falta)
# ---------------------------------------------------------------------------
st.subheader("3. Resumo por mês")
ano_sel = int(st.number_input("Ano", min_value=2020, max_value=2100, value=date.today().year, step=1))
meses = retiradas_por_mes(ano_sel)

m1, m2 = st.columns(2)
m1.metric(f"Total distribuído em {ano_sel}", f"R$ {total_retiradas(ano_sel):,.2f}")
m2.metric("Total geral (todos os anos)", f"R$ {total_retiradas():,.2f}")

df_m = pd.DataFrame(meses)
df_m["Status"] = df_m["feito"].map({True: "✅ Feito", False: "⚠️ Falta"})
df_m["assin"] = df_m.apply(lambda r: f"{r['assinados']}/{r['qtd']}" if r["qtd"] else "—", axis=1)
df_show = df_m[["nome_mes", "Status", "qtd", "assin", "total"]].copy()
df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}" if v else "—")
df_show.columns = ["Mês", "Status", "Docs", "Assinados", "Total"]


def _pinta(row):
    cor = "background-color: #d4edda" if "Feito" in row["Status"] else "background-color: #fff3cd"
    return [cor] * len(row)


st.dataframe(df_show.style.apply(_pinta, axis=1), use_container_width=True, hide_index=True)
faltam = [m["nome_mes"] for m in meses if not m["feito"]]
if faltam:
    st.caption("🔎 Meses **sem** retirada registrada em " + str(ano_sel) + ": **" + ", ".join(faltam) + "**.")

# Documentos de um mês específico
mes_nomes = {m["nome_mes"]: m["mes"] for m in meses}
mes_escolhido = st.selectbox("Ver documentos do mês", list(mes_nomes.keys()), index=date.today().month - 1)
docs_mes = listar_retiradas(ano=ano_sel, mes=mes_nomes[mes_escolhido])
if docs_mes:
    for r in docs_mes:
        st.write(
            f"• {r['data'].strftime('%d/%m/%Y')} — R$ {r['valor']:,.2f} "
            f"{'✍️ assinado' if r['assinado'] else '🕓 aguardando assinatura'}"
            + (f" · {r['observacao']}" if r["observacao"] else "")
        )
else:
    st.caption("Nenhum documento neste mês.")

st.divider()

# ---------------------------------------------------------------------------
# Gerenciar registro (editar / devolver assinado / baixar / excluir)
# ---------------------------------------------------------------------------
st.subheader("4. Gerenciar registro (editar, devolver assinado, baixar)")
todos = listar_retiradas()
if not todos:
    st.info("Nenhuma retirada registrada ainda.")
    st.stop()

opcoes = {
    f"{r['data'].strftime('%d/%m/%Y')} · R$ {r['valor']:,.2f} · "
    f"{'assinado' if r['assinado'] else 'pendente'}": r["id"]
    for r in todos
}
sel = st.selectbox("Selecione um registro", list(opcoes.keys()))
rid = opcoes[sel]
reg = next(r for r in todos if r["id"] == rid)

with st.container(border=True):
    # Editar dados
    ed1, ed2 = st.columns(2)
    with ed1:
        nova_data = st.date_input("Data", value=reg["data"], format="DD/MM/YYYY", key=f"ed_d_{rid}")
    with ed2:
        novo_valor = st.number_input("Valor (R$)", min_value=0.0, value=float(reg["valor"]), step=100.0, format="%.2f", key=f"ed_v_{rid}")
    nova_obs = st.text_input("Observação", value=reg["observacao"] or "", key=f"ed_o_{rid}")
    if st.button("Salvar alterações", key=f"ed_save_{rid}"):
        atualizar_retirada(rid, nova_data, float(novo_valor), nova_obs.strip() or None)
        st.success("Alterações salvas.")
        st.rerun()

    st.markdown("**Devolver recibo assinado:**")
    if reg["tem_assinado"]:
        st.success(f"✍️ Já tem versão assinada anexada ({reg['assinado_nome']}).")
        nome_a, dados_a = arquivo_assinado(rid)
        da1, da2 = st.columns(2)
        with da1:
            st.download_button("📄 Baixar assinado", data=dados_a, file_name=nome_a, mime="application/pdf", key=f"dl_a_{rid}")
        with da2:
            if st.button("Remover assinado", key=f"rm_a_{rid}"):
                remover_assinado(rid)
                st.rerun()
    else:
        assinado_up = st.file_uploader("Suba o PDF assinado", type=["pdf"], key=f"up_a_{rid}")
        if assinado_up is not None and st.button("Anexar assinado", key=f"save_a_{rid}"):
            registrar_assinado(rid, assinado_up.name, assinado_up.getvalue())
            st.success("Versão assinada anexada!")
            st.rerun()

    st.markdown("**Outros:**")
    o1, o2 = st.columns(2)
    with o1:
        nome_r, dados_r = arquivo_retirada(rid)
        if dados_r:
            st.download_button("📄 Baixar recibo (não assinado)", data=dados_r, file_name=nome_r, mime="application/pdf", key=f"dl_r_{rid}")
    with o2:
        if st.button("🗑️ Excluir registro", key=f"del_{rid}", type="secondary"):
            excluir_retirada(rid)
            st.rerun()
