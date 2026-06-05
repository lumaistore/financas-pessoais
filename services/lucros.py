"""Retirada de Lucros — recibo de distribuição de lucros (geração + controle).

Gera o recibo já preenchido (só falta assinar), guarda cada retirada (gerada
ou anexada) e soma o total distribuído. Os dados fixos (empresa, CNPJ,
beneficiário, CPF, cidade) ficam numa configuração única.
"""
from __future__ import annotations

import io
from datetime import date, datetime
from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import RetiradaLucro, RetiradaLucroConfig

MESES = [
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
]


# ---------------------------------------------------------------------------
# Configuração (dados fixos)
# ---------------------------------------------------------------------------
def get_config() -> dict:
    with get_session() as s:
        c = s.scalar(select(RetiradaLucroConfig).limit(1))
        if not c:
            return {"empresa": "", "cnpj": "", "beneficiario": "", "cpf": "", "cidade": ""}
        return {
            "empresa": c.empresa or "",
            "cnpj": c.cnpj or "",
            "beneficiario": c.beneficiario or "",
            "cpf": c.cpf or "",
            "cidade": c.cidade or "",
        }


def salvar_config(empresa: str, cnpj: str, beneficiario: str, cpf: str, cidade: str) -> None:
    with get_session() as s:
        c = s.scalar(select(RetiradaLucroConfig).limit(1))
        if not c:
            c = RetiradaLucroConfig()
            s.add(c)
        c.empresa = empresa.strip()
        c.cnpj = cnpj.strip()
        c.beneficiario = beneficiario.strip()
        c.cpf = cpf.strip()
        c.cidade = cidade.strip()


def config_completa() -> bool:
    c = get_config()
    return all(c[k] for k in ("empresa", "cnpj", "beneficiario", "cpf"))


# ---------------------------------------------------------------------------
# Valor por extenso e datas
# ---------------------------------------------------------------------------
def valor_por_extenso(valor: float) -> str:
    try:
        from num2words import num2words

        return num2words(valor, lang="pt_BR", to="currency")
    except Exception:
        return ""


def _data_extenso(d: date) -> str:
    return f"{d.day:02d} de {MESES[d.month - 1]} de {d.year}"


def _brl(v: float) -> str:
    """Formata no padrão brasileiro: 12500.5 -> '12.500,50'."""
    return f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


# ---------------------------------------------------------------------------
# Geração do recibo em PDF
# ---------------------------------------------------------------------------
def gerar_recibo_pdf(data_dist: date, valor: float, config: Optional[dict] = None) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import cm
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

    cfg = config or get_config()
    extenso = valor_por_extenso(valor)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer, pagesize=A4,
        topMargin=2 * cm, bottomMargin=2 * cm, leftMargin=2.5 * cm, rightMargin=2.5 * cm,
        title="Recibo de Distribuição de Lucros",
    )
    estilos = getSampleStyleSheet()
    corpo = ParagraphStyle("corpo", parent=estilos["Normal"], fontSize=11, leading=18, spaceAfter=10)
    titulo = ParagraphStyle("tit", parent=estilos["Title"], fontSize=18, spaceAfter=24)

    e = []
    e.append(Paragraph("RECIBO DE DISTRIBUIÇÃO DE LUCROS", titulo))
    e.append(Paragraph(
        f"Declaro que recebi(emos) da empresa <b>{cfg['empresa']}</b>, "
        f"CNPJ nº <b>{cfg['cnpj']}</b>, a importância abaixo discriminada, "
        f"referente à Distribuição de Lucros, conforme legislação vigente:", corpo))
    e.append(Paragraph(
        f"<b>Data da distribuição:</b> {data_dist.strftime('%d/%m/%Y')}", corpo))
    e.append(Paragraph(
        f"<b>Valor distribuído:</b><br/>R$ {_brl(valor)}<br/>({extenso})", corpo))
    e.append(Spacer(1, 0.3 * cm))
    e.append(Paragraph(f"<b>Beneficiário:</b> {cfg['beneficiario']}", corpo))
    e.append(Paragraph(f"<b>CPF/CNPJ:</b> {cfg['cpf']}", corpo))
    e.append(Spacer(1, 0.2 * cm))
    e.append(Paragraph(
        "Declaro estar ciente de que a distribuição de lucros está sujeita às "
        "regras previstas na <b>Lei nº 15.270/2025</b>, em vigor a partir de "
        "<b>1º de janeiro de 2026</b>, especialmente no que se refere à "
        "tributação do <b>Imposto de Renda sobre lucros e dividendos</b>, quando "
        "aplicável, observados os limites e condições estabelecidos na "
        "legislação vigente.", corpo))
    e.append(Paragraph(
        "O presente recibo é emitido para fins de comprovação da distribuição "
        "de lucros, sendo de responsabilidade do beneficiário a veracidade das "
        "informações declaradas.", corpo))
    e.append(Spacer(1, 1 * cm))
    local = cfg["cidade"] or "____________________"
    e.append(Paragraph(f"Local e data: {local}, {_data_extenso(data_dist)}", corpo))
    e.append(Spacer(1, 1.2 * cm))
    e.append(Paragraph("Assinatura do beneficiário: ________________________________", corpo))
    e.append(Spacer(1, 0.4 * cm))
    e.append(Paragraph(f"Nome legível: {cfg['beneficiario']}", corpo))

    doc.build(e)
    return buffer.getvalue()


# ---------------------------------------------------------------------------
# Registros
# ---------------------------------------------------------------------------
def adicionar_retirada(
    data_dist: date,
    valor: float,
    arquivo_nome: Optional[str] = None,
    arquivo_dados: Optional[bytes] = None,
    observacao: Optional[str] = None,
) -> int:
    with get_session() as s:
        r = RetiradaLucro(
            data=data_dist,
            valor=float(valor),
            observacao=observacao,
            arquivo_nome=arquivo_nome,
            arquivo_dados=arquivo_dados,
        )
        s.add(r)
        s.flush()
        return r.id


def listar_retiradas() -> List[dict]:
    with get_session() as s:
        rs = s.scalars(select(RetiradaLucro).order_by(RetiradaLucro.data.desc())).all()
        return [
            {
                "id": r.id,
                "data": r.data,
                "valor": r.valor,
                "observacao": r.observacao,
                "tem_arquivo": r.arquivo_nome is not None,
                "arquivo_nome": r.arquivo_nome,
                "ano": r.data.year,
            }
            for r in rs
        ]


def excluir_retirada(retirada_id: int) -> None:
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if r:
            s.delete(r)


def arquivo_retirada(retirada_id: int):
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if not r or r.arquivo_dados is None:
            return None, None
        return r.arquivo_nome, r.arquivo_dados


def total_retiradas(ano: Optional[int] = None) -> float:
    return sum(r["valor"] for r in listar_retiradas() if ano is None or r["ano"] == ano)
