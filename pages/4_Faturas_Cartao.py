"""Tela de Faturas de Cartão (Fase 3): upload, importação e revisão manual."""
from datetime import date

import pandas as pd
import streamlit as st

from core.db import init_db
from core.ui import aplicar_estilo
from services.cartao import (
    adicionar_categoria,
    atualizar_mes_referencia,
    comprovante_fatura,
    desfazer_reembolso_fatura,
    detectar_banco,
    excluir_categoria,
    excluir_fatura,
    gasto_por_categoria_fatura,
    importar_fatura,
    listar_categorias,
    listar_faturas,
    listar_transacoes,
    marcar_fatura_reembolsada,
    previsualizar,
    registrar_pagamento_fatura,
    remover_pagamento_fatura,
    renomear_categoria,
    reembolso_lumai_por_fatura,
    salvar_revisao,
    salvar_upload,
    total_lumai_fatura,
)

init_db()
aplicar_estilo()

st.title("Faturas de Cartão")
st.caption("Envie o PDF da fatura. O sistema extrai as transações e sugere categorias para você revisar.")

# ---------------------------------------------------------------------------
# 1) Upload e importação
# ---------------------------------------------------------------------------
st.subheader("1. Importar fatura (PDF)")
arquivo = st.file_uploader("Selecione o PDF da fatura", type=["pdf"])

if arquivo is not None:
    if "upload_path" not in st.session_state or st.session_state.get("upload_nome") != arquivo.name:
        caminho = salvar_upload(arquivo.name, arquivo.getvalue())
        st.session_state["upload_path"] = caminho
        st.session_state["upload_nome"] = arquivo.name

    caminho = st.session_state["upload_path"]
    banco = detectar_banco(caminho)
    st.info(f"Banco detectado: **{banco}**")

    prev = previsualizar(caminho)
    if not prev["transacoes"]:
        st.warning("Nenhuma transação reconhecida neste PDF. O layout pode ser diferente — me avise para ajustar o parser.")
    else:
        df_prev = pd.DataFrame(prev["transacoes"])
        st.write(
            f"**{len(df_prev)}** transações · total R$ {df_prev['valor'].sum():,.2f} · "
            f"vencimento {prev['vencimento'] or '—'}"
        )
        st.dataframe(df_prev, use_container_width=True, hide_index=True)

        # Competência sugerida = mês anterior ao vencimento (fatura que vence em
        # junho é a fatura de maio).
        venc = prev.get("vencimento")
        if venc:
            ano, mes = (venc.year, venc.month - 1)
            if mes == 0:
                ano, mes = ano - 1, 12
            default_mes = f"{ano:04d}-{mes:02d}"
        else:
            default_mes = prev["mes_referencia"] or ""

        col1, col2 = st.columns([1, 2])
        with col1:
            mes_ref = st.text_input(
                "Mês de competência (AAAA-MM)",
                value=default_mes,
                help="Mês anterior ao vencimento. Ex.: fatura que vence em junho → maio.",
            )
        with col2:
            st.write("")
            st.write("")
            if st.button("Importar fatura", type="primary"):
                fid = importar_fatura(caminho, mes_referencia=mes_ref or None)
                st.success(f"Fatura importada (#{fid}). Revise as categorias abaixo.")
                for k in ("upload_path", "upload_nome"):
                    st.session_state.pop(k, None)
                st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# 2) Faturas importadas + revisão
# ---------------------------------------------------------------------------
st.subheader("2. Faturas importadas")
faturas = listar_faturas()
if not faturas:
    st.info("Nenhuma fatura importada ainda.")
    st.stop()

df_fat = pd.DataFrame(faturas)
df_fat_view = df_fat[["id", "banco", "mes_referencia", "transacoes", "total", "pendentes_revisao"]].copy()
df_fat_view["status"] = df_fat["fechada"].map(lambda x: "✅ Fechada" if x else "🟡 Em aberto")
df_fat_view.columns = ["#", "Banco", "Mês ref.", "Transações", "Total (R$)", "Pendentes", "Status"]
st.dataframe(df_fat_view, use_container_width=True, hide_index=True)

