"""Assessor de Investimentos — conversa com o Ricardo (IA) e sua equipe."""
from datetime import datetime

import streamlit as st

from core.db import init_db
from services.assessor import (
    DISCLAIMER,
    carregar_consulta,
    conversar,
    criar_consulta,
    duplicar_como_base,
    excluir_consulta,
    extrair_tickers_da_resposta,
    listar_consultas,
    montar_contexto_carteira,
    renomear_consulta,
    salvar_conversa,
)


def _formatar_pct(v):
    return f"{v:.2f}%" if v is not None else "—"


def _formatar_num(v, casas=2):
    return f"{v:,.{casas}f}" if v is not None else "—"


def renderizar_analise_tickers(tickers_lista: list, titulo: str):
    """Para cada ticker, busca dados reais (yfinance) e mostra tabela +
    gráfico Plotly no formato de research report."""
    if not tickers_lista:
        return
    from services.analise_ticker import analisar, gerar_grafico, linha_comparativo
    import pandas as pd

    st.markdown(f"### 📊 {titulo}")
    dados_por_ticker = {}
    with st.spinner(f"Buscando dados de mercado ({len(tickers_lista)} tickers)..."):
        for tk in tickers_lista:
            d = analisar(tk)
            if d:
                dados_por_ticker[tk] = d

    if not dados_por_ticker:
        st.warning("Não consegui buscar dados dos tickers.")
        return

    # Tabela comparativa
    linhas = [linha_comparativo(d) for d in dados_por_ticker.values()]
    df = pd.DataFrame(linhas)
    df_fmt = df.copy()
    for col in ("Preço", "Máx 5a", "Mín 5a", "Média 5a"):
        df_fmt[col] = df_fmt[col].apply(lambda v: f"R$ {v:,.2f}" if pd.notna(v) else "—")
    for col in ("DY %", "ROE %", "Vol 1a %", "Vol 5a %", "Ret 1a %", "Ret 5a %", "% da faixa"):
        df_fmt[col] = df_fmt[col].apply(lambda v: f"{v:.1f}%" if pd.notna(v) else "—")
    for col in ("P/VP", "P/L"):
        df_fmt[col] = df_fmt[col].apply(lambda v: f"{v:.2f}" if pd.notna(v) else "—")
    st.dataframe(df_fmt, use_container_width=True, hide_index=True)
    st.caption(
        "**Legenda:** DY = dividend yield · P/VP = preço/valor patrimonial · "
        "Vol = volatilidade anualizada · Ret = retorno acumulado · "
        "% da faixa = posição do preço atual entre a mínima (0%) e máxima (100%) dos últimos 5 anos."
    )

    # Gráfico de cada ticker
    for tk, d in dados_por_ticker.items():
        with st.expander(f"📈 {tk} — {d['nome']}", expanded=len(dados_por_ticker) <= 3):
            fig = gerar_grafico(d)
            st.plotly_chart(fig, use_container_width=True)

            i1, i2, i3, i4 = st.columns(4)
            i1.metric("Preço atual", f"R$ {d['preco_atual']:,.2f}")
            i2.metric("DY (12m)", _formatar_pct(d.get("dy_calculado") or d.get("dy")))
            i3.metric("P/VP", _formatar_num(d.get("pvp")))
            i4.metric("ROE", _formatar_pct(d.get("roe")))

            i5, i6, i7, i8 = st.columns(4)
            i5.metric("Vol 1a", _formatar_pct(d["vol_1a_pct"]))
            i6.metric("Vol 5a", _formatar_pct(d["vol_5a_pct"]))
            i7.metric("Retorno 5a", _formatar_pct(d["retorno_5a_pct"]))
            i8.metric("Posição na faixa 5a", f"{d['posicao_5a_pct']:.0f}%",
                       help="0% = mínima, 100% = máxima dos últimos 5 anos.")

            st.caption(
                f"Se voltar à **mínima 5a** (R$ {d['minima_5a']:,.2f}): "
                f"queda de {d['dist_min_pct']:.1f}%. "
                f"Se voltar à **máxima 5a** (R$ {d['maxima_5a']:,.2f}): "
                f"alta de {d['dist_max_pct']:.1f}%. "
                f"Preço médio 5a: **R$ {d['media_5a']:,.2f}**."
            )

init_db()

