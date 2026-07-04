"""Movimentações — receitas, despesas e visão unificada em 3 sub-abas.

Cada aba com resumo, gráficos diários, listas cronológicas e ranking
por fonte (com detalhamento no hover).
"""
from datetime import date

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from core.db import init_db
from core.ui import COR, aplicar_estilo, cabecalho_pagina, kpi
from services.cartao import listar_categorias
from services.contas import listar_contas
from services.movimentacoes import (
    FORMAS,
    TIPOS,
    adicionar,
    atualizar,
    excluir,
    listar,
    meses_disponiveis,
    por_categoria,
    por_dia,
    por_fonte,
    resumo_mes,
    total_lumai_a_reembolsar,
)

init_db()
aplicar_estilo()

cabecalho_pagina(
    "Movimentações",
    "Todas as entradas e saídas do mês. Transferências entre suas contas não contam.",
    "💰",
)

# ---------------------------------------------------------------------------
# Auto-sincronização silenciosa (uma vez por sessão)
# ---------------------------------------------------------------------------
if not st.session_state.get("mov_autosync"):
    from services.sincronizar import sincronizar_tudo
    resultado_auto = sincronizar_tudo()
    total_auto = sum(resultado_auto.values())
    st.session_state["mov_autosync"] = True
    if total_auto > 0:
        partes = [f"**{v}** de {k}" for k, v in resultado_auto.items() if v > 0]
        st.info(f"🔗 Sincronização automática: {total_auto} movimentação(ões) trazidas ({', '.join(partes)}).")

# ---------------------------------------------------------------------------
# Raio-X: de onde vêm os dados (transparência total)
# ---------------------------------------------------------------------------
with st.expander("🔍 Raio-X: onde estão meus dados?"):
    from services.movimentacoes import listar as _listar_todas
    todas_movs = _listar_todas()
    if not todas_movs:
        st.caption("Ainda não há nenhuma movimentação no banco.")
    else:
        by_origem: dict = {}
        by_mes: dict = {}
        for m in todas_movs:
            origem_key = (m.get("origem") or "manual").split(":")[0]
            by_origem[origem_key] = by_origem.get(origem_key, 0) + 1
            by_mes[m["mes_referencia"]] = by_mes.get(m["mes_referencia"], 0) + 1
        cols = st.columns(2)
        with cols[0]:
            st.markdown("**Por origem:**")
            for k, v in sorted(by_origem.items(), key=lambda x: -x[1]):
                st.write(f"- `{k}`: {v} movimentação(ões)")
        with cols[1]:
            st.markdown("**Por mês:**")
            for k, v in sorted(by_mes.items(), reverse=True)[:6]:
                st.write(f"- **{k}**: {v} movimentação(ões)")
    if st.button("🔄 Forçar re-sincronização agora"):
        from services.sincronizar import sincronizar_tudo
        with st.spinner("Sincronizando..."):
            r = sincronizar_tudo()
        total = sum(r.values())
        if total == 0:
            st.info("Tudo já está sincronizado.")
        else:
            partes = [f"**{v}** de {k}" for k, v in r.items() if v > 0]
            st.success(f"✅ +{total}: {', '.join(partes)}")
        st.rerun()

# ---------------------------------------------------------------------------
# Seletor de mês fácil (dropdown com meses existentes + navegação)
# ---------------------------------------------------------------------------
MESES_PT = {
    1: "janeiro", 2: "fevereiro", 3: "março", 4: "abril", 5: "maio", 6: "junho",
    7: "julho", 8: "agosto", 9: "setembro", 10: "outubro", 11: "novembro", 12: "dezembro",
}


def _rotulo(mes_str: str) -> str:
    try:
        ano, m = mes_str.split("-")
        return f"{MESES_PT[int(m)].capitalize()} / {ano}"
    except Exception:
        return mes_str


