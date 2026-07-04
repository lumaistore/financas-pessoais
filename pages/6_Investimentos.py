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
from core.ui import aplicar_estilo, cabecalho_pagina
from services.investimentos import (
    CLASSES,
    MOEDAS,
    adicionar_posicao,
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
from services.aportes import excluir_compra, listar_compras, registrar_compra, total_aportes_mes
from services.proventos import (
    excluir_provento,
    ler_imagens,
    listar_proventos,
    registrar_proventos,
    total_proventos_mes,
)

INDEXADORES = ["", "CDI", "PREFIXADO", "IPCA"]

init_db()
aplicar_estilo()

cabecalho_pagina("Investimentos", icone="📈")
st.caption(
    "Sua carteira é guardada como fotos (snapshots) por data. Confira a posição "
    "abaixo, ajuste o que precisar e salve. Crie um novo snapshot quando quiser "
    "registrar a carteira numa nova data — assim o sistema mostra a evolução."
)

# Semeia o snapshot inicial pré-preenchido na primeira vez.
if criar_snapshot_inicial():
    st.success("Carregamos sua carteira inicial (01/06/2026) a partir dos prints enviados. Revise os valores abaixo.")

# ---------------------------------------------------------------------------
# 🛒 Compras / Aportes — histórico + conta como "Aplicação" do mês
# ---------------------------------------------------------------------------
st.subheader("🛒 Compras / Aportes")
st.caption(
    "Registre cada compra (ex.: 1000 BBAS3 a R\\$ 19,98 em 03/06). Cada compra "
    "entra no **histórico** e vira uma **Aplicação** naquele mês — aparecendo no "
    "'Aplicado' do Painel e nas Movimentações."
)

with st.expander("➕ Registrar compra / aporte", expanded=False):
    with st.form("nova_compra", clear_on_submit=True):
        cc1, cc2, cc3 = st.columns(3)
        with cc1:
            comp_data = st.date_input("Data da compra", value=date.today(), format="DD/MM/YYYY")
            comp_ativo = st.text_input("Ativo", placeholder="Ex.: BBAS3, ITSA4")
            comp_ticker = st.text_input("Ticker (opcional)", placeholder="Ex.: BBAS3")
        with cc2:
            comp_qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, format="%.6f", value=0.0)
            comp_preco = st.number_input("Preço unitário (R$)", min_value=0.0, step=0.01, format="%.2f", value=0.0)
            comp_classe = st.selectbox("Classe", CLASSES)
        with cc3:
            comp_total = st.number_input(
                "Valor total (R$) — opcional",
                min_value=0.0, step=100.0, format="%.2f", value=0.0,
                help="Se deixar 0, calculo automaticamente por quantidade × preço.",
            )
            comp_moeda = st.selectbox("Moeda", MOEDAS)
            comp_somar = st.checkbox("Somar à carteira (posições)", value=True,
                                      help="Desmarque se essa posição já está na foto da carteira.")
        comp_obs = st.text_input("Observação (opcional)")

        if st.form_submit_button("Registrar compra", type="primary"):
            total = comp_total or (comp_qtd * comp_preco if comp_qtd and comp_preco else 0.0)
            if not comp_ativo.strip():
                st.error("Informe o ativo.")
            elif total <= 0:
                st.error("Informe quantidade + preço, ou o valor total.")
            else:
                registrar_compra(
                    data_=comp_data, ativo=comp_ativo, valor_total=float(total),
                    ticker=comp_ticker or None, classe=comp_classe,
                    quantidade=comp_qtd or None, preco_unitario=comp_preco or None,
                    moeda=comp_moeda, observacao=comp_obs or None,
                    somar_carteira=comp_somar,
                )
                st.success(f"Compra registrada: {comp_ativo.upper()} — R\\$ {total:,.2f} "
                           f"(aplicação lançada em {comp_data.strftime('%m/%Y')}).")
                st.rerun()

