"""Movimentações — receitas, despesas e visão unificada em 3 sub-abas.

Cada aba com resumo, gráficos e lista dedicados.
"""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
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
    total_por_tipo,
)

init_db()

st.title("💰 Movimentações")
st.caption(
    "Todas as entradas e saídas do mês, organizadas por tipo. "
    "Transferências entre suas contas e aplicações **não** entram no fluxo real."
)

# ---------------------------------------------------------------------------
# Sincronização (uma vez): puxa faturas de cartão + tabelas antigas
# ---------------------------------------------------------------------------
with st.expander("🔄 Sincronizar dados existentes (cartão + dados antigos)"):
    st.write(
        "Cria movimentações a partir do que já está no banco: "
        "**transações de cartão** (das faturas importadas), **receitas** e "
        "**despesas manuais** de antes da reforma. É seguro clicar mais de "
        "uma vez — o sistema detecta duplicatas por (data + valor + descrição) "
        "e não recria."
    )
    st.warning(
        "⚠️ Depois de sincronizar, você pode ter **conflito** entre "
        "'Fatura Paga do Cartão' no extrato e as transações do cartão em si — "
        "escolha **um** dos dois na hora de manter (senão duplica o gasto)."
    )
    if st.button("🔄 Sincronizar agora"):
        from services.sincronizar import sincronizar_tudo
        with st.spinner("Sincronizando..."):
            resultado = sincronizar_tudo()
        total = sum(resultado.values())
        if total == 0:
            st.info("Nada novo para sincronizar (tudo já está migrado).")
        else:
            partes = [f"**{v}** de {k}" for k, v in resultado.items() if v > 0]
            st.success("✅ " + str(total) + " movimentação(ões) criadas: " + ", ".join(partes) + ".")
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
# Lista todos os meses que já têm movimentação + adiciona o mês atual + últimos 24 meses.
disponiveis = set(meses_disponiveis()) | {padrao}
# Preenche 24 meses retroativos para o usuário sempre ter opções.
for i in range(24):
    m = hoje.month - i
    y = hoje.year
    while m <= 0:
        m += 12
        y -= 1
    disponiveis.add(f"{y:04d}-{m:02d}")
meses_lista = sorted(disponiveis, reverse=True)

# Estado inicial
if "mov_mes" not in st.session_state:
    st.session_state["mov_mes"] = padrao if padrao in meses_lista else meses_lista[0]

# Navegação: ← [dropdown] →
col_a, col_b, col_c = st.columns([1, 4, 1])
with col_a:
    idx_atual = meses_lista.index(st.session_state["mov_mes"]) if st.session_state["mov_mes"] in meses_lista else 0
    if st.button("◀ Mês anterior", disabled=idx_atual >= len(meses_lista) - 1):
        st.session_state["mov_mes"] = meses_lista[idx_atual + 1]
        st.rerun()
