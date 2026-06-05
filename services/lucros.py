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


def _parse_valor(s: str) -> Optional[float]:
    """Converte texto de valor (BR '12.500,50' ou US '12,500.50') em float."""
    s = (s or "").strip().strip(".,")
    if not s:
        return None
    if "." in s and "," in s:
        if s.rfind(",") > s.rfind("."):  # vírgula é o decimal (BR)
            s = s.replace(".", "").replace(",", ".")
        else:  # ponto é o decimal (US)
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def ler_recibo_pdf(dados: bytes) -> dict:
    """Lê um PDF de recibo e tenta extrair {valor, data}. Vazio se não achar
    (ex.: PDF escaneado/imagem) — aí o usuário preenche à mão."""
    import re

    import pdfplumber

    texto = ""
    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pg in pdf.pages:
                texto += (pg.extract_text() or "") + "\n"
    except Exception:
        return {"valor": None, "data": None}

    data_val = None
    m = re.search(r"distribui[çc][ãa]o[:\s]*?(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})", texto, re.I)
    if not m:
        m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", texto)
    if m:
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if y < 100:
            y += 2000
        try:
            data_val = date(y, mo, d)
        except ValueError:
            data_val = None

    valor_val = None
    mv = re.search(r"R\$\s*([\d\.,]+)", texto)
    if mv:
        valor_val = _parse_valor(mv.group(1))
    return {"valor": valor_val, "data": data_val}


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


def registrar_assinado(retirada_id: int, nome: str, dados: bytes) -> None:
    """Anexa a versão assinada do recibo ao registro."""
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if r:
            r.assinado = True
            r.assinado_nome = nome
            r.assinado_dados = dados


def remover_assinado(retirada_id: int) -> None:
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if r:
            r.assinado = False
            r.assinado_nome = None
            r.assinado_dados = None


def atualizar_retirada(retirada_id: int, data_dist: date, valor: float, observacao: Optional[str]) -> None:
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if r:
            r.data = data_dist
            r.valor = float(valor)
            r.observacao = observacao


def arquivo_assinado(retirada_id: int):
    with get_session() as s:
        r = s.get(RetiradaLucro, retirada_id)
        if not r or r.assinado_dados is None:
            return None, None
        return r.assinado_nome, r.assinado_dados


def listar_retiradas(ano: Optional[int] = None, mes: Optional[int] = None) -> List[dict]:
    with get_session() as s:
        rs = s.scalars(select(RetiradaLucro).order_by(RetiradaLucro.data.desc())).all()
        out = []
        for r in rs:
            if ano is not None and r.data.year != ano:
                continue
            if mes is not None and r.data.month != mes:
                continue
            out.append(
                {
                    "id": r.id,
                    "data": r.data,
                    "valor": r.valor,
                    "observacao": r.observacao,
                    "tem_arquivo": r.arquivo_nome is not None,
                    "arquivo_nome": r.arquivo_nome,
                    "assinado": bool(r.assinado),
                    "tem_assinado": r.assinado_nome is not None,
                    "assinado_nome": r.assinado_nome,
                    "ano": r.data.year,
                    "mes": r.data.month,
                }
            )
        return out


def retiradas_por_mes(ano: int) -> List[dict]:
    """Para os 12 meses do ano: total, quantidade e se já foi feito."""
    todas = listar_retiradas(ano=ano)
    resultado = []
    for m in range(1, 13):
        do_mes = [r for r in todas if r["mes"] == m]
        total = sum(r["valor"] for r in do_mes)
        assinados = sum(1 for r in do_mes if r["assinado"])
        resultado.append(
            {
                "mes": m,
                "nome_mes": MESES[m - 1].capitalize(),
                "qtd": len(do_mes),
                "total": total,
                "feito": len(do_mes) > 0,
                "assinados": assinados,
            }
        )
    return resultado


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