hoje = date.today()
padrao = hoje.strftime("%Y-%m")
com_dados = meses_disponiveis()  # do mais recente ao mais antigo
disponiveis = set(com_dados) | {padrao}
for i in range(24):
    m = hoje.month - i
    y = hoje.year
    while m <= 0:
        m += 12
        y -= 1
    disponiveis.add(f"{y:04d}-{m:02d}")
meses_lista = sorted(disponiveis, reverse=True)

if "mov_mes" not in st.session_state:
    # Abre no mês corrente se tiver dados; senão, no último mês com dados.
    if padrao in com_dados or not com_dados:
        st.session_state["mov_mes"] = padrao if padrao in meses_lista else meses_lista[0]
    else:
        st.session_state["mov_mes"] = com_dados[0]

col_a, col_b, col_c = st.columns([1, 4, 1])
idx_atual = meses_lista.index(st.session_state["mov_mes"]) if st.session_state["mov_mes"] in meses_lista else 0
with col_a:
    if st.button("◀ Mês anterior", disabled=idx_atual >= len(meses_lista) - 1):
        st.session_state["mov_mes"] = meses_lista[idx_atual + 1]
        st.rerun()
with col_b:
    escolhido = st.selectbox(
        "Mês de referência", meses_lista, index=idx_atual,
        format_func=_rotulo, key="mov_mes_select", label_visibility="collapsed",
    )
    if escolhido != st.session_state["mov_mes"]:
        st.session_state["mov_mes"] = escolhido
        st.rerun()
with col_c:
    if st.button("Próximo mês ▶", disabled=idx_atual == 0):
        st.session_state["mov_mes"] = meses_lista[idx_atual - 1]
        st.rerun()

mes_ref = st.session_state["mov_mes"]

# ---------------------------------------------------------------------------
# Resumo (KPIs 2x2 para não cortar em telas menores)
# ---------------------------------------------------------------------------
r = resumo_mes(mes_ref)


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


k1, k2 = st.columns(2)
with k1:
    kpi("Recebido", _brl(r["receitas"]), icone="💵")
with k2:
    kpi("Gasto real", _brl(r["despesas"]), "exclui LUMAI", "neutro", icone="💸")
k3, k4 = st.columns(2)
with k3:
    kpi("Aplicado", _brl(r["aplicacoes"]), "para investimentos", "accent", icone="📈")
with k4:
    cor_saldo = COR["sucesso"] if r["saldo"] >= 0 else COR["perigo"]
    kpi("Saldo do mês", _brl(r["saldo"]), icone="💰", cor_valor=cor_saldo)

lumai_pend = total_lumai_a_reembolsar(mes_ref)
if lumai_pend:
    st.info(f"💼 R$ {lumai_pend:,.2f} em despesas LUMAI a reembolsar (não contam no gasto).")

st.divider()

# ---------------------------------------------------------------------------
# Formulário de nova movimentação
# ---------------------------------------------------------------------------
categorias = [c["nome"] for c in listar_categorias()]
contas = listar_contas()
opcoes_conta = {"(nenhuma)": None, **{c["apelido"]: c["id"] for c in contas}}

