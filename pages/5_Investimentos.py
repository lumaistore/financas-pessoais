"""Tela de Investimentos (Fase 4).

A carteira é registrada como snapshots por data. O primeiro snapshot já vem
pré-preenchido com as posições extraídas dos prints enviados. Você confere/
ajusta numa tabela editável e cria novos snapshots ao longo do tempo para
acompanhar evolução e rendimento.
"""
import time
from datetime import date, datetime

import pandas as pd
import streamlit as st

from core.db import init_db
from services.investimentos import (
    CLASSES,
    MOEDAS,
    carregar_snapshot,
    cotacao_usd_do_snapshot,
    criar_snapshot_inicial,
    evolucao,
    excluir_snapshot,
    listar_datas,
    por_classe,
    preencher_metadados_conhecidos,
    rendimento,
    salvar_snapshot,
)
from services.cotacoes import atualizar_cotacoes, buscar_dolar, evolucao_intradiaria, ganho_perda

INDEXADORES = ["", "CDI", "PREFIXADO", "IPCA"]

init_db()

st.title("Investimentos")
st.caption(
    "Sua carteira é guardada como fotos (snapshots) por data. Confira a posição "
    "abaixo, ajuste o que precisar e salve. Crie um novo snapshot quando quiser "
    "registrar a carteira numa nova data — assim o sistema mostra a evolução."
)

# Semeia o snapshot inicial pré-preenchido na primeira vez.
if criar_snapshot_inicial():
    st.success("Carregamos sua carteira inicial (01/06/2026) a partir dos prints enviados. Revise os valores abaixo.")

datas = listar_datas()
if not datas:
    st.info("Nenhuma posição registrada ainda.")
    st.stop()

# ---------------------------------------------------------------------------
# Seleção / criação de snapshot
# ---------------------------------------------------------------------------
col_sel, col_nova = st.columns([2, 2])
with col_sel:
    data_ref = st.selectbox(
        "Snapshot (data da posição)",
        datas,
        format_func=lambda d: d.strftime("%d/%m/%Y"),
    )
with col_nova:
    nova_data = st.date_input("Criar/editar snapshot para a data", value=date.today())
    if st.button("Usar esta data"):
        if nova_data not in datas:
            # Começa o novo snapshot a partir da posição mais recente.
            base = carregar_snapshot(datas[0])
            salvar_snapshot(nova_data, base, cotacao_usd=cotacao_usd_do_snapshot(datas[0]))
        st.rerun()

cotacao_usd = st.number_input(
    "Cotação USD → BRL (aplicada aos ativos em dólar)",
    min_value=0.0,
    value=float(cotacao_usd_do_snapshot(data_ref)),
    step=0.01,
    format="%.4f",
)

st.divider()

# ---------------------------------------------------------------------------
# Atualização de mercado (Fase 13)
# ---------------------------------------------------------------------------
st.subheader("Atualização de mercado")
st.caption(
    "Busca o preço de ações, FIIs e ETFs na bolsa e estima a renda fixa CDI por "
    "carrego. Só os símbolos (tickers) saem da máquina — nada pessoal."
)
# Cotação do dólar do momento, bem visível.
dolar_mostrado = st.session_state.get("dolar_agora") or float(cotacao_usd_do_snapshot(data_ref))
cd1, cd2 = st.columns([1, 3])
cd1.metric("💵 Dólar agora (USD→BRL)", f"R$ {dolar_mostrado:,.4f}")
with cd2:
    st.write("")
    if st.button("Atualizar só o dólar"):
        d = buscar_dolar()
        if d:
            st.session_state["dolar_agora"] = d
            st.toast(f"Dólar agora: R$ {d:,.4f}")
        else:
            st.warning("Não consegui buscar o dólar agora.")
        st.rerun()

ca, cb, cc = st.columns([2, 2, 2])
with ca:
    if st.button("🔄 Atualizar cotações agora", type="primary"):
        with st.spinner("Buscando preços..."):
            res = atualizar_cotacoes(data_ref)
            st.session_state["ultima_atualizacao"] = res
            if isinstance(res, dict) and res.get("usd"):
                st.session_state["dolar_agora"] = res["usd"]
        st.rerun()
with cb:
    if st.button("Preencher tickers/índices conhecidos"):
        n = preencher_metadados_conhecidos(data_ref)
        st.success(f"{n} posição(ões) preenchida(s). Informe a data de aplicação da renda fixa.")
        st.rerun()
with cc:
    auto = st.checkbox("Atualizar sozinho (15 min)", help="Funciona enquanto esta aba estiver aberta.")

res = st.session_state.get("ultima_atualizacao")
if res and "erro" not in res:
    st.success(
        f"Última atualização: {res['momento']:%d/%m/%Y %H:%M} · "
        f"{res['atualizados']} cotações de bolsa, {res['rf_estimados']} de renda fixa · "
        f"CDI {res['cdi']:.2f}% a.a. · USD {res['usd']:.4f} · "
        f"carteira R$ {res['total']:,.2f}"
    )
    if res["falhas"]:
        st.warning(f"{res['falhas']} ticker(s) não retornaram preço (mantido o último valor).")