st.title("👔 Assessor de Investimentos")
st.caption(
    "Converse com o **Ricardo** — assessor sênior com equipe multi-mercado "
    "(BR, EUA, China, Europa). Foco em longo prazo."
)
st.info(DISCLAIMER)

# ---------------------------------------------------------------------------
# Seletor de sessão + histórico visível
# ---------------------------------------------------------------------------
consultas = listar_consultas()

# Session state para lembrar qual sessão está ativa (mesmo entre reruns).
if "consulta_atual" not in st.session_state:
    st.session_state["consulta_atual"] = None  # None = nova consulta

# --- Histórico de sessões (bem visível) ------------------------------------
if consultas:
    with st.expander(f"📚 Histórico de consultas ({len(consultas)})",
                     expanded=st.session_state["consulta_atual"] is None):
        st.caption(
            "Toda conversa fica **salva automaticamente**. Clique em uma "
            "consulta para **retomar do ponto onde parou**, ou use "
            "**'Nova consulta usando esta como base'** para começar uma nova "
            "aplicação com o histórico como contexto."
        )
        for c in consultas:
            with st.container(border=True):
                col_info, col_open, col_del = st.columns([4, 1, 1])
                with col_info:
                    st.markdown(f"**{c['titulo']}**")
                    detalhes = [c["criada_em"].strftime("%d/%m/%Y %H:%M"),
                                f"{c['n_mensagens']} mensagens"]
                    if c["valor_investir"]:
                        detalhes.append(f"aporte R$ {c['valor_investir']:,.2f}")
                    st.caption(" · ".join(detalhes))
                    if c["preview"]:
                        st.caption(f"↳ _{c['preview']}..._")
                with col_open:
                    st.write("")
                    if st.button("Abrir", key=f"open_{c['id']}"):
                        st.session_state["consulta_atual"] = c["id"]
                        st.rerun()
                with col_del:
                    st.write("")
                    if st.button("🗑️", key=f"del_{c['id']}",
                                 help="Excluir esta consulta"):
                        excluir_consulta(c["id"])
                        if st.session_state["consulta_atual"] == c["id"]:
                            st.session_state["consulta_atual"] = None
                        st.rerun()

    if st.button("➕ Nova consulta", type="primary" if st.session_state["consulta_atual"] else "secondary"):
        st.session_state["consulta_atual"] = None
        st.rerun()

# ---------------------------------------------------------------------------
# Nova consulta (do zero)
# ---------------------------------------------------------------------------
if st.session_state["consulta_atual"] is None:
    st.subheader("Nova consulta ao assessor")

    contexto = montar_contexto_carteira()
    with st.expander("📊 Contexto que o Ricardo vai receber (sua carteira atual)"):
        st.markdown(contexto)

    valor = st.number_input(
        "Quanto você quer investir agora? (R$)",
        min_value=0.0,
        step=500.0,
        format="%.2f",
        help="Aporte deste mês. Pode ficar em 0 se quiser só uma revisão da carteira.",
    )
    titulo = st.text_input(
        "Título da consulta (opcional)",
        placeholder="Ex.: Aporte de outubro/2026",
    )
    pergunta_inicial = st.text_area(
        "O que você quer discutir com o Ricardo?",
        value=(
            "Fiz um aporte novo este mês. Considerando minha carteira e o "
            "cenário macro global, para onde faz sentido alocar pensando "
            "em longo prazo (5-10 anos)?"
        ) if valor else (
            "Faça uma leitura da minha carteira: pontos fortes, concentrações "
            "e o que ajustar pensando em longo prazo."
        ),
        height=110,
    )

    if st.button("🎙️ Consultar o Ricardo", type="primary"):
        if not pergunta_inicial.strip():
            st.error("Escreva sua pergunta.")
        else:
            with st.spinner("Ricardo consultando a equipe e preparando a resposta..."):
                try:
                    cid = criar_consulta(
                        valor if valor > 0 else None,
                        contexto,
                        titulo or f"Aporte {datetime.now().strftime('%m/%Y')}",
                    )
                    resposta = conversar(
                        valor if valor > 0 else None,
                        contexto,
                        conversa=[],
                        nova_mensagem=pergunta_inicial.strip(),
                    )
                    salvar_conversa(cid, [
                        {"role": "user", "content": pergunta_inicial.strip()},
                        {"role": "assistant", "content": resposta},
                    ])
                    st.session_state["consulta_atual"] = cid
                    st.rerun()
                except Exception as e:
                    st.error(f"Falha ao consultar o assessor: {e}")