with st.expander("➕ Adicionar movimentação"):
    with st.form("nova_mov", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_ = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            descricao = st.text_input("Descrição", placeholder="Ex.: Mercado, Salário")
            valor = st.number_input("Valor (R$)", min_value=0.0, step=10.0, format="%.2f")
        with col2:
            tipo = st.selectbox("Tipo", TIPOS)
            forma = st.selectbox("Forma", ["(nenhuma)"] + FORMAS)
            conta_apelido = st.selectbox("Conta", list(opcoes_conta.keys()))
        with col3:
            categoria = st.selectbox("Categoria", ["(sem)"] + categorias)
            lumai = st.checkbox("LUMAI (reembolsar)")
            obs = st.text_input("Observação")

        if st.form_submit_button("Adicionar", type="primary"):
            if not descricao.strip() or valor <= 0:
                st.error("Preencha descrição e valor.")
            else:
                adicionar(
                    data_=data_, descricao=descricao, valor=float(valor), tipo=tipo,
                    forma=None if forma == "(nenhuma)" else forma,
                    categoria=None if categoria == "(sem)" else categoria,
                    conta_id=opcoes_conta[conta_apelido],
                    lumai=lumai, observacao=obs, origem="manual",
                )
                st.success("Adicionada.")
                st.rerun()


# ---------------------------------------------------------------------------
# Helpers de gráfico
# ---------------------------------------------------------------------------
def _grafico_diario(movs: list, tipo_label: str, cor: str,
                    mes_ref: str) -> go.Figure:
    """Gráfico de barras diário do MÊS SELECIONADO (mes_ref = 'AAAA-MM').
    O eixo x cobre todos os dias desse mês; lançamentos com data fora do mês
    não aparecem como barra (mas continuam nos totais)."""
    if not movs:
        return None
    df = pd.DataFrame([{"data": m["data"], "valor": m["valor"],
                        "descricao": m["descricao"]} for m in movs])
    df["dia"] = pd.to_datetime(df["data"]).dt.normalize()
    serie = df.groupby("dia")["valor"].sum()
    conta = df.groupby("dia")["descricao"].count()
    # Eixo ancorado no mês selecionado (não na data mais antiga dos dados).
    try:
        _ano, _mes = mes_ref.split("-")
        ini = pd.Timestamp(int(_ano), int(_mes), 1)
    except Exception:
        ini = serie.index.min().replace(day=1)
    fim = ini + pd.offsets.MonthEnd(1)
    todos_dias = pd.date_range(ini, fim, freq="D")
    serie = serie.reindex(todos_dias, fill_value=0.0)
    conta = conta.reindex(todos_dias, fill_value=0)

    fig = go.Figure(go.Bar(
        x=serie.index,
        y=serie.values,
        marker_color=cor,
        customdata=conta.values,
        hovertemplate=("<b>%{x|%d/%m/%Y}</b><br>" + tipo_label
                       + ": R$ %{y:,.2f}<br>Lançamentos: %{customdata}<extra></extra>"),
    ))
    fig.update_layout(
        height=300,
        margin=dict(l=30, r=20, t=10, b=30),
        xaxis=dict(title="", type="date", tickformat="%d/%m",
                   dtick=86400000 * 3, tickangle=0),  # tick a cada 3 dias
        yaxis=dict(title="", tickprefix="R$ "),
        template="simple_white",
        showlegend=False,
        bargap=0.25,
        font=dict(family="Inter, sans-serif", size=12),
    )
    return fig


def _ranking_com_hover(movs: list, titulo: str) -> None:
    """Ranking por fonte/descrição com bar chart + tabela detalhada
    (cada pagamento por baixo, no hover do gráfico)."""
    if not movs:
        return
    # Agrupar pela descrição base — os identificadores repetem em cima
    df = pd.DataFrame([{
        "descricao": m["descricao"],
        "valor": m["valor"],
        "data": m["data"],
    } for m in movs])
    # Chave-fonte: primeira parte da descrição (até 40 chars ou palavras)
    df["fonte"] = df["descricao"].apply(lambda d: (d or "(sem descrição)")[:60])

    # Agregação: total + lista com cada pagamento (para hover)
    def _detalhe(sub: pd.DataFrame) -> str:
        linhas = [
            f"{r['data'].strftime('%d/%m')}: {_brl(r['valor'])}"
            for _, r in sub.sort_values("data").iterrows()
        ]
        return "<br>".join(linhas)

    agrup = df.groupby("fonte").agg(
        total=("valor", "sum"),
        n=("valor", "count"),
    ).reset_index()
    agrup["detalhe"] = df.groupby("fonte").apply(_detalhe).reset_index(drop=True)
    agrup = agrup.sort_values("total", ascending=False)

    st.markdown(f"**🏆 {titulo}**")

    # Top 10 no gráfico (com hover detalhado)
    top10 = agrup.head(10).sort_values("total", ascending=True)  # ascending pra barras horizontais irem do maior no topo
    fig = go.Figure(go.Bar(
        y=top10["fonte"],
        x=top10["total"],
        orientation="h",
        marker_color="#1f77b4",
        text=[_brl(v) for v in top10["total"]],
        textposition="outside",
        customdata=list(zip(top10["n"], top10["detalhe"])),
        hovertemplate="<b>%{y}</b><br>"
                      + "Total: %{x:,.2f}<br>"
                      + "Lançamentos: %{customdata[0]}<br><br>"
                      + "%{customdata[1]}<extra></extra>",
    ))
    fig.update_layout(
        height=max(280, len(top10) * 32 + 60),
        margin=dict(l=10, r=30, t=10, b=30),
        xaxis=dict(title="R$"),
        yaxis=dict(title="", automargin=True),
        template="simple_white",
        showlegend=False,
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

    # Tabela detalhada completa
    with st.expander(f"Ver todas as fontes ({len(agrup)} agrupadas)"):
        df_show = agrup[["fonte", "n", "total"]].copy()
        df_show["total"] = df_show["total"].apply(_brl)
        df_show.columns = ["Fonte", "Qtd", "Total"]
        st.dataframe(df_show, use_container_width=True, hide_index=True)


def _lista_cronologica(movs: list) -> pd.DataFrame:
    """Ordena movimentações por data crescente (1º ao último dia do mês)."""
    if not movs:
        return pd.DataFrame()
    df = pd.DataFrame(movs).sort_values("data", ascending=True)
    dv = df.copy()
    dv["data"] = dv["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
    dv["valor"] = dv["valor"].apply(_brl)
    if "lumai" in dv.columns:
        dv["lumai"] = dv["lumai"].map({True: "✅", False: ""})
    return dv


# ---------------------------------------------------------------------------
# 3 abas: Receitas / Despesas / Movimentações (tudo)
# ---------------------------------------------------------------------------
aba_rec, aba_desp, aba_todas = st.tabs(["💵 Receitas", "💸 Despesas", "📋 Todas as movimentações"])


# ---------- Aba Receitas ---------------------------------------------------
with aba_rec:
    st.subheader(f"Receitas em {_rotulo(mes_ref)}")
    # Receitas de FORA da carteira do usuário (exclui transferência interna)
    receitas = [m for m in listar(mes_referencia=mes_ref, tipos=["receita"])]
    resgates = listar(mes_referencia=mes_ref, tipos=["resgate"])
    total_rec = sum(m["valor"] for m in receitas)
    total_res = sum(m["valor"] for m in resgates)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total recebido", _brl(total_rec))
    m2.metric("Resgates de aplicação", _brl(total_res))
    m3.metric("Nº de entradas", len(receitas) + len(resgates))

    if not receitas and not resgates:
        st.info("Sem receitas ou resgates neste mês.")
    else:
        # Gráfico diário
        st.markdown("**📈 Evolução das entradas ao longo do mês** (por dia)")
        fig = _grafico_diario(receitas + resgates, "Entradas", "#2ca02c", mes_ref)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Ranking com hover
        _ranking_com_hover(receitas + resgates,
                            "Ranking por fonte (passe o mouse para ver cada pagamento)")

        # Lista cronológica
        st.markdown("**📅 Todas as entradas (ordem cronológica — 1º ao último dia)**")
        todas_entradas = receitas + resgates
        dv = _lista_cronologica(todas_entradas)
        if not dv.empty:
            dv = dv[["data", "descricao", "tipo", "categoria", "valor", "origem"]]
            dv.columns = ["Data", "Descrição", "Tipo", "Categoria", "Valor", "Origem"]
            st.dataframe(dv, use_container_width=True, hide_index=True)


# ---------- Aba Despesas ---------------------------------------------------
with aba_desp:
    st.subheader(f"Despesas em {_rotulo(mes_ref)}")
    despesas = listar(mes_referencia=mes_ref, tipos=["despesa"])
    despesas_sem_lumai = [d for d in despesas if not d["lumai"]]
    despesas_lumai = [d for d in despesas if d["lumai"]]
    total_desp = sum(d["valor"] for d in despesas_sem_lumai)
    total_lumai = sum(d["valor"] for d in despesas_lumai)

    m1, m2 = st.columns(2)
    m1.metric("Gasto real (você)", _brl(total_desp), help="Exclui LUMAI.")
    m2.metric("Despesas LUMAI", _brl(total_lumai),
              help="A serem reembolsadas — não contam no seu gasto.")
    m3, m4 = st.columns(2)
    m3.metric("Total lançado", _brl(total_desp + total_lumai))
    m4.metric("Nº de despesas", len(despesas))

    if not despesas:
        st.info("Sem despesas neste mês.")
    else:
        # Gráfico diário (só despesas suas)
        st.markdown("**📈 Evolução dos gastos ao longo do mês** (por dia, excluindo LUMAI)")
        fig = _grafico_diario(despesas_sem_lumai, "Gastos", "#d62728", mes_ref)
        if fig:
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})
        # Aviso se há despesas com data fora do mês selecionado.
        _fora = [d for d in despesas_sem_lumai if d["data"].strftime("%Y-%m") != mes_ref]
        if _fora:
            _soma_fora = sum(d["valor"] for d in _fora)
            st.caption(
                f"⚠️ {len(_fora)} despesa(s) deste mês têm **data fora de {_rotulo(mes_ref)}** "
                f"(somam R\\$ {_soma_fora:,.2f}) — por isso não aparecem no gráfico por dia. "
                f"Isso costuma ser data errada de cartão/importação. Dá para corrigir na "
                f"auditoria do Painel ou aqui na aba 'Todas'."
            )

        # Pizza por categoria
        st.markdown("**🥧 Gasto por categoria**")
        cats = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
        if cats:
            df_pie = pd.DataFrame(cats)
            if len(df_pie) > 8:
                df_top = df_pie.head(7)
                df_outros = pd.DataFrame([{
                    "categoria": "Outros",
                    "total": df_pie.iloc[7:]["total"].sum(),
                }])
                df_pie = pd.concat([df_top, df_outros])
            figp = px.pie(df_pie, values="total", names="categoria", hole=0.4)
            figp.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10),
                                legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(figp, use_container_width=True, config={"displayModeBar": False})

        # Ranking de destinos das despesas (para quem/onde você mais gasta)
        _ranking_com_hover(despesas_sem_lumai,
                            "Ranking por destino (para onde vai seu dinheiro)")

        # Lista cronológica
        st.markdown("**📅 Todas as despesas (ordem cronológica — 1º ao último dia)**")
        dv = _lista_cronologica(despesas)
        if not dv.empty:
            dv = dv[["data", "descricao", "categoria", "forma", "valor", "lumai", "origem"]]
            dv.columns = ["Data", "Descrição", "Categoria", "Forma", "Valor", "LUMAI", "Origem"]
            st.dataframe(dv, use_container_width=True, hide_index=True)