# Auto-atualização enquanto a aba está aberta (a cada ~15 min).
if auto:
    if "auto_ts" not in st.session_state:
        st.session_state["auto_ts"] = time.time()

    @st.fragment(run_every=60)
    def _auto_atualizar():
        if time.time() - st.session_state.get("auto_ts", 0) >= 900:
            st.session_state["auto_ts"] = time.time()
            st.session_state["ultima_atualizacao"] = atualizar_cotacoes(data_ref)
            st.rerun()
        st.caption(f"⏱️ Auto-atualização ligada (último check {datetime.now():%H:%M:%S}).")

    _auto_atualizar()
else:
    st.session_state.pop("auto_ts", None)

st.divider()

# ---------------------------------------------------------------------------
# Tabela editável das posições
# ---------------------------------------------------------------------------
st.subheader("Posições")
posicoes = carregar_snapshot(data_ref)
df = pd.DataFrame(posicoes)

edit = st.data_editor(
    df,
    use_container_width=True,
    hide_index=True,
    num_rows="dynamic",
    column_config={
        "ativo": st.column_config.TextColumn("Ativo", width="large", required=True),
        "classe_ativo": st.column_config.SelectboxColumn("Classe", options=CLASSES, required=True),
        "moeda": st.column_config.SelectboxColumn("Moeda", options=MOEDAS, required=True),
        "quantidade": st.column_config.NumberColumn("Qtd.", format="%.6f"),
        "preco_unitario": st.column_config.NumberColumn("Preço unit.", format="%.2f"),
        "valor_mercado": st.column_config.NumberColumn("Valor de mercado", format="%.2f", required=True),
        "valor_investido": st.column_config.NumberColumn("Valor investido (custo)", format="%.2f"),
        "ticker": st.column_config.TextColumn("Ticker", help="Símbolo na bolsa (ex.: BBAS3, HGCR11, VIG)."),
        "indexador": st.column_config.SelectboxColumn("Índice", options=INDEXADORES),
        "taxa_indice": st.column_config.NumberColumn("% índice", format="%.1f", help="Ex.: 102 para 102% do CDI."),
        "data_aplicacao": st.column_config.DateColumn("Aplicado em", format="DD/MM/YYYY"),
    },
    key=f"editor_inv_{data_ref}",
)

if st.button("Salvar snapshot", type="primary"):
    linhas = edit.to_dict("records")
    salvar_snapshot(data_ref, linhas, cotacao_usd=cotacao_usd)
    st.success("Snapshot salvo.")
    st.rerun()

col_x, col_y = st.columns([4, 1])
with col_y:
    if st.button("Excluir snapshot", type="secondary"):
        excluir_snapshot(data_ref)
        st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Resumo da carteira
# ---------------------------------------------------------------------------
st.subheader("Resumo da carteira")
total = total_brl = sum(p["valor_mercado"] * (cotacao_usd if p["moeda"] == "USD" else 1.0) for p in posicoes)
rend = rendimento(data_ref)

c1, c2, c3 = st.columns(3)
c1.metric("Patrimônio total", f"R$ {total_brl:,.2f}")
c2.metric("Rendimento (custo conhecido)", f"R$ {rend['lucro']:,.2f}", f"{rend['percentual']:.2f}%")
c3.metric("Posições", len(posicoes))

# --- Ganho / perda por período (histórico de atualizações) ----------------
st.markdown("**Ganho / perda por período**")
periodo = st.selectbox(
    "Período",
    ["Hoje", "7 dias", "30 dias", "90 dias", "Desde o início"],
    label_visibility="collapsed",
)
gp = ganho_perda(periodo)
if gp:
    g1, g2 = st.columns(2)
    g1.metric(
        f"Variação ({periodo})",
        f"R$ {gp['ganho']:,.2f}",
        f"{gp['percentual']:.2f}%",
    )
    g2.metric(
        "Base de comparação",
        f"R$ {gp['base']:,.2f}",
        help=f"Valor da carteira em {gp['momento_base']:%d/%m/%Y %H:%M}.",
    )
    intr = evolucao_intradiaria()
    if len(intr) >= 2:
        df_i = pd.DataFrame(intr).set_index("momento")
        st.line_chart(df_i["total"])
else:
    st.caption(
        "Atualize as cotações pelo menos **2 vezes** (em momentos diferentes) "
        "para o sistema medir o ganho/perda no tempo."
    )

# --- Por classe -----------------------------------------------------------
st.markdown("**Distribuição por classe**")
classes = por_classe(data_ref)
if classes:
    df_cls = pd.DataFrame(classes)
    cc1, cc2 = st.columns([2, 1])
    with cc1:
        st.bar_chart(df_cls.set_index("classe"))
    with cc2:
        df_show = df_cls.copy()
        df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
        df_show.columns = ["Classe", "Total"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)

st.divider()

# ---------------------------------------------------------------------------
# Evolução entre snapshots
# ---------------------------------------------------------------------------
st.subheader("Evolução do patrimônio")
evo = evolucao()
if len(evo) >= 2:
    df_evo = pd.DataFrame(evo)
    df_evo["data"] = pd.to_datetime(df_evo["data"])
    st.line_chart(df_evo.set_index("data")["total"])
else:
    st.caption(
        "Crie um novo snapshot em outra data (acima) para o sistema desenhar a "
        "evolução do patrimônio entre as datas."
    )