opcoes = {f"#{f['id']} — {f['banco']} · {f['mes_referencia']} · R$ {f['total']:,.2f}": f["id"] for f in faturas}
escolha = st.selectbox("Selecione uma fatura para revisar", list(opcoes.keys()))
fatura_id = opcoes[escolha]

mes_ref_atual = next((f["mes_referencia"] for f in faturas if f["id"] == fatura_id), "") or ""
col_a, col_b, col_c = st.columns([2, 1, 1])
with col_a:
    novo_mes = st.text_input(
        "Mês de competência desta fatura (AAAA-MM)",
        value=mes_ref_atual,
        help="Rótulo organizador. O gasto no painel é contado pela data de cada compra.",
    )
with col_b:
    st.write("")
    st.write("")
    if st.button("Salvar mês") and novo_mes != mes_ref_atual:
        atualizar_mes_referencia(fatura_id, novo_mes)
        st.success("Mês atualizado.")
        st.rerun()
with col_c:
    st.write("")
    st.write("")
    if st.button("Excluir fatura", type="secondary"):
        excluir_fatura(fatura_id)
        st.rerun()

# --- Validação / fechamento da fatura -------------------------------------
fat_sel = next((f for f in faturas if f["id"] == fatura_id), None)
if fat_sel:
    with st.container(border=True):
        st.markdown("### 🧾 Fechamento da fatura")
        if fat_sel["fechada"]:
            st.success(
                f"✅ **Fatura fechada** — paga em "
                f"{fat_sel['data_pagamento'].strftime('%d/%m/%Y') if fat_sel['data_pagamento'] else '—'} · "
                f"valor pago R$ {(fat_sel['valor_pago'] or 0):,.2f}"
            )
            # Validação do valor pago vs total da fatura.
            if fat_sel["confere"]:
                st.caption(f"💯 O valor pago confere com o total da fatura (R$ {fat_sel['total']:,.2f}).")
            elif fat_sel["diferenca"] is not None:
                d = fat_sel["diferenca"]
                sinal = "a mais" if d > 0 else "a menos"
                st.warning(
                    f"⚠️ O valor pago difere do total da fatura em **R$ {abs(d):,.2f}** ({sinal}). "
                    f"Total da fatura: R$ {fat_sel['total']:,.2f}."
                )
            v1, v2 = st.columns(2)
            with v1:
                if fat_sel["tem_comprovante"]:
                    nome, dados = comprovante_fatura(fatura_id)
                    st.download_button(
                        "📎 Baixar comprovante",
                        data=dados,
                        file_name=nome or f"comprovante_fatura_{fatura_id}",
                    )
            with v2:
                if st.button("Reabrir fatura (desfazer)", type="secondary"):
                    remover_pagamento_fatura(fatura_id)
                    st.rerun()
        else:
            st.caption("Anexe o comprovante de pagamento para confirmar que a fatura fechou.")
            with st.form(f"pagar_fatura_{fatura_id}"):
                pf1, pf2 = st.columns(2)
                with pf1:
                    data_pag = st.date_input("Data do pagamento", value=date.today(), format="DD/MM/YYYY")
                with pf2:
                    valor_pago = st.number_input(
                        "Valor pago (R$)",
                        min_value=0.0,
                        value=float(fat_sel["total"]),
                        step=10.0,
                        format="%.2f",
                        help=f"Total da fatura: R$ {fat_sel['total']:,.2f}. O sistema confere se bate.",
                    )
                comprovante = st.file_uploader(
                    "Comprovante de pagamento (PDF ou imagem)", type=["pdf", "png", "jpg", "jpeg"]
                )
                confirmar = st.form_submit_button("Confirmar pagamento e fechar fatura", type="primary")
                if confirmar:
                    if comprovante is None:
                        st.error("Anexe o comprovante para fechar a fatura.")
                    else:
                        registrar_pagamento_fatura(
                            fatura_id,
                            data_pagamento=data_pag,
                            valor_pago=float(valor_pago),
                            comprovante_nome=comprovante.name,
                            comprovante_dados=comprovante.getvalue(),
                        )
                        st.success("Fatura fechada e comprovante anexado!")
                        st.rerun()