# Histórico de compras
_compras = listar_compras()
if _compras:
    df_compras = pd.DataFrame(_compras)
    df_compras["data"] = df_compras["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
    df_show = df_compras[["data", "ativo", "ticker", "quantidade", "preco_unitario",
                          "valor_total", "classe"]].copy()
    df_show["quantidade"] = df_show["quantidade"].apply(lambda v: f"{v:g}" if pd.notna(v) else "—")
    df_show["preco_unitario"] = df_show["preco_unitario"].apply(
        lambda v: f"R$ {v:,.2f}" if pd.notna(v) else "—")
    df_show["valor_total"] = df_show["valor_total"].apply(lambda v: f"R$ {v:,.2f}")
    df_show.columns = ["Data", "Ativo", "Ticker", "Qtd", "Preço", "Valor total", "Classe"]
    st.dataframe(df_show, use_container_width=True, hide_index=True)

    # Total por mês
    tot_mes: dict = {}
    for c in _compras:
        tot_mes[c["mes_referencia"]] = tot_mes.get(c["mes_referencia"], 0.0) + c["valor_total"]
    resumo_txt = " · ".join(
        f"{m}: R\\$ {v:,.2f}" for m, v in sorted(tot_mes.items(), reverse=True)[:6]
    )
    st.caption(f"💰 Aportes por mês — {resumo_txt}")

    # Excluir uma compra
    op = {f"{c['data'].strftime('%d/%m/%Y')} · {c['ativo']} · R$ {c['valor_total']:,.2f}": c["id"]
          for c in _compras}
    ec1, ec2 = st.columns([3, 1])
    with ec1:
        sel_compra = st.selectbox("Excluir compra", ["(nenhuma)"] + list(op.keys()))
    with ec2:
        st.write("")
        if st.button("🗑️ Excluir", disabled=sel_compra == "(nenhuma)"):
            excluir_compra(op[sel_compra])
            st.rerun()
else:
    st.info("Nenhuma compra registrada ainda. Use o formulário acima.")

st.divider()

# ---------------------------------------------------------------------------
# 💰 Proventos / Dividendos — upload de prints lidos por IA
# ---------------------------------------------------------------------------
st.subheader("💰 Proventos / Dividendos")
st.caption(
    "Suba os **prints** dos proventos da corretora (dividendos, JCP, "
    "rendimentos de FII, amortização). A IA lê **ticker, tipo, valor e data** "
    "de cada um — você confere e salva."
)

with st.expander("📤 Enviar prints e ler com IA", expanded=False):
    up1, up2 = st.columns([3, 1])
    with up1:
        imgs = st.file_uploader(
            "Prints dos proventos (pode selecionar vários)",
            type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True,
            key="prov_uploader",
        )
    with up2:
        ano_prov = st.number_input("Ano", min_value=2000, max_value=2100,
                                    value=date.today().year, step=1)
    if imgs and st.button("🔍 Ler proventos das imagens", type="primary"):
        arquivos = []
        for f in imgs:
            ext = f.name.lower().rsplit(".", 1)[-1]
            mime = {"png": "image/png", "jpg": "image/jpeg",
                    "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext, "image/png")
            arquivos.append((f.getvalue(), mime))
        with st.spinner(f"Lendo {len(arquivos)} imagem(ns) com IA..."):
            lidos = ler_imagens(arquivos, int(ano_prov))
        if not lidos:
            st.warning("Não consegui extrair proventos (verifique a chave da API ou a nitidez das imagens).")
        else:
            # Preenche a cotação do dólar para proventos em USD.
            tem_usd = any(p.get("moeda") == "USD" for p in lidos)
            dolar = buscar_dolar() if tem_usd else None
            for p in lidos:
                p["cotacao"] = float(dolar or 5.0) if p.get("moeda") == "USD" else 1.0
            st.session_state["prov_lidos"] = lidos
            st.success(f"{len(lidos)} provento(s) lido(s). Confira abaixo e salve.")

    # Revisão dos proventos lidos (editável)
    if st.session_state.get("prov_lidos"):
        st.markdown("**Confira antes de salvar** (edite/remova o que precisar):")
        st.caption("Para proventos em **USD**, ajuste a **cotação** se quiser (já preenchi com o dólar de hoje). "
                   "O total é sempre convertido para reais.")
        df_prov = pd.DataFrame(st.session_state["prov_lidos"])
        edit_prov = st.data_editor(
            df_prov, num_rows="dynamic", use_container_width=True, hide_index=True,
            key="prov_editor",
            column_config={
                "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                "ticker": st.column_config.TextColumn("Ticker"),
                "tipo": st.column_config.SelectboxColumn(
                    "Tipo", options=["dividendo", "jcp", "rendimento", "amortizacao", "outro"]),
                "valor": st.column_config.NumberColumn("Valor (bruto)", format="%.2f", min_value=0.0),
                "moeda": st.column_config.SelectboxColumn("Moeda", options=["BRL", "USD"]),
                "cotacao": st.column_config.NumberColumn("Cotação USD→BRL", format="%.4f"),
                "imposto": st.column_config.NumberColumn("Imposto retido", format="%.2f"),
            },
        )
        # Total em reais (converte USD).
        _soma_brl = 0.0
        for _, r in edit_prov.iterrows():
            v = r.get("valor")
            if pd.isna(v):
                continue
            if str(r.get("moeda") or "BRL").upper() == "USD":
                _soma_brl += float(v) * float(r.get("cotacao") or 0.0)
            else:
                _soma_brl += float(v)
        st.caption(f"Total a salvar: **R\\$ {_soma_brl:,.2f}** em {len(edit_prov)} provento(s).")
        if st.button("💾 Salvar proventos", type="primary"):
            itens = []
            for _, r in edit_prov.iterrows():
                d = r.get("data")
                if isinstance(d, pd.Timestamp):
                    d = d.date()
                v = r.get("valor")
                tk = str(r.get("ticker") or "").strip().upper()
                if d and tk and pd.notna(v) and float(v) > 0:
                    _moeda = str(r.get("moeda") or "BRL").upper()
                    itens.append({
                        "data": d, "ticker": tk,
                        "tipo": str(r.get("tipo") or "dividendo"),
                        "valor": float(v), "moeda": _moeda,
                        "cotacao": float(r.get("cotacao") or (1.0 if _moeda == "BRL" else 0.0)),
                        "imposto": float(r.get("imposto") or 0.0) if pd.notna(r.get("imposto")) else 0.0,
                    })
            n = registrar_proventos(itens)
            st.session_state.pop("prov_lidos", None)
            st.success(f"{n} provento(s) salvo(s) (duplicatas ignoradas).")
            st.rerun()

# Histórico de proventos
_proventos = listar_proventos()
if _proventos:
    def _orig(p):
        simb = "US$" if p["moeda"] == "USD" else "R$"
        return f"{simb} {p['valor']:,.2f}"

    dfp = pd.DataFrame([{
        "Data": p["data"].strftime("%d/%m/%Y"), "Ticker": p["ticker"],
        "Tipo": p["tipo"], "Valor original": _orig(p),
        "Em R$": f"R$ {p['valor_brl']:,.2f}",
    } for p in _proventos])
    st.dataframe(dfp, use_container_width=True, hide_index=True)

    tot_mes: dict = {}
    for p in _proventos:
        tot_mes[p["mes_referencia"]] = tot_mes.get(p["mes_referencia"], 0.0) + p["valor_brl"]
    resumo = " · ".join(f"{m}: R\\$ {v:,.2f}" for m, v in sorted(tot_mes.items(), reverse=True)[:6])
    st.caption(f"💰 Proventos por mês (em R$) — {resumo}")

    op_prov = {f"{p['data'].strftime('%d/%m/%Y')} · {p['ticker']} · R$ {p['valor_brl']:,.2f}": p["id"]
               for p in _proventos}
    epc1, epc2 = st.columns([3, 1])
    with epc1:
        sel_prov = st.selectbox("Excluir provento", ["(nenhum)"] + list(op_prov.keys()))
    with epc2:
        st.write("")
        if st.button("🗑️ Excluir", key="del_prov", disabled=sel_prov == "(nenhum)"):
            excluir_provento(op_prov[sel_prov])
            st.rerun()
else:
    st.info("Nenhum provento registrado ainda. Envie os prints acima.")

st.divider()

# ---------------------------------------------------------------------------
# Adicionar aplicação (formulário guiado)
# ---------------------------------------------------------------------------
with st.expander("➕ Adicionar aplicação", expanded=not listar_datas()):
    st.caption(
        "**Ação / FII / ETF**: preencha **quantidade** e **preço de compra** — o "
        "**valor pago é calculado automaticamente** (qtd × preço). Se informar o "
        "**ticker**, o sistema **busca a cotação atual** e calcula o valor de "
        "mercado de hoje. **Renda fixa**: preencha o valor aplicado + (se CDI) "
        "% do índice e data de aplicação."
    )
    with st.form("nova_aplicacao", clear_on_submit=True):
        a1, a2, a3 = st.columns(3)
        with a1:
            novo_ativo = st.text_input("Ativo", placeholder="Ex.: BBSE3, CDB Banco X")
            nova_classe = st.selectbox("Classe", CLASSES)
            novo_ticker = st.text_input(
                "Ticker (cotação automática)",
                placeholder="Ex.: BBAS3, BBSE3, VIG",
                help="Símbolo na bolsa. Com ticker, busco o preço de hoje e calculo o valor de mercado.",
            )
        with a2:
            nova_qtd = st.number_input("Quantidade", min_value=0.0, step=1.0, format="%.6f", value=0.0)
            novo_preco = st.number_input(
                "Preço unitário de compra",
                min_value=0.0, step=0.01, format="%.2f", value=0.0,
                help="Quanto você pagou em cada cota/ação. Usado para o valor pago e preço médio.",
            )
            nova_moeda = st.selectbox("Moeda", MOEDAS)
        with a3:
            novo_investido = st.number_input(
                "Valor pago / aplicado (R$) — opcional",
                min_value=0.0, step=100.0, format="%.2f", value=0.0,
                help="Se preencher qtd × preço, eu calculo automaticamente. Preencha aqui só se quiser sobrescrever.",
            )
            novo_vm = st.number_input(
                "Valor de mercado atual (R$) — opcional",
                min_value=0.0, step=100.0, format="%.2f", value=0.0,
                help="Se informar o ticker, eu busco a cotação atual e calculo. Preencha só para sobrescrever.",
            )

        st.markdown("**Renda fixa (opcional):**")
        rf1, rf2, rf3 = st.columns(3)
        with rf1:
            novo_indexador = st.selectbox("Índice", INDEXADORES)
        with rf2:
            nova_taxa = st.number_input("% do índice", min_value=0.0, step=1.0, format="%.1f", value=0.0,
                                        help="Ex.: 102 para 102% do CDI.")
        with rf3:
            nova_aplicacao = st.date_input(
                "Data da compra/aplicação", value=date.today(), format="DD/MM/YYYY",
                help="Data em que o dinheiro entrou no investimento. Usada para contar "
                     "no 'Aplicado' do mês (e, se renda fixa, no cálculo do CDI).",
            )
        contar_aplic = st.checkbox(
            "📅 Contar como aplicação do mês (dinheiro novo)", value=True,
            help="Cria uma movimentação de aplicação nessa data — aparece no 'Aplicado' "
                 "do Painel. Desmarque se estiver só ajustando uma posição existente.",
        )

        enviar_aplic = st.form_submit_button("Adicionar aplicação", type="primary")
        if enviar_aplic:
            mensagens = []

            # (1) Valor pago = quantidade × preço de compra (se não foi informado).
            valor_pago = novo_investido or None
            if not valor_pago and nova_qtd and novo_preco:
                valor_pago = nova_qtd * novo_preco
                mensagens.append(f"💰 Valor pago calculado: R$ {valor_pago:,.2f} ({nova_qtd:g} × {novo_preco:.2f}).")

            # (2) Valor de mercado: busca cotação se tem ticker; senão usa
            # qtd × preço de compra; senão valor pago.
            vm = novo_vm or None
            if not vm and novo_ticker.strip() and nova_qtd:
                from services.cotacoes import _yf_ticker, buscar_precos
                tk = _yf_ticker(novo_ticker.strip(), nova_moeda)
                with st.spinner(f"Buscando cotação de {tk}..."):
                    precos = buscar_precos([tk])
                preco_atual = precos.get(tk)
                if preco_atual:
                    vm = nova_qtd * preco_atual
                    mensagens.append(
                        f"📈 Cotação atual de {novo_ticker.upper()}: R$ {preco_atual:,.2f} → "
                        f"valor de mercado R$ {vm:,.2f}."
                    )
                else:
                    mensagens.append(f"⚠️ Não consegui buscar a cotação de {tk}. Usando preço de compra.")
            if not vm and nova_qtd and novo_preco:
                vm = nova_qtd * novo_preco
            if not vm and valor_pago:
                vm = valor_pago

            if not novo_ativo.strip():
                st.error("Informe o nome do ativo.")
            elif not vm:
                st.error("Preencha pelo menos quantidade + preço, ou um valor de mercado.")
            else:
                linha = {
                    "ativo": novo_ativo.strip(),
                    "classe_ativo": nova_classe,
                    "moeda": nova_moeda,
                    "quantidade": nova_qtd or None,
                    "preco_unitario": novo_preco or None,
                    "valor_mercado": float(vm),
                    "valor_investido": valor_pago,
                    "ticker": novo_ticker.strip().upper() or None,
                    "indexador": novo_indexador or None,
                    "taxa_indice": nova_taxa or None,
                    "data_aplicacao": nova_aplicacao,
                }
                d = adicionar_posicao(linha)
                for m in mensagens:
                    st.info(m)
                # Também registra como aplicação do mês (histórico + movimentação),
                # sem re-somar à carteira (o snapshot já foi atualizado acima).
                if contar_aplic and (valor_pago or vm):
                    _valor_ap = float(valor_pago or vm)
                    _dt_ap = nova_aplicacao or date.today()
                    registrar_compra(
                        data_=_dt_ap, ativo=novo_ativo.strip(), valor_total=_valor_ap,
                        ticker=novo_ticker.strip().upper() or None, classe=nova_classe,
                        quantidade=nova_qtd or None, preco_unitario=novo_preco or None,
                        moeda=nova_moeda, somar_carteira=False,
                    )
                    st.info(f"📅 Aplicação de R\\$ {_valor_ap:,.2f} lançada em {_dt_ap.strftime('%m/%Y')} "
                            f"(aparece no 'Aplicado' do Painel).")
                st.success(f"'{novo_ativo.strip()}' adicionado ao snapshot de {d.strftime('%d/%m/%Y')}.")
                st.rerun()

datas = listar_datas()
if not datas:
    st.info("Nenhuma posição registrada ainda. Use **➕ Adicionar aplicação** acima.")
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
