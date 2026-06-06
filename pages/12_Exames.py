"""Exames médicos — anexa laudos e oferece análise educativa por IA."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from services.exames import (
    CATEGORIAS,
    DISCLAIMER,
    adicionar,
    analisar_com_ia,
    analise,
    arquivo,
    atualizar,
    excluir,
    extrair_texto,
    historico_mesmo_nome,
    inferir_categoria,
    inferir_data,
    inferir_laboratorio,
    inferir_nome,
    listar,
    salvar_analise,
    texto,
)
from services.perfil import paciente_padrao

init_db()

st.title("Exames Médicos")
st.caption(
    "Guarde aqui os laudos de exames e peça uma leitura educativa em texto. "
    "Útil para entender o que o exame mostra e levar dúvidas certas ao médico."
)
st.warning(
    "⚠️ A análise por IA é **educativa**, não substitui consulta médica. "
    "Ela é gerada a partir do texto do laudo e pode interpretar números "
    "errado. Sempre converse com seu médico."
)

# ---------------------------------------------------------------------------
# Upload com leitura automática
# ---------------------------------------------------------------------------
st.subheader("➕ Anexar exame")
arq = st.file_uploader(
    "Laudo em PDF",
    type=["pdf"],
    key="exame_up",
    help="Suba o laudo. O sistema lê data, laboratório e categoria sozinho.",
)

if arq is not None:
    if st.session_state.get("ex_nome_arq") != arq.name:
        with st.spinner("Lendo o laudo..."):
            tx = extrair_texto(arq.getvalue())
            st.session_state["ex_texto"] = tx
            st.session_state["ex_bytes"] = arq.getvalue()
            st.session_state["ex_nome_arq"] = arq.name
            st.session_state["ex_categoria"] = inferir_categoria(tx) or "Outros"
            st.session_state["ex_data"] = inferir_data(tx) or date.today()
            st.session_state["ex_lab"] = inferir_laboratorio(tx) or ""
            st.session_state["ex_nome"] = inferir_nome(tx, st.session_state["ex_categoria"])
    pistas = []
    if st.session_state.get("ex_data"):
        pistas.append(f"📅 {st.session_state['ex_data'].strftime('%d/%m/%Y')}")
    if st.session_state.get("ex_nome"):
        pistas.append(f"🧪 {st.session_state['ex_nome']}")
    if st.session_state.get("ex_categoria"):
        pistas.append(f"🏷️ {st.session_state['ex_categoria']}")
    if st.session_state.get("ex_lab"):
        pistas.append(f"🏥 {st.session_state['ex_lab']}")
    if pistas:
        st.success("Li do laudo: " + " · ".join(pistas))
    else:
        st.info("Não consegui extrair texto (PDF pode ser imagem). Preencha à mão.")

with st.form("novo_exame", clear_on_submit=False):
    c1, c2, c3 = st.columns(3)
    with c1:
        data_ = st.date_input("Data do exame", value=st.session_state.get("ex_data") or date.today(), format="DD/MM/YYYY")
        nome = st.text_input("Nome do exame", value=st.session_state.get("ex_nome") or "")
    with c2:
        cat_default = st.session_state.get("ex_categoria") or "Outros"
        categoria = st.selectbox("Categoria", CATEGORIAS,
                                  index=CATEGORIAS.index(cat_default) if cat_default in CATEGORIAS else len(CATEGORIAS) - 1)
        paciente = st.text_input("Paciente", value=paciente_padrao() or "")
    with c3:
        laboratorio = st.text_input("Laboratório / clínica", value=st.session_state.get("ex_lab") or "")
        obs = st.text_input("Observação", placeholder="Ex.: solicitado por Dr. Fulano")

    if st.form_submit_button("Adicionar exame", type="primary", disabled=arq is None):
        if not paciente.strip():
            st.error("Informe o paciente.")
        else:
            adicionar(
                data_=data_,
                nome=nome,
                categoria=categoria,
                paciente=paciente,
                arquivo_nome=arq.name,
                arquivo_dados=st.session_state.get("ex_bytes"),
                laboratorio=laboratorio,
                observacao=obs,
                texto_extraido=st.session_state.get("ex_texto"),
            )
            for k in ("ex_texto", "ex_bytes", "ex_nome_arq", "ex_categoria", "ex_data", "ex_lab", "ex_nome"):
                st.session_state.pop(k, None)
            st.success("Exame adicionado.")
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Lista + filtros
# ---------------------------------------------------------------------------
st.subheader("Meus exames")
f1, f2, f3 = st.columns(3)
with f1:
    ano_filtro = st.selectbox("Ano", ["(todos)"] + sorted({r["ano"] for r in listar()}, reverse=True))
with f2:
    cat_filtro = st.selectbox("Categoria", ["(todas)"] + CATEGORIAS)
with f3:
    pacs = sorted({r["paciente"] for r in listar()})
    pac_filtro = st.selectbox("Paciente", ["(todos)"] + pacs)

exames = listar(
    ano=None if ano_filtro == "(todos)" else int(ano_filtro),
    paciente=None if pac_filtro == "(todos)" else pac_filtro,
    categoria=None if cat_filtro == "(todas)" else cat_filtro,
)
if not exames:
    st.info("Nenhum exame com esse filtro.")
    st.stop()

df = pd.DataFrame(exames)
dfv = df[["data", "nome", "categoria", "paciente", "laboratorio", "tem_arquivo"]].copy()
dfv["data"] = dfv["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
dfv["tem_arquivo"] = dfv["tem_arquivo"].map({True: "📎", False: "—"})
dfv.columns = ["Data", "Exame", "Categoria", "Paciente", "Laboratório", "PDF"]
st.dataframe(dfv, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Detalhe do exame (analisar / baixar / editar / excluir)
# ---------------------------------------------------------------------------
st.subheader("Detalhes de um exame")
opcoes = {f"{r['data'].strftime('%d/%m/%Y')} · {r['nome']} · {r['paciente']}": r["id"] for r in exames}
sel = st.selectbox("Selecione", list(opcoes.keys()))
eid = opcoes[sel]
reg = next(r for r in exames if r["id"] == eid)

with st.container(border=True):
    e1, e2, e3 = st.columns(3)
    with e1:
        nd = st.date_input("Data", value=reg["data"], format="DD/MM/YYYY", key=f"ed_d_{eid}")
        nn = st.text_input("Nome", value=reg["nome"], key=f"ed_n_{eid}")
    with e2:
        nc = st.selectbox("Categoria", CATEGORIAS,
                           index=CATEGORIAS.index(reg["categoria"]) if reg["categoria"] in CATEGORIAS else len(CATEGORIAS) - 1,
                           key=f"ed_c_{eid}")
        npac = st.text_input("Paciente", value=reg["paciente"], key=f"ed_p_{eid}")
    with e3:
        nlab = st.text_input("Laboratório", value=reg["laboratorio"] or "", key=f"ed_l_{eid}")
        nobs = st.text_input("Observação", value=reg["observacao"] or "", key=f"ed_o_{eid}")

    a1, a2, a3 = st.columns(3)
    with a1:
        if st.button("💾 Salvar alterações", key=f"sv_{eid}"):
            atualizar(eid, nd, nn, nc, npac, nlab, nobs)
            st.success("Salvo.")
            st.rerun()
    with a2:
        nome_arq, dados = arquivo(eid)
        if dados:
            st.download_button("📎 Baixar laudo", data=dados, file_name=nome_arq, key=f"dl_{eid}")
    with a3:
        if st.button("🗑️ Excluir", type="secondary", key=f"del_{eid}"):
            excluir(eid)
            st.rerun()

# --- Análise educativa por IA --------------------------------------------
st.markdown("### 🤖 Análise educativa")
analise_salva = analise(eid)
if analise_salva:
    st.markdown(analise_salva)
    st.caption(DISCLAIMER)
    if st.button("🔄 Refazer análise", key=f"redo_{eid}"):
        analise_salva = None

if not analise_salva:
    txt = texto(eid)
    if not txt:
        st.caption("Este exame não tem texto extraído — não dá para analisar (PDF pode ser imagem).")
    else:
        st.caption(
            "Vai usar o seu acesso à IA para gerar uma leitura educativa do laudo "
            "(o texto do exame é enviado à API da Anthropic)."
        )
        if st.button("Gerar análise educativa", type="primary", key=f"go_{eid}"):
            try:
                with st.spinner("Lendo o laudo e gerando análise..."):
                    hist = historico_mesmo_nome(eid)
                    hist_resumo = ""
                    if hist:
                        hist_resumo = "; ".join(
                            f"{h['data'].strftime('%d/%m/%Y')} {h['nome']}" for h in hist[-5:]
                        )
                    resultado = analisar_com_ia(eid, hist_resumo or None)
                    salvar_analise(eid, resultado)
                st.rerun()
            except Exception as e:
                st.error(f"Falha ao analisar: {e}")

# --- Histórico do paciente -----------------------------------------------
hist = historico_mesmo_nome(eid)
if hist:
    st.markdown("### 📈 Outros exames do mesmo paciente / categoria")
    dfh = pd.DataFrame(hist)
    dfh["data"] = dfh["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
    dfh = dfh[["data", "nome", "categoria"]]
    dfh.columns = ["Data", "Exame", "Categoria"]
    st.dataframe(dfh, use_container_width=True, hide_index=True)