# --- Gerenciar categorias --------------------------------------------------
with st.expander("🏷️ Gerenciar categorias (criar, renomear, excluir)"):
    categorias_atuais = [c["nome"] for c in listar_categorias()]

    cg1, cg2 = st.columns(2)
    with cg1:
        nova_cat = st.text_input("Nova categoria", key="nova_cat", placeholder="Ex.: Pets, Educação")
        if st.button("Criar categoria"):
            if adicionar_categoria(nova_cat):
                st.success(f"Categoria '{nova_cat}' criada.")
                st.rerun()
            else:
                st.warning("Nome vazio ou categoria já existe.")
    with cg2:
        alvo = st.selectbox("Categoria existente", categorias_atuais, key="cat_alvo")
        novo_nome = st.text_input("Renomear para", key="cat_novo_nome", placeholder="Novo nome")
        ra1, ra2 = st.columns(2)
        with ra1:
            if st.button("Renomear"):
                if renomear_categoria(alvo, novo_nome):
                    st.success(f"'{alvo}' → '{novo_nome}'.")
                    st.rerun()
                else:
                    st.warning("Nome inválido ou já existente.")
        with ra2:
            if st.button("Excluir", key="del_cat"):
                excluir_categoria(alvo)
                st.success(f"Categoria '{alvo}' excluída (transações ficaram sem categoria).")
                st.rerun()

# Revisão das categorias e marcação LUMAI com data_editor.
st.subheader("3. Revisar categorias e marcar LUMAI")
st.caption("Marque ✅ na coluna **LUMAI** as despesas da empresa a reembolsar. Edite a categoria pelo menu.")
transacoes = listar_transacoes(fatura_id)
categorias = [c["nome"] for c in listar_categorias()]

df_tx = pd.DataFrame(transacoes)
edit = st.data_editor(
    df_tx,
    use_container_width=True,
    hide_index=True,
    disabled=["id", "data", "descricao", "valor"],
    column_config={
        "id": None,
        "reembolsado_em": None,
        "data": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
        "descricao": st.column_config.TextColumn("Descrição", width="large"),
        "valor": st.column_config.NumberColumn("Valor (R$)", format="%.2f"),
        "categoria": st.column_config.SelectboxColumn("Categoria", options=categorias, required=True),
        "lumai": st.column_config.CheckboxColumn("LUMAI", help="Despesa da empresa, a reembolsar."),
        "reembolsado": st.column_config.CheckboxColumn(
            "Reembolsado",
            help="Marque quando a LUMAI já pagou o reembolso — o item sai do relatório.",
        ),
        "revisado": st.column_config.CheckboxColumn("Revisado"),
    },
    key=f"editor_{fatura_id}",
)

if st.button("Salvar revisão", type="primary"):
    alteracoes = edit[["id", "categoria", "lumai", "reembolsado", "revisado"]].to_dict("records")
    salvar_revisao(alteracoes)
    st.success("Revisão salva.")
    st.rerun()

# --- Visão LUMAI desta fatura (pintada) -----------------------------------
lumai_rows = edit[edit["lumai"] == True]  # noqa: E712
total_lumai = total_lumai_fatura(fatura_id)
st.metric(
    "💼 Total LUMAI nesta fatura (a reembolsar)",
    f"R$ {total_lumai:,.2f}",
    help="Soma das transações marcadas como LUMAI (conforme a última revisão salva).",
)
if not lumai_rows.empty:
    st.caption("Itens marcados como LUMAI nesta fatura (não salvos ainda aparecem ao salvar a revisão):")
    df_lumai = lumai_rows[["data", "descricao", "categoria", "valor"]].copy()

    def _pinta(_):
        return ["background-color: #fff3cd"] * 4  # amarelo suave

    styler = df_lumai.style.apply(_pinta, axis=1).format({"valor": "R$ {:,.2f}"})
    st.dataframe(styler, use_container_width=True, hide_index=True)

# Resumo por categoria desta fatura (a fatura inteira, não o mês-calendário).
st.subheader("Gasto por categoria (desta fatura)")
por_cat = gasto_por_categoria_fatura(fatura_id)
if por_cat:
    df_cat = pd.DataFrame(por_cat).set_index("categoria")
    st.bar_chart(df_cat)

