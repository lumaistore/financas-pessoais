"""Relatórios de reembolso LUMAI em Excel (.xlsx) e PDF.

Reúne todas as despesas marcadas como LUMAI (faturas de cartão + despesas
manuais) com detalhe — para você enviar à empresa e receber o reembolso.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import List

import pandas as pd
from sqlalchemy import select

from core.db import get_session
from core.models import Fatura
from services.movimentacoes import listar as _listar_movs


def listar_despesas():
    """Wrapper compat: retorna despesas LUMAI para o relatório."""
    return [
        {**m, "reembolsado": m["reembolsado"]}
        for m in _listar_movs()
        if m["tipo"] == "despesa" and m["lumai"]
    ]


def itens_lumai(incluir_pagos: bool = False) -> List[dict]:
    """Despesas LUMAI ainda a reembolsar (não pagas por padrão), com detalhe.
    Passe `incluir_pagos=True` para relatório histórico completo."""
    itens: List[dict] = []
    with get_session() as s:
        for f in s.scalars(select(Fatura)).all():
            origem = f"Cartão {f.banco or '—'} · fatura {f.mes_referencia or '—'}"
            for t in f.transacoes:
                if not t.lumai:
                    continue
                if not incluir_pagos and t.reembolsado_em is not None:
                    continue
                itens.append(
                    {
                        "origem": origem,
                        "data": t.data,
                        "descricao": t.descricao,
                        "categoria": t.categoria.nome if t.categoria else "Outros",
                        "valor": float(t.valor),
                    }
                )
    for d in listar_despesas():
        if not d.get("lumai"):
            continue
        if not incluir_pagos and d.get("reembolsado"):
            continue
        itens.append(
            {
                "origem": f"Despesa avulsa ({d['forma']})",
                "data": d["data"],
                "descricao": d["descricao"],
                "categoria": d["categoria"],
                "valor": float(d["valor"]),
            }
        )
    itens.sort(key=lambda x: (x["origem"], x["data"]))
    return itens


def resumo_por_origem(itens: List[dict]) -> List[dict]:
    acc: dict = {}
    for it in itens:
        a = acc.setdefault(it["origem"], {"origem": it["origem"], "itens": 0, "total": 0.0})
        a["itens"] += 1
        a["total"] += it["valor"]
    return sorted(acc.values(), key=lambda x: x["origem"])


def _brl(v: float) -> str:
    return f"R$ {v:,.2f}"


# ---------------------------------------------------------------------------
# Excel
# ---------------------------------------------------------------------------
def gerar_excel_lumai() -> bytes:
    """.xlsx com colunas separadas (abre certo no Excel), detalhe + total."""
    itens = itens_lumai()
    df = pd.DataFrame(itens)
    if df.empty:
        df = pd.DataFrame(columns=["origem", "data", "descricao", "categoria", "valor"])
    df = df[["data", "descricao", "categoria", "origem", "valor"]]
    df.columns = ["Data", "Descrição", "Categoria", "Origem", "Valor (R$)"]

    total = float(df["Valor (R$)"].sum()) if not df.empty else 0.0

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Reembolso LUMAI", startrow=1)
        ws = writer.sheets["Reembolso LUMAI"]
        ws["A1"] = f"Reembolso LUMAI — gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')}"
        # Linha de total no fim.
        ultima = len(df) + 3
        ws.cell(row=ultima, column=4, value="TOTAL A REEMBOLSAR")
        ws.cell(row=ultima, column=5, value=total)
        # Formato de moeda na coluna de valor e largura das colunas.
        for row in ws.iter_rows(min_row=3, min_col=5, max_col=5):
            for cell in row:
                cell.number_format = "#,##0.00"
        larguras = {"A": 12, "B": 42, "C": 16, "D": 30, "E": 14}
        for col, w in larguras.items():
            ws.column_dimensions[col].width = w
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# PDF
# ---------------------------------------------------------------------------
def gerar_pdf_lumai() -> bytes:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.platypus import (
        Paragraph,
        SimpleDocTemplate,
        Spacer,
        Table,
        TableStyle,
    )

    itens = itens_lumai()
    total = sum(it["valor"] for it in itens)
    resumo = resumo_por_origem(itens)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        rightMargin=1.5 * cm,
        title="Relatório de Reembolso LUMAI",
    )
    estilos = getSampleStyleSheet()
    estilo_cel = ParagraphStyle("cel", parent=estilos["Normal"], fontSize=8, leading=10)
    estilo_cab = ParagraphStyle("cab", parent=estilos["Normal"], fontSize=8, leading=10, textColor=colors.white)
    azul = colors.HexColor("#1f4e79")

    elementos = []
    elementos.append(Paragraph("Relatório de Reembolso — LUMAI", estilos["Title"]))
    elementos.append(
        Paragraph(
            f"Gerado em {datetime.now().strftime('%d/%m/%Y %H:%M')} · "
            f"{len(itens)} despesa(s)",
            estilos["Normal"],
        )
    )
    elementos.append(Spacer(1, 0.3 * cm))
    elementos.append(
        Paragraph(f"<b>TOTAL A REEMBOLSAR: {_brl(total)}</b>", estilos["Heading2"])
    )
    elementos.append(Spacer(1, 0.5 * cm))

    # --- Resumo por origem ---
    elementos.append(Paragraph("Resumo por origem", estilos["Heading3"]))
    dados_resumo = [[Paragraph("<b>Origem</b>", estilo_cab),
                     Paragraph("<b>Itens</b>", estilo_cab),
                     Paragraph("<b>Subtotal</b>", estilo_cab)]]
    for r in resumo:
        dados_resumo.append([
            Paragraph(r["origem"], estilo_cel),
            Paragraph(str(r["itens"]), estilo_cel),
            Paragraph(_brl(r["total"]), estilo_cel),
        ])
    t_resumo = Table(dados_resumo, colWidths=[11 * cm, 2 * cm, 4 * cm])
    t_resumo.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f2f2f2")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
    ]))
    elementos.append(t_resumo)
    elementos.append(Spacer(1, 0.6 * cm))

    # --- Detalhamento ---
    elementos.append(Paragraph("Detalhamento das despesas", estilos["Heading3"]))
    dados = [[Paragraph("<b>Data</b>", estilo_cab),
              Paragraph("<b>Descrição</b>", estilo_cab),
              Paragraph("<b>Categoria</b>", estilo_cab),
              Paragraph("<b>Origem</b>", estilo_cab),
              Paragraph("<b>Valor</b>", estilo_cab)]]
    for it in itens:
        dados.append([
            Paragraph(it["data"].strftime("%d/%m/%Y"), estilo_cel),
            Paragraph(it["descricao"], estilo_cel),
            Paragraph(it["categoria"], estilo_cel),
            Paragraph(it["origem"], estilo_cel),
            Paragraph(_brl(it["valor"]), estilo_cel),
        ])
    dados.append([Paragraph("", estilo_cel), Paragraph("", estilo_cel),
                  Paragraph("", estilo_cel), Paragraph("<b>TOTAL</b>", estilo_cel),
                  Paragraph(f"<b>{_brl(total)}</b>", estilo_cel)])
    t = Table(dados, colWidths=[2.2 * cm, 6.3 * cm, 2.8 * cm, 4 * cm, 2.5 * cm], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), azul),
        ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
        ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#f2f2f2")]),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#dce6f1")),
    ]))
    elementos.append(t)

    doc.build(elementos)
    return buffer.getvalue()
