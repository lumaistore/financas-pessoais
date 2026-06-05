"""Retirada de Lucros — gerar recibo preenchido e controlar o total distribuído."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.lucros import (
    adicionar_retirada,
    arquivo_retirada,
    config_completa,
    excluir_retirada,
    gerar_recibo_pdf,
    get_config,
    listar_retiradas,
    salvar_config,
    total_retiradas,
)

init_db()

st.title("Retirada de Lucros")
st.caption(
    "Gere o recibo de distribuição de lucros já preenchido (você só assina), "
    "guarde cada retirada e acompanhe o total distribuído."
)

# ---------------------------------------------------------------------------
# Dados fixos (empresa / beneficiário)
# ---------------------------------------------------------------------------
cfg = get_config()
with st.expander("🏢 Dados da empresa e do beneficiário", expanded=not config_completa()):
    st.caption("Preenchidos uma vez e usados em todos os recibos.")
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
st.subheader("Nova retirada (gerar recibo)")
with st.form("nova_retirada", clear_on_submit=True):
    r1, r2 = st.columns(2)
    with r1:
        data_dist = st.date_input("Data da distribuição", value=date.today(), format="DD/MM/YYYY")
    with r2:
        valor = st.number_input("Valor distribuído (R$)", min_value=0.0, step=100.0, format="%.2f")
    obs = st.text_input("Observação (opcional)", placeholder="Ex.: Lucros referentes a maio/2026")
    gerar = st.form_submit_button("Gerar recibo e registrar", type="primary", disabled=not config_completa())
    if gerar:
        if valor <= 0:
            st.error("Informe um valor maior que zero.")
        else:
            pdf = gerar_recibo_pdf(data_dist, float(valor))
            nome = f"recibo_lucros_{data_dist.strftime('%Y-%m-%d')}.pdf"
            rid = adicionar_retirada(data_dist, float(valor), nome, pdf, obs.strip() or None)
            st.session_state["ultimo_recibo"] = {"bytes": pdf, "nome": nome, "valor": float(valor)}
            st.success(f"Recibo gerado e registrado (R$ {valor:,.2f}). Baixe abaixo para assinar.")
            st.rerun()

ult = st.session_state.get("ultimo_recibo")
if ult:
    st.download_button(
        f"📄 Baixar recibo gerado (R$ {ult['valor']:,.2f})",
        data=ult["bytes"],
        file_name=ult["nome"],
        mime="application/pdf",
    )

st.divider()

# ---------------------------------------------------------------------------
# Anexar retirada antiga
# ---------------------------------------------------------------------------
with st.expander("📎 Anexar retirada antiga (recibo que você já fez)"):
    with st.form("anexar_retirada", clear_on_submit=True):
        a1, a2 = st.columns(2)
        with a1:
            data_ant = st.date_input("Data da distribuição", value=date.today(), format="DD/MM/YYYY", key="data_ant")
        with a2:
            valor_ant = st.number_input("Valor (R$)", min_value=0.0, step=100.0, format="%.2f", key="valor_ant")
        arquivo = st.file_uploader("Recibo (PDF)", type=["pdf"])
        obs_ant = st.text_input("Observação (opcional)", key="obs_ant")
        if st.form_submit_button("Anexar retirada"):
            if valor_ant <= 0:
                st.error("Informe o valor.")
            else:
                nome = arquivo.name if arquivo else None
                dados = arquivo.getvalue() if arquivo else None
                adicionar_retirada(data_ant, float(valor_ant), nome, dados, obs_ant.strip() or None)
                st.success("Retirada anexada ao controle.")
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Histórico e total
# ---------------------------------------------------------------------------
st.subheader("Histórico de retiradas")
retiradas = listar_retiradas()
if not retiradas:
    st.info("Nenhuma retirada registrada ainda.")
    st.stop()

ano_atual = date.today().year
t1, t2 = st.columns(2)
t1.metric("Total distribuído (geral)", f"R$ {total_retiradas():,.2f}")
t2.metric(f"Total em {ano_atual}", f"R$ {total_retiradas(ano_atual):,.2f}")

df = pd.DataFrame(retiradas)
df_view = df[["data", "valor", "observacao", "tem_arquivo"]].copy()
df_view["data"] = df_view["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
df_view["valor"] = df_view["valor"].apply(lambda v: f"R$ {v:,.2f}")
df_view["tem_arquivo"] = df_view["tem_arquivo"].map({True: "📎 Sim", False: "—"})
df_view.columns = ["Data", "Valor", "Observação", "Recibo"]
st.dataframe(df_view, use_container_width=True, hide_index=True)

# Baixar / excluir um registro
st.caption("Baixar recibo ou excluir um registro:")
opcoes = {
    f"{r['data'].strftime('%d/%m/%Y')} · R$ {r['valor']:,.2f}": r["id"] for r in retiradas
}
sel = st.selectbox("Registro", list(opcoes.keys()))
rid = opcoes[sel]
b1, b2 = st.columns(2)
with b1:
    nome, dados = arquivo_retirada(rid)
    if dados:
        st.download_button("📄 Baixar recibo", data=dados, file_name=nome or f"recibo_{rid}.pdf", mime="application/pdf")
    else:
        st.caption("Sem arquivo anexado neste registro.")
with b2:
    if st.button("Excluir registro", type="secondary"):
        excluir_retirada(rid)
        st.rerun()