else:
    # -----------------------------------------------------------------------
    # Sessão existente: exibe conversa e permite continuar
    # -----------------------------------------------------------------------
    cid = st.session_state["consulta_atual"]
    dados = carregar_consulta(cid)
    if not dados:
        st.error("Consulta não encontrada.")
        st.session_state["consulta_atual"] = None
        st.stop()

    # Título editável
    c_tit, c_save = st.columns([4, 1])
    with c_tit:
        novo_titulo = st.text_input("Título", value=dados["titulo"],
                                      label_visibility="collapsed", key=f"tit_{cid}")
    with c_save:
        if st.button("💾 Renomear", key=f"ren_{cid}") and novo_titulo != dados["titulo"]:
            renomear_consulta(cid, novo_titulo)
            st.success("Renomeada.")
            st.rerun()

    if dados["valor_investir"]:
        st.caption(f"💰 Aporte desta consulta: R$ {dados['valor_investir']:,.2f} · "
                    f"Criada em {dados['criada_em'].strftime('%d/%m/%Y %H:%M')}")
    else:
        st.caption(f"Criada em {dados['criada_em'].strftime('%d/%m/%Y %H:%M')}")

    with st.expander("📊 Carteira usada como contexto"):
        st.markdown(dados["contexto_carteira"] or "_(sem contexto)_")

    # Botão "Nova consulta com base nesta"
    with st.expander("🔄 Nova consulta usando esta como base (Ricardo lembra do histórico)"):
        st.caption(
            "Cria uma nova sessão herdando o resumo da conversa atual. Ideal "
            "quando você vai fazer um **novo aporte** e quer que o Ricardo "
            "lembre do que já discutiram sem começar do zero."
        )
        n_valor = st.number_input(
            "Novo valor a investir (R$)",
            min_value=0.0, step=500.0, format="%.2f", key=f"nv_{cid}",
        )
        n_titulo = st.text_input(
            "Título da nova consulta",
            value=f"Continuação · {datetime.now().strftime('%m/%Y')}",
            key=f"nt_{cid}",
        )
        if st.button("🎙️ Abrir nova consulta com histórico", key=f"nb_{cid}"):
            novo_ctx = montar_contexto_carteira()
            novo_id = duplicar_como_base(
                cid, n_valor if n_valor > 0 else None, novo_ctx, n_titulo
            )
            if novo_id:
                st.session_state["consulta_atual"] = novo_id
                st.rerun()

    st.divider()

    # Exibe a conversa
    for i, msg in enumerate(dados["conversa"]):
        with st.chat_message("user" if msg["role"] == "user" else "assistant",
                             avatar="🧑" if msg["role"] == "user" else "👔"):
            st.markdown(msg["content"])
            # Se a mensagem do assessor tem bloco de tickers, renderiza a
            # análise técnica logo abaixo (só da última mensagem — evita
            # buscar dados de mercado toda vez que abre o histórico).
            if msg["role"] == "assistant" and i == len(dados["conversa"]) - 1:
                tks = extrair_tickers_da_resposta(msg["content"])
                if tks["principais"]:
                    renderizar_analise_tickers(tks["principais"],
                                                "Análise técnica das principais")
                if tks["reservas"]:
                    renderizar_analise_tickers(tks["reservas"],
                                                "Análise técnica das reservas")

    # Input para continuar
    nova = st.chat_input("Continue a conversa com o Ricardo — questione, peça detalhes, ajuste…")
    if nova:
        # Adiciona pergunta e chama modelo
        with st.chat_message("user", avatar="🧑"):
            st.markdown(nova)
        with st.chat_message("assistant", avatar="👔"):
            with st.spinner("Ricardo pensando..."):
                try:
                    resposta = conversar(
                        dados["valor_investir"],
                        dados["contexto_carteira"] or "",
                        conversa=dados["conversa"],
                        nova_mensagem=nova,
                    )
                    nova_conversa = dados["conversa"] + [
                        {"role": "user", "content": nova},
                        {"role": "assistant", "content": resposta},
                    ]
                    salvar_conversa(cid, nova_conversa)
                    st.rerun()  # rerun mostra a resposta + análise técnica
                except Exception as e:
                    st.error(f"Falha: {e}")

    st.divider()
    st.caption(DISCLAIMER)