# ---------- Aba Todas -----------------------------------------------------
with aba_todas:
    st.subheader(f"Todas as movimentações em {_rotulo(mes_ref)}")

    filtros = st.multiselect(
        "Filtrar por tipo", TIPOS,
        default=["receita", "despesa", "aplicacao", "resgate"],
        help="Transferências ficam ocultas por padrão (não afetam o fluxo).",
    )
    movs = listar(mes_referencia=mes_ref, tipos=filtros)
    if not movs:
        st.info("Sem movimentações neste filtro.")
    else:
        entradas = sum(m["valor"] for m in movs if m["tipo"] in ("receita", "resgate"))
        saidas = sum(m["valor"] for m in movs if m["tipo"] in ("despesa", "aplicacao") and not m["lumai"])

        m1, m2, m3 = st.columns(3)
        m1.metric("Entradas", _brl(entradas))
        m2.metric("Saídas", _brl(saidas))
        m3.metric("Movs", len(movs))

        # Gráfico: entradas vs saídas por dia (barras agrupadas)
        st.markdown("**📊 Entradas vs Saídas por dia**")
        df_all = pd.DataFrame([{
            "data": m["data"],
            "grupo": ("Entrada" if m["tipo"] in ("receita", "resgate")
                     else "Saída" if m["tipo"] in ("despesa", "aplicacao") and not m["lumai"]
                     else None),
            "valor": m["valor"],
        } for m in movs])
        df_all = df_all[df_all["grupo"].notna()]
        if not df_all.empty:
            df_all["dia"] = pd.to_datetime(df_all["data"])
            grp = df_all.groupby([df_all["dia"].dt.date, "grupo"])["valor"].sum().reset_index()
            grp.columns = ["dia", "grupo", "valor"]
            grp["dia_dt"] = pd.to_datetime(grp["dia"])
            fig = px.bar(
                grp, x="dia_dt", y="valor", color="grupo",
                color_discrete_map={"Entrada": "#2ca02c", "Saída": "#d62728"},
                barmode="group",
            )
            fig.update_layout(
                height=340,
                xaxis=dict(title="", type="date", tickformat="%d/%m", dtick=86400000*3, tickangle=0),
                yaxis=dict(title="R$"),
                template="simple_white",
                legend_title_text="",
                margin=dict(l=30, r=20, t=20, b=40),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # Lista cronológica completa
        st.markdown("**📅 Lista cronológica completa**")
        dv = _lista_cronologica(movs)
        if not dv.empty:
            dv = dv[["data", "descricao", "tipo", "categoria", "forma", "valor", "lumai", "origem"]]
            dv.columns = ["Data", "Descrição", "Tipo", "Categoria", "Forma", "Valor", "LUMAI", "Origem"]
            st.dataframe(dv, use_container_width=True, hide_index=True)

        # --- Editar/excluir ---
        st.divider()
        st.markdown("**✏️ Editar ou excluir**")
        opcoes = {
            f"{m['data'].strftime('%d/%m')} · {m['tipo']} · R$ {m['valor']:,.2f} · {m['descricao'][:40]}": m["id"]
            for m in movs
        }
        sel = st.selectbox("Movimentação", list(opcoes.keys()))
        mid = opcoes[sel]
        reg = next(m for m in movs if m["id"] == mid)

        with st.container(border=True):
            e1, e2, e3 = st.columns(3)
            with e1:
                nd = st.date_input("Data", value=reg["data"], format="DD/MM/YYYY", key=f"ed_d_{mid}")
                ndes = st.text_input("Descrição", value=reg["descricao"], key=f"ed_ds_{mid}")
            with e2:
                nt = st.selectbox("Tipo", TIPOS,
                                    index=TIPOS.index(reg["tipo"]) if reg["tipo"] in TIPOS else 0,
                                    key=f"ed_t_{mid}")
                nf = st.selectbox("Forma", ["(nenhuma)"] + FORMAS,
                                    index=(FORMAS.index(reg["forma"]) + 1) if reg["forma"] in FORMAS else 0,
                                    key=f"ed_f_{mid}")
            with e3:
                nv = st.number_input("Valor", min_value=0.0, value=float(reg["valor"]),
                                     step=10.0, format="%.2f", key=f"ed_v_{mid}")
                nc = st.selectbox("Categoria", ["(sem)"] + categorias,
                                    index=(categorias.index(reg["categoria"]) + 1) if reg["categoria"] in categorias else 0,
                                    key=f"ed_c_{mid}")
                nl = st.checkbox("LUMAI", value=reg["lumai"], key=f"ed_l_{mid}")

            a1, a2 = st.columns(2)
            with a1:
                if st.button("💾 Salvar", key=f"sv_{mid}"):
                    atualizar(mid, data=nd, descricao=ndes, valor=float(nv), tipo=nt,
                              forma=None if nf == "(nenhuma)" else nf,
                              categoria=None if nc == "(sem)" else nc, lumai=nl)
                    st.rerun()
            with a2:
                if st.button("🗑️ Excluir", type="secondary", key=f"del_{mid}"):
                    excluir(mid)
                    st.rerun()
