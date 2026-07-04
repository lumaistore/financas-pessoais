"""Painel Mensal 2.0 — visão consolidada e inteligente do mês.

8 seções em cards visuais: saúde do mês, waterfall do fluxo, patrimônio
consolidado, saldo por conta, gastos, investimentos, alertas e compromissos.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo
from services.backup import criar_backup, listar_backups
from services.cartao import reembolso_lumai_por_fatura
from services.compromissos import (
    contar_ativos,
    listar_compromissos,
    total_financiamento_a_contratar,
    total_saldo_devedor,
)
from services.cotacoes import buscar_cdi_anual, buscar_dolar
from services.investimentos import (
    cotacao_usd_do_snapshot,
    listar_datas,
    por_classe,
    rendimento,
    total_carteira,
)
from services.movimentacoes import meses_disponiveis, por_categoria
from services.painel import (
    alertas,
    aportes_ano,
    dividendos_mes,
    evolucao_patrimonio_liquido,
    fluxo_com_delta,
    fluxo_por_conta,
    top_despesas,
    variacao_por_categoria,
)

init_db()
aplicar_estilo()

st.title("📊 Painel Mensal")
st.caption("Visão consolidada e inteligente das suas finanças.")

# ---------------------------------------------------------------------------
# Seletor de mês (dropdown pt-BR + navegação)
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
disponiveis = set(meses_disponiveis()) | {padrao}
for i in range(24):
    m = hoje.month - i
    y = hoje.year
    while m <= 0:
        m += 12
        y -= 1
    disponiveis.add(f"{y:04d}-{m:02d}")
meses_lista = sorted(disponiveis, reverse=True)

if "painel_mes" not in st.session_state:
    st.session_state["painel_mes"] = padrao if padrao in meses_lista else meses_lista[0]

col_a, col_b, col_c = st.columns([1, 4, 1])
idx = meses_lista.index(st.session_state["painel_mes"]) if st.session_state["painel_mes"] in meses_lista else 0
with col_a:
    if st.button("◀ Mês anterior", disabled=idx >= len(meses_lista) - 1):
        st.session_state["painel_mes"] = meses_lista[idx + 1]
        st.rerun()
with col_b:
    escolhido = st.selectbox("Mês", meses_lista, index=idx, format_func=_rotulo,
                              label_visibility="collapsed")
    if escolhido != st.session_state["painel_mes"]:
        st.session_state["painel_mes"] = escolhido
        st.rerun()
with col_c:
    if st.button("Próximo mês ▶", disabled=idx == 0):
        st.session_state["painel_mes"] = meses_lista[idx - 1]
        st.rerun()

mes_ref = st.session_state["painel_mes"]

# ---------------------------------------------------------------------------
# Helpers de exibição
# ---------------------------------------------------------------------------
def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


def _delta_str(pct: float, invertido: bool = False) -> str:
    """Formata delta em % com seta. `invertido=True` para gastos (subir é ruim)."""
    if pct is None:
        return "—"
    seta = "↑" if pct > 0 else ("↓" if pct < 0 else "")
    return f"{seta} {abs(pct):.1f}% vs mês anterior"


def _localizar_pagina(nome_chave: str) -> str:
    """Acha o arquivo da página cujo nome contém a chave (para page_link)."""
    import os
    pasta = os.path.dirname(os.path.abspath(__file__))
    for arq in os.listdir(pasta):
        if arq.endswith(".py") and nome_chave in arq:
            return arq
    return "1_Painel_Mensal.py"


# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — 🎯 Saúde do Mês
# ═══════════════════════════════════════════════════════════════════════
st.markdown(f"### 🎯 Saúde do Mês — {_rotulo(mes_ref)}")

f = fluxo_com_delta(mes_ref)

with st.container(border=True):
    c1, c2, c3 = st.columns(3)
    c1.metric(
        "💵 Recebido", _brl(f["receitas"]),
        _delta_str(f["receitas_delta"]),
        help="Receitas do mês (salário, LUMAI, resgates classificados como receita).",
    )
    c2.metric(
        "💸 Gasto real", _brl(f["gasto_real"]),
        _delta_str(f["gasto_delta"]),
        delta_color="inverse",  # subir gasto = ruim (vermelho)
        help=(f"Cartão {_brl(f['gasto_cartao'])} + despesas "
              f"{_brl(f['gasto_movimentacoes'])}. Exclui LUMAI e transferências."),
    )
    c3.metric(
        "📈 Aplicado", _brl(f["aplicacoes"]),
        _delta_str(f["aplicacoes_delta"]),
        help="Enviado para investimentos (BTG etc).",
    )

    c4, c5 = st.columns(2)
    cor_sobra = "normal" if f["sobra"] >= 0 else "inverse"
    c4.metric(
        "💰 Sobra do mês", _brl(f["sobra"]),
        _delta_str(f["sobra_delta"]),
        delta_color=cor_sobra,
        help="Recebido − Gasto − Parcelas − Aplicações + Resgates.",
    )
    c5.metric(
        "📊 Taxa de poupança", f"{f['taxa_poupanca']:.1f}%",
        _delta_str(f["taxa_poupanca_delta"]),
        help="(Aplicado + Sobra) ÷ Recebido. Meta saudável: 20%+.",
    )

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 2 — 📊 Waterfall do Fluxo
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 📊 Fluxo do mês em cascata")
with st.container(border=True):
    import plotly.graph_objects as go

    valores = [
        f["receitas"], -f["gasto_real"], -f["parcelas"],
        -f["aplicacoes"], f["resgates"], 0,
    ]
    medidas = ["absolute", "relative", "relative", "relative", "relative", "total"]
    rotulos = ["Recebido", "Gastos", "Parcelas", "Aplicações", "Resgates", "Sobra"]

    wf = go.Figure(go.Waterfall(
        orientation="v",
        measure=medidas,
        x=rotulos,
        y=valores,
        text=[_brl(abs(v)) for v in valores[:-1]] + [_brl(f["sobra"])],
        textposition="outside",
        connector={"line": {"color": "rgb(200,200,200)"}},
        increasing={"marker": {"color": "#2ca02c"}},
        decreasing={"marker": {"color": "#d62728"}},
        totals={"marker": {"color": "#1f77b4"}},
    ))
    wf.update_layout(
        height=380, showlegend=False,
        margin=dict(l=20, r=20, t=10, b=20),
        yaxis_title="R$", template="simple_white",
    )
    st.plotly_chart(wf, use_container_width=True)

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 3 — 💰 Onde está seu dinheiro (Patrimônio)
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 💰 Onde está seu dinheiro")
datas_inv = listar_datas()
with st.container(border=True):
    if datas_inv:
        d_inv = datas_inv[0]
        carteira = total_carteira(d_inv)
        rend = rendimento(d_inv)
        saldo_dev = total_saldo_devedor()
        financ = total_financiamento_a_contratar()
        patrimonio_liq = carteira - saldo_dev

        p1, p2, p3 = st.columns(3)
        p1.metric("💎 Patrimônio líquido", _brl(patrimonio_liq),
                   help="Carteira de investimentos − saldo devedor.")
        p2.metric("📈 Carteira", _brl(carteira),
                   f"{rend['percentual']:+.2f}% (custo conhecido)")
        p3.metric("💳 Saldo devedor", _brl(saldo_dev),
                   help="Total dos compromissos ativos.")

        if financ:
            st.caption(f"⚡ Além disso: {_brl(financ)} de financiamento imobiliário a contratar na entrega.")

        # Evolução do patrimônio líquido
        evo = evolucao_patrimonio_liquido()
        if len(evo) >= 2:
            st.markdown("**Evolução do patrimônio líquido**")
            df_evo = pd.DataFrame(evo)
            df_evo["data"] = df_evo["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
            df_evo_show = df_evo[["data", "carteira", "patrimonio_liquido"]].copy()
            df_evo_show.columns = ["Data", "Carteira", "Patrimônio líquido"]
            st.line_chart(df_evo_show.set_index("Data"))
    else:
        st.caption("Nenhuma posição de investimento registrada. Cadastre em **Investimentos**.")

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 4 — 🏦 Saldo por Conta
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 🏦 Movimentação por conta bancária")
contas_fluxo = fluxo_por_conta(mes_ref)
with st.container(border=True):
    if contas_fluxo and any(c["entradas"] or c["saidas"] for c in contas_fluxo):
        df_c = pd.DataFrame(contas_fluxo)
        df_c = df_c[df_c["entradas"] + df_c["saidas"] > 0]  # esconde contas sem movimento
        if not df_c.empty:
            df_show = df_c[["apelido", "banco", "entradas", "saidas", "saldo_mes"]].copy()
            for col in ("entradas", "saidas", "saldo_mes"):
                df_show[col] = df_show[col].apply(_brl)
            df_show.columns = ["Conta", "Banco", "Entradas", "Saídas", "Saldo do mês"]
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        else:
            st.caption("Sem movimentações classificadas por conta neste mês.")
    else:
        st.caption("Nenhuma conta cadastrada ou sem movimentações. Cadastre em **🏦 Contas**.")

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 5 — 📉 Gastos (gráfico + variação + top)
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 📉 Análise de gastos")
with st.container(border=True):
    cats = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)

    gc1, gc2 = st.columns(2)
    with gc1:
        st.markdown("**Distribuição por categoria (pizza)**")
        if cats:
            import plotly.express as px
            df_pie = pd.DataFrame(cats)
            # agrupa da 8ª em diante
            if len(df_pie) > 8:
                df_top = df_pie.head(7)
                df_outros = pd.DataFrame([{
                    "categoria": "Outros",
                    "total": df_pie.iloc[7:]["total"].sum(),
                }])
                df_pie = pd.concat([df_top, df_outros])
            fig = px.pie(df_pie, values="total", names="categoria", hole=0.4)
            fig.update_layout(height=300, margin=dict(l=10, r=10, t=10, b=10),
                              legend=dict(orientation="h", y=-0.15))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.caption("Sem gastos categorizados.")

    with gc2:
        st.markdown("**Variação vs mês anterior**")
        variacoes = variacao_por_categoria(mes_ref)
        if variacoes:
            top_var = variacoes[:6]
            df_v = pd.DataFrame(top_var)
            df_v_show = df_v[["categoria", "atual", "delta_valor"]].copy()
            df_v_show["atual"] = df_v_show["atual"].apply(_brl)
            df_v_show["delta_valor"] = df_v_show["delta_valor"].apply(
                lambda v: f"{'↑' if v > 0 else '↓' if v < 0 else '='} {_brl(abs(v))}"
            )
            df_v_show.columns = ["Categoria", "Mês atual", "Variação"]
            st.dataframe(df_v_show, use_container_width=True, hide_index=True)
        else:
            st.caption("Sem dados de comparação.")

    # Top 5 despesas
    st.markdown("**Top 5 despesas do mês**")
    top5 = top_despesas(mes_ref, n=5)
    if top5:
        df_t = pd.DataFrame(top5)
        df_t["data"] = df_t["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
        df_t["valor"] = df_t["valor"].apply(_brl)
        df_t.columns = ["Data", "Descrição", "Valor", "Categoria"]
        st.dataframe(df_t, use_container_width=True, hide_index=True)
    else:
        st.caption("Sem despesas registradas.")

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 6 — 📈 Investimentos
# ═══════════════════════════════════════════════════════════════════════
st.markdown("### 📈 Investimentos e cotações")
with st.container(border=True):
    if datas_inv:
        ic1, ic2, ic3, ic4 = st.columns(4)
        ic1.metric("Dividendos no mês", _brl(dividendos_mes(mes_ref)),
                    help="Aproximação: resgates + receitas com termos como 'dividendos', 'JCP', 'proventos'.")
        ic2.metric("Aportes no ano", _brl(aportes_ano(int(mes_ref[:4]))))
        # Cotações ao vivo
        dolar = st.session_state.get("dolar_agora") or float(cotacao_usd_do_snapshot(datas_inv[0]))
        ic3.metric("💵 Dólar", f"R$ {dolar:,.4f}")
        try:
            cdi = buscar_cdi_anual()
            ic4.metric("📊 CDI (a.a.)", f"{cdi:.2f}%")
        except Exception:
            ic4.metric("📊 CDI (a.a.)", "—")

        atualizar_col1, _ = st.columns([1, 3])
        with atualizar_col1:
            if st.button("🔄 Atualizar dólar"):
                v = buscar_dolar()
                if v:
                    st.session_state["dolar_agora"] = v
                st.rerun()

        # Distribuição por classe (donut)
        classes = por_classe(datas_inv[0])
        if classes:
            import plotly.express as px
            df_cls = pd.DataFrame(classes)
            fig = px.pie(df_cls, values="total", names="classe", hole=0.5,
                          title="Distribuição da carteira por classe")
            fig.update_layout(height=350, margin=dict(l=10, r=10, t=40, b=10),
                              legend=dict(orientation="h", y=-0.1))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.caption("Sem carteira cadastrada. Cadastre em **Investimentos**.")

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 7 — ⚠️ Alertas e Pendências
# ═══════════════════════════════════════════════════════════════════════
lista_alertas = alertas(mes_ref)
if lista_alertas:
    st.markdown("### ⚠️ Alertas e pendências")
    for a in lista_alertas:
        with st.container(border=True):
            ac1, ac2 = st.columns([4, 1])
            with ac1:
                if a["tipo"] == "warning":
                    st.warning(f"**{a['titulo']}** — {a['descricao']}")
                else:
                    st.info(f"**{a['titulo']}** — {a['descricao']}")
            with ac2:
                if a.get("pagina_alvo"):
                    st.page_link(f"pages/{_localizar_pagina(a['pagina_alvo'])}",
                                  label="Abrir →", icon="🔗")

# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 8 — 🎯 Compromissos ativos (compacto)
# ═══════════════════════════════════════════════════════════════════════
ativos = listar_compromissos(apenas_ativos=True)
if ativos:
    st.markdown("### 🎯 Compromissos em andamento")
    with st.container(border=True):
        cc1, cc2 = st.columns(2)
        cc1.metric("Compromissos ativos", contar_ativos())
        cc2.metric("Saldo devedor total", _brl(total_saldo_devedor()))

        for c in ativos:
            prox = c["proxima_data"].strftime("%d/%m/%Y") if c["proxima_data"] else "—"
            if c.get("eh_imovel"):
                st.progress(min(c["progresso"], 1.0),
                             text=(f"🏢 {c['nome']} — {c['progresso']*100:.0f}% pago · "
                                   f"saldo à vista {_brl(c['saldo_devedor'])} · próx {prox}"))
            else:
                pct = c["parcelas_pagas"] / max(c["total_parcelas"], 1)
                st.progress(pct,
                             text=(f"{c['nome']} — {c['parcelas_pagas']}/{c['total_parcelas']} pagas · "
                                   f"saldo {_brl(c['saldo_devedor'])} · próx {prox}"))

# ═══════════════════════════════════════════════════════════════════════
# BACKUP (compacto no fim)
# ═══════════════════════════════════════════════════════════════════════
with st.expander("💾 Backup dos dados"):
    if st.button("Fazer backup agora"):
        caminho = criar_backup()
        st.success(f"Backup criado: {caminho}")
    bks = listar_backups()
    if bks:
        df_bk = pd.DataFrame(bks)
        df_bk["modificado"] = df_bk["modificado"].apply(lambda d: d.strftime("%d/%m/%Y %H:%M"))
        df_bk.columns = ["Arquivo", "Tamanho (KB)", "Criado em"]
        st.dataframe(df_bk, use_container_width=True, hide_index=True)

