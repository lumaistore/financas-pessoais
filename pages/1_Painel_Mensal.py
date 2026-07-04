"""Painel Mensal 2.0 — visão consolidada e inteligente do mês.

8 seções em cards visuais: saúde do mês, waterfall do fluxo, patrimônio
consolidado, saldo por conta, gastos, investimentos, alertas e compromissos.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import COR, aplicar_estilo, cabecalho_pagina, kpi
from services.backup import criar_backup, listar_backups
from services.cartao import reembolso_lumai_por_fatura
from services.compromissos import (
    contar_ativos,
    listar_compromissos,
    resumo_imoveis,
    total_financiamento_a_contratar,
    total_saldo_devedor,
)
from services.cotacoes import buscar_cdi_anual, buscar_dolar
from services.investimentos import (
    composicao_por_classe,
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
    gastos_categoria_pivot,
    media_gasto_meses,
    top_despesas,
)

init_db()
aplicar_estilo()

cabecalho_pagina("Painel Mensal",
                 "Visão consolidada e inteligente das suas finanças.", "📊")

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


def _rotulo_curto(mes_str: str) -> str:
    """Rótulo compacto para cabeçalho de coluna: 'Julho/26'."""
    try:
        ano, m = mes_str.split("-")
        return f"{MESES_PT[int(m)].capitalize()}/{ano[2:]}"
    except Exception:
        return mes_str


hoje = date.today()
padrao = hoje.strftime("%Y-%m")
com_dados = meses_disponiveis()  # já vem do mais recente ao mais antigo
disponiveis = set(com_dados) | {padrao}
for i in range(24):
    m = hoje.month - i
    y = hoje.year
    while m <= 0:
        m += 12
        y -= 1
    disponiveis.add(f"{y:04d}-{m:02d}")
meses_lista = sorted(disponiveis, reverse=True)

if "painel_mes" not in st.session_state:
    # Abre no mês corrente se ele já tiver dados; senão, no último mês com
    # dados (ex.: julho vazio → abre em junho). O usuário ainda pode navegar.
    if padrao in com_dados or not com_dados:
        st.session_state["painel_mes"] = padrao if padrao in meses_lista else meses_lista[0]
    else:
        st.session_state["painel_mes"] = com_dados[0]

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


def _localizar_pagina(nome_chave: str) -> str:
    """Acha o arquivo da página cujo nome contém a chave (para page_link)."""
    import os
    pasta = os.path.dirname(os.path.abspath(__file__))
    for arq in os.listdir(pasta):
        if arq.endswith(".py") and nome_chave in arq:
            return arq
    return "1_Painel_Mensal.py"


def _delta_pill(pct, higher_good: bool = True):
    """Retorna (texto, tom) para uma pill de variação vs mês anterior."""
    if pct is None:
        return ("sem base anterior", "neutro")
    seta = "↑" if pct > 0 else ("↓" if pct < 0 else "→")
    bom = (pct > 0) if higher_good else (pct < 0)
    tom = "sucesso" if bom else ("perigo" if pct != 0 else "neutro")
    return (f"{seta} {abs(pct):.0f}% vs mês ant.", tom)


# ═══════════════════════════════════════════════════════════════════════
# SEÇÃO 1 — 🎯 Saúde do Mês
# ═══════════════════════════════════════════════════════════════════════
st.markdown(f"### 🎯 Saúde do mês — {_rotulo(mes_ref)}")

f = fluxo_com_delta(mes_ref)

c1, c2, c3 = st.columns(3)
with c1:
    d, t = _delta_pill(f["receitas_delta"], higher_good=True)
    kpi("Recebido", _brl(f["receitas"]), d, t, icone="💵")
with c2:
    d, t = _delta_pill(f["gasto_delta"], higher_good=False)
    _cats_mes = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
    if _cats_mes:
        hover_gasto = "&#10;".join(f"{c['categoria']}: {_brl(c['total'])}"
                                    for c in _cats_mes[:12])
    else:
        hover_gasto = "Sem gastos neste mês"
    kpi("Gasto real", _brl(f["gasto_real"]), d, t, icone="💸", hover=hover_gasto)
with c3:
    d, t = _delta_pill(f["aplicacoes_delta"], higher_good=True)
    kpi("Aplicado", _brl(f["aplicacoes"]), d, t, icone="📈")

c4, c5 = st.columns(2)
with c4:
    mg = media_gasto_meses(mes_ref, n=3)
    if mg["meses_usados"]:
        vs = mg["atual_vs_media_pct"]
        if vs is None:
            pill_txt, pill_tom = f"base: {len(mg['meses_usados'])} mês(es)", "neutro"
        elif vs > 5:
            pill_txt, pill_tom = f"↑ {abs(vs):.0f}% acima da média", "perigo"
        elif vs < -5:
            pill_txt, pill_tom = f"↓ {abs(vs):.0f}% abaixo da média", "sucesso"
        else:
            pill_txt, pill_tom = "em linha com a média", "neutro"
        # Detalhamento para o hover: totais por mês + média por categoria.
        linhas_h = [f"{_rotulo_curto(m)}: {_brl(v)}" for m, v in mg["detalhe_meses"]]
        linhas_h.append("──── média por categoria ────")
        linhas_h += [f"{c}: {_brl(v)}" for c, v in mg["por_categoria"][:10]]
        hover_media = "&#10;".join(linhas_h)
        kpi("Média de gasto (3m)", _brl(mg["media"]), pill_txt, pill_tom,
            icone="📉", hover=hover_media)
    else:
        kpi("Média de gasto (3m)", "—", "sem histórico ainda", "neutro", icone="📉")
with c5:
    d, t = _delta_pill(f["taxa_poupanca_delta"], higher_good=True)
    meta = "meta 20%+" if f["taxa_poupanca"] >= 20 else "abaixo da meta"
    tom_meta = "sucesso" if f["taxa_poupanca"] >= 20 else "aviso"
    kpi("Taxa de poupança", f"{f['taxa_poupanca']:.0f}%", meta, tom_meta, icone="📊")

# Detalhamento expansível dos gastos (mês atual + média por categoria)
with st.expander("🔍 Ver detalhamento dos gastos"):
    dc1, dc2 = st.columns(2)
    with dc1:
        st.markdown(f"**{_rotulo(mes_ref)} — por categoria**")
        _cats_atual = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
        if _cats_atual:
            _df = pd.DataFrame(_cats_atual)
            _df["total"] = _df["total"].apply(_brl)
            _df.columns = ["Categoria", "Total"]
            st.dataframe(_df, hide_index=True, use_container_width=True)
        else:
            st.caption("Sem gastos registrados neste mês.")
    with dc2:
        if mg["por_categoria"]:
            st.markdown("**Média por categoria (últimos meses)**")
            _base = ", ".join(_rotulo_curto(m) for m, _ in mg["detalhe_meses"])
            st.caption(f"Base: {_base}")
            _dfm = pd.DataFrame(mg["por_categoria"], columns=["Categoria", "Média/mês"])
            _dfm["Média/mês"] = _dfm["Média/mês"].apply(_brl)
            st.dataframe(_dfm, hide_index=True, use_container_width=True)
        else:
            st.caption("Sem histórico suficiente para a média.")

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
        financ = total_financiamento_a_contratar()
        imoveis = resumo_imoveis()
        pago_imoveis = imoveis["total_pago"]
        # Patrimônio líquido = carteira + o que já foi pago nos imóveis
        # (sem considerar juros/parcelas futuras).
        patrimonio_liq = carteira + pago_imoveis

        p1, p2, p3 = st.columns(3)
        p1.metric(
            "💎 Patrimônio líquido", _brl(patrimonio_liq),
            help=(f"Carteira {_brl(carteira)} + já pago em imóveis "
                  f"{_brl(pago_imoveis)}. Não considera juros nem parcelas futuras."),
        )
        p2.metric("📈 Carteira", _brl(carteira),
                   f"{rend['percentual']:+.2f}% (custo conhecido)")
        p3.metric("🏠 Já pago em imóveis", _brl(pago_imoveis),
                   help="Soma do que você já pagou nos imóveis (SP + Carneiros), sem juros.")

        # Discreto ao lado: quanto ainda falta pagar (sem juros).
        partes_falta = [f"SP em parcelas: {_brl(imoveis['sp_falta'])}"]
        if imoveis["carneiros_sem_valor"]:
            partes_falta.append(
                "Carneiros: informe o **valor do imóvel** na aba Financiamentos"
            )
        else:
            partes_falta.append(
                f"Carneiros (imóvel − pago): {_brl(imoveis['carneiros_falta'])}"
            )
        st.caption(
            f"🧮 Falta pagar (sem juros): **{_brl(imoveis['falta_total'])}** "
            f"— {' · '.join(partes_falta)}."
        )
        if financ:
            st.caption(f"⚡ Além disso: {_brl(financ)} de financiamento imobiliário a contratar na entrega.")

        # Evolução da carteira de investimentos
        evo = evolucao_patrimonio_liquido()
        if len(evo) >= 2:
            st.markdown("**Evolução da carteira**")
            df_evo = pd.DataFrame(evo)
            df_evo["data"] = df_evo["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
            df_evo_show = df_evo[["data", "carteira"]].copy()
            df_evo_show.columns = ["Data", "Carteira"]
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
        st.markdown(f"**Top 5 despesas — {_rotulo(mes_ref)}**")
        top5 = top_despesas(mes_ref, n=5)
        if top5:
            df_t = pd.DataFrame(top5)
            df_t["data"] = df_t["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
            df_t["valor"] = df_t["valor"].apply(_brl)
            df_t.columns = ["Data", "Descrição", "Valor", "Categoria"]
            st.dataframe(df_t, use_container_width=True, hide_index=True)
        else:
            st.caption("Sem despesas neste mês.")

    # ---- Gasto por categoria — mês a mês (todos os meses com dados) ----
    st.markdown("**Gasto por categoria — mês a mês**")
    pivot = gastos_categoria_pivot()
    meses_p = pivot["meses"]
    if meses_p and pivot["linhas"]:
        registros = []
        for ln in pivot["linhas"]:
            reg = {"Categoria": ln["categoria"]}
            for m in meses_p:
                reg[_rotulo_curto(m)] = ln["por_mes"].get(m, 0.0)
            registros.append(reg)
        df_p = pd.DataFrame(registros)

        # Variação PERCENTUAL entre os dois últimos meses COMPLETOS
        # (ignora o mês corrente, que ainda está em andamento).
        def _fmt_pct(ant_v: float, ult_v: float) -> str:
            if ant_v == 0:
                return "novo" if ult_v > 0 else "—"
            pct = (ult_v - ant_v) / ant_v * 100
            seta = "↑" if pct > 0 else ("↓" if pct < 0 else "=")
            return f"{seta} {abs(pct):.0f}%"

        mes_corrente = date.today().strftime("%Y-%m")
        completos = [m for m in meses_p if m != mes_corrente]
        col_var = None
        if len(completos) >= 2:
            ant, ult = completos[-2], completos[-1]
            col_var = f"Δ% {_rotulo_curto(ant)}→{_rotulo_curto(ult)}"
            df_p[col_var] = [
                _fmt_pct(ln["por_mes"].get(ant, 0.0), ln["por_mes"].get(ult, 0.0))
                for ln in pivot["linhas"]
            ]

        # Linha de TOTAL ao final
        totais = {"Categoria": "TOTAL"}
        for m in meses_p:
            totais[_rotulo_curto(m)] = sum(ln["por_mes"].get(m, 0.0) for ln in pivot["linhas"])
        if col_var:
            soma_ant = sum(ln["por_mes"].get(ant, 0.0) for ln in pivot["linhas"])
            soma_ult = sum(ln["por_mes"].get(ult, 0.0) for ln in pivot["linhas"])
            totais[col_var] = _fmt_pct(soma_ant, soma_ult)
        df_p = pd.concat([df_p, pd.DataFrame([totais])], ignore_index=True)

        # Formatação em R$ (só as colunas de mês; a variação já é texto).
        for m in meses_p:
            lbl = _rotulo_curto(m)
            df_p[lbl] = df_p[lbl].apply(lambda v: f"R$ {v:,.2f}")

        st.dataframe(df_p, use_container_width=True, hide_index=True)
        if col_var:
            st.caption(
                f"Variação percentual entre os dois últimos meses completos "
                f"({_rotulo(completos[-2])} → {_rotulo(completos[-1])}). "
                f"'novo' = categoria sem gasto no mês anterior. "
                f"O mês corrente ({_rotulo(mes_corrente)}) está em andamento e "
                f"fica de fora da comparação."
            )
    else:
        st.caption("Ainda não há despesas registradas para comparar entre meses.")

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

        # Distribuição por classe (donut) — hover mostra os ativos da classe
        comp = composicao_por_classe(datas_inv[0])
        if comp:
            import plotly.graph_objects as go

            labels = [c["classe"] for c in comp]
            values = [c["total"] for c in comp]
            # Monta o detalhamento (ativo: R$ valor) de cada classe para o hover.
            detalhes = []
            for c in comp:
                linhas = "<br>".join(
                    f"&nbsp;&nbsp;• {ativo}: R$ {v:,.2f}"
                    for ativo, v in c["itens"][:15]
                )
                extra = "" if len(c["itens"]) <= 15 else f"<br>&nbsp;&nbsp;… +{len(c['itens'])-15} ativos"
                detalhes.append(linhas + extra)

            fig = go.Figure(go.Pie(
                labels=labels,
                values=values,
                hole=0.5,
                customdata=detalhes,
                sort=False,
                hovertemplate=(
                    "<b>%{label}</b> — %{percent}<br>"
                    "Total: R$ %{value:,.2f}<br>"
                    "<br>%{customdata}<extra></extra>"
                ),
                textinfo="label+percent",
            ))
            fig.update_layout(
                title="Distribuição da carteira por classe",
                height=380, margin=dict(l=10, r=10, t=40, b=10),
                legend=dict(orientation="h", y=-0.1),
                hoverlabel=dict(align="left"),
            )
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
                # Escapa "$" para o Streamlit não interpretar "R$ ... $" como LaTeX.
                titulo = a["titulo"].replace("$", "\\$")
                descricao = a["descricao"].replace("$", "\\$")
                if a["tipo"] == "warning":
                    st.warning(f"**{titulo}** — {descricao}")
                else:
                    st.info(f"**{titulo}** — {descricao}")
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