# --- Reembolso LUMAI consolidado por fatura -------------------------------
st.divider()
st.subheader("💼 Reembolso LUMAI por fatura")
st.caption("Só entram aqui as despesas LUMAI que **ainda não foram reembolsadas**.")
reembolsos = reembolso_lumai_por_fatura()
if reembolsos:
    df_re = pd.DataFrame(reembolsos)
    total_geral = df_re["total"].sum()
    df_show = df_re[["banco", "mes_referencia", "itens", "total"]].copy()
    df_show["total"] = df_show["total"].apply(lambda v: f"R$ {v:,.2f}")
    df_show.columns = ["Banco", "Mês ref.", "Itens", "Total a reembolsar"]
    st.dataframe(df_show, use_container_width=True, hide_index=True)
    st.metric("Total LUMAI em todas as faturas", f"R$ {total_geral:,.2f}")

    # --- Marcar fatura inteira como reembolsada --------------------------
    st.markdown("**✅ Já recebeu o reembolso de uma fatura?**")
    op_re = {
        f"#{r['fatura_id']} · {r['banco']} · {r['mes_referencia']} · R$ {r['total']:,.2f}": r["fatura_id"]
        for r in reembolsos
    }
    sel_re = st.selectbox("Fatura", list(op_re.keys()), key="mark_reemb")
    if st.button("Marcar todos os itens LUMAI desta fatura como reembolsados"):
        n = marcar_fatura_reembolsada(op_re[sel_re])
        st.success(f"{n} item(ns) marcado(s) como reembolsado(s). Sairam do relatório.")
        for k in ("lumai_xlsx", "lumai_pdf"):
            st.session_state.pop(k, None)
        st.rerun()

    # --- Exportar relatório de reembolso (Excel / PDF) --------------------
    st.markdown("**Baixar relatório para reembolso:**")
    if st.button("Gerar relatório de reembolso"):
        from services.relatorios import gerar_excel_lumai, gerar_pdf_lumai

        with st.spinner("Gerando arquivos..."):
            st.session_state["lumai_xlsx"] = gerar_excel_lumai()
            st.session_state["lumai_pdf"] = gerar_pdf_lumai()

    if st.session_state.get("lumai_xlsx") and st.session_state.get("lumai_pdf"):
        carimbo = date.today().strftime("%Y-%m-%d")
        bx, bp = st.columns(2)
        with bx:
            st.download_button(
                "📥 Baixar Excel (.xlsx)",
                data=st.session_state["lumai_xlsx"],
                file_name=f"reembolso_lumai_{carimbo}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        with bp:
            st.download_button(
                "📄 Baixar PDF",
                data=st.session_state["lumai_pdf"],
                file_name=f"reembolso_lumai_{carimbo}.pdf",
                mime="application/pdf",
            )
        st.caption("O Excel abre com as colunas separadas; o PDF vem detalhado e organizado por origem.")
else:
    st.caption("Nenhuma transação LUMAI a reembolsar no momento.")

# --- Reembolsos já pagos (histórico) --------------------------------------
pagos = reembolso_lumai_por_fatura(incluir_pagos=True)
pagos_filtrados = []
for p in pagos:
    a_pagar = next((r for r in reembolso_lumai_por_fatura() if r["fatura_id"] == p["fatura_id"]), None)
    if a_pagar is None:  # todos os itens LUMAI dessa fatura já foram pagos
        pagos_filtrados.append(p)
if pagos_filtrados:
    with st.expander(f"✅ Reembolsos já pagos ({len(pagos_filtrados)} fatura(s))"):
        st.caption("Se marcou por engano, dá pra reabrir aqui.")
        for p in pagos_filtrados:
            col1, col2 = st.columns([4, 1])
            with col1:
                st.write(f"#{p['fatura_id']} · {p['banco']} · {p['mes_referencia']} · **R$ {p['total']:,.2f}** · {p['itens']} item(ns)")
            with col2:
                if st.button("↩️ Reabrir", key=f"reab_{p['fatura_id']}"):
                    n = desfazer_reembolso_fatura(p["fatura_id"])
                    st.success(f"{n} item(ns) voltaram para o relatório.")
                    st.rerun()