with col_b:
    escolhido = st.selectbox(
        "Mês de referência",
        meses_lista,
        index=idx_atual,
        format_func=_rotulo,
        key="mov_mes_select",
        label_visibility="collapsed",
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
# Resumo no topo (sempre visível)
# ---------------------------------------------------------------------------
r = resumo_mes(mes_ref)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Recebido", f"R$ {r['receitas']:,.2f}")
c2.metric("Gasto (real)", f"R$ {r['despesas']:,.2f}",
          help="Exclui LUMAI e transferências.")
c3.metric("Aplicado", f"R$ {r['aplicacoes']:,.2f}",
          help="Enviado para contas de aplicação (BTG etc.).")
c4.metric("Saldo do mês", f"R$ {r['saldo']:,.2f}",
          help="Recebido − Gasto − Aplicado + Resgates.")

lumai_pend = total_lumai_a_reembolsar(mes_ref)
if lumai_pend:
    st.info(f"💼 R$ {lumai_pend:,.2f} em despesas LUMAI a reembolsar (não contam no gasto).")

st.divider()

# ---------------------------------------------------------------------------
# Formulário de nova movimentação (compartilhado entre as abas)
# ---------------------------------------------------------------------------
categorias = [c["nome"] for c in listar_categorias()]
contas = listar_contas()
opcoes_conta = {"(nenhuma)": None, **{c["apelido"]: c["id"] for c in contas}}

with st.expander("➕ Adicionar movimentação"):
    with st.form("nova_mov", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            data_ = st.date_input("Data", value=date.today(), format="DD/MM/YYYY")
            descricao = st.text_input("Descrição", placeholder="Ex.: Mercado, Salário, PIX Maria")
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
# 3 abas: Receitas / Despesas / Movimentações (tudo)
# ---------------------------------------------------------------------------
aba_rec, aba_desp, aba_todas = st.tabs(["💵 Receitas", "💸 Despesas", "📋 Todas as movimentações"])


def _formatar_df(df: pd.DataFrame) -> pd.DataFrame:
    """Formata colunas comuns para exibição."""
    dv = df.copy()
    dv["data"] = dv["data"].apply(lambda d: d.strftime("%d/%m/%Y"))
    dv["valor"] = dv["valor"].apply(lambda v: f"R$ {v:,.2f}")
    if "lumai" in dv.columns:
        dv["lumai"] = dv["lumai"].map({True: "✅", False: ""})
    return dv


# ---------- Aba Receitas ---------------------------------------------------
with aba_rec:
    st.subheader(f"Receitas em {_rotulo(mes_ref)}")
    receitas = listar(mes_referencia=mes_ref, tipos=["receita"])
    total_rec = sum(m["valor"] for m in receitas)
    resgates = listar(mes_referencia=mes_ref, tipos=["resgate"])
    total_res = sum(m["valor"] for m in resgates)

    m1, m2, m3 = st.columns(3)
    m1.metric("Total recebido", f"R$ {total_rec:,.2f}")
    m2.metric("Resgates de aplicação", f"R$ {total_res:,.2f}")
    m3.metric("Nº de entradas", len(receitas) + len(resgates))

    if not receitas and not resgates:
        st.info("Sem receitas ou resgates neste mês.")
    else:
        # Gráfico 1: evolução diária das receitas
        st.markdown("**📈 Evolução das entradas ao longo do mês**")
        rec_dia = por_dia(mes_ref, tipo="receita")
        if rec_dia:
            df_dia = pd.DataFrame(rec_dia).set_index("data")
            st.bar_chart(df_dia)
        else:
            st.caption("Sem dados diários.")

        # Gráfico 2: top fontes de receita
        st.markdown("**🏆 Top fontes de receita**")
        fontes = por_fonte(mes_ref, tipo="receita")
        if fontes:
            df_f = pd.DataFrame(fontes[:10]).set_index("fonte")
            st.bar_chart(df_f)
            with st.expander("Ver detalhado por fonte"):
                df_show = pd.DataFrame(fontes)
                df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
                df_show.columns = ["Fonte", "Total"]
                st.dataframe(df_show, use_container_width=True, hide_index=True)

        # Lista completa
        st.markdown("**Lista de entradas**")
        todas_entradas = receitas + resgates
        todas_entradas.sort(key=lambda x: x["data"], reverse=True)
        df = pd.DataFrame(todas_entradas)
        dv = _formatar_df(df[["data", "descricao", "tipo", "categoria", "valor", "origem"]])
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

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Gasto real (você)", f"R$ {total_desp:,.2f}",
              help="Só despesas suas, exclui LUMAI.")
    m2.metric("Despesas LUMAI", f"R$ {total_lumai:,.2f}",
              help="A serem reembolsadas — não contam no seu gasto.")
    m3.metric("Total lançado", f"R$ {total_desp + total_lumai:,.2f}")
    m4.metric("Nº de despesas", len(despesas))

    if not despesas:
        st.info("Sem despesas neste mês.")
    else:
        # Gráfico 1: gasto por categoria
        st.markdown("**📊 Gasto por categoria** (excluindo LUMAI)")
        cats = por_categoria(mes_ref, tipo="despesa", excluir_lumai=True)
        if cats:
            df_c = pd.DataFrame(cats).set_index("categoria")
            col_g, col_t = st.columns([2, 1])
            with col_g:
                st.bar_chart(df_c)
            with col_t:
                df_show = pd.DataFrame(cats)
                df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
                df_show.columns = ["Categoria", "Total"]
                st.dataframe(df_show, use_container_width=True, hide_index=True)

        # Gráfico 2: evolução diária
        st.markdown("**📈 Evolução dos gastos ao longo do mês**")
        desp_dia = por_dia(mes_ref, tipo="despesa", excluir_lumai=True)
        if desp_dia:
            df_dia = pd.DataFrame(desp_dia).set_index("data")
            st.bar_chart(df_dia)

        # Lista completa
        st.markdown("**Lista de despesas**")
        df = pd.DataFrame(despesas)
        dv = _formatar_df(df[["data", "descricao", "categoria", "forma", "valor", "lumai", "origem"]])
        dv.columns = ["Data", "Descrição", "Categoria", "Forma", "Valor", "LUMAI", "Origem"]
        st.dataframe(dv, use_container_width=True, hide_index=True)


# ---------- Aba Todas -----------------------------------------------------
with aba_todas:
    st.subheader(f"Todas as movimentações em {_rotulo(mes_ref)}")

    filtros = st.multiselect(
        "Filtrar por tipo",
        TIPOS,
        default=["receita", "despesa", "aplicacao", "resgate"],
        help="Transferências ficam ocultas por padrão (não afetam o fluxo).",
    )
    movs = listar(mes_referencia=mes_ref, tipos=filtros)
    if not movs:
        st.info("Sem movimentações neste filtro.")
    else:
        # Resumo do que está filtrado
        entradas = sum(m["valor"] for m in movs if m["tipo"] in ("receita", "resgate"))
        saidas = sum(m["valor"] for m in movs if m["tipo"] in ("despesa", "aplicacao") and not m["lumai"])
        st.write(f"**{len(movs)} movimentações** · Entradas: R$ {entradas:,.2f} · Saídas: R$ {saidas:,.2f}")

        df = pd.DataFrame(movs)
        dv = _formatar_df(df[["data", "descricao", "tipo", "categoria", "forma", "valor", "lumai", "origem"]])
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
