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
    (ex.: PDF escaneado/imagem) — aí o usuário preenche à mão.

    Detalhe: alguns recibos vêm do modelo em branco com '_____' como linha
    pra preencher; ao digitar em cima, os caracteres ficam intercalados com
    underscores (ex.: 'L_U_M_A_I' = 'LUMAI', '0_5_/0_1_/2_0_26' = '05/01/2026').
    Removemos os '_' antes da extração para esses casos funcionarem.
    """
    import re

    import pdfplumber

    texto = ""
    try:
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pg in pdf.pages:
                texto += (pg.extract_text() or "") + "\n"
    except Exception:
        return {"valor": None, "data": None}

    # Versão "limpa": sem os underscores do template em branco. Mantemos o
    # original também, caso algum recibo legítimo tenha '_' no meio.
    limpo = texto.replace("_", " ")

    data_val = None
    for fonte in (limpo, texto):
        # Tenta perto da palavra "distribuição" primeiro (mais confiável).
        m = re.search(
            r"distribui[çc][ãa]o[^0-9]{0,40}(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{2,4})",
            fonte, re.I,
        )
        if not m:
            m = re.search(r"(\d{1,2})\s*/\s*(\d{1,2})\s*/\s*(\d{4})", fonte)
        if m:
            d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
            if y < 100:
                y += 2000
            try:
                data_val = date(y, mo, d)
                break
            except ValueError:
                pass
    # Fallback: textos onde os dígitos da data ficaram separados por espaços
    # (ex.: "Data da distribuição: 0 5 / 0 1 / 2 0 26" — original veio com
    # underscores entre os dígitos). Procura especificamente "Data da
    # distribuição" e extrai os 6-8 dígitos seguintes.
    if data_val is None:
        # Itera todas as ocorrências de "distribuição" — pode haver 2+ no PDF
        # (uma no título, outra no campo). Aceita a primeira que tiver dígitos.
        for m in re.finditer(r"(?:Data\s+da\s+)?distribui[çc][ãa]o[^A-Za-z]{0,80}", limpo, re.I):
            trecho = m.group(0)
            digitos = re.sub(r"\D", "", trecho)
            if len(digitos) < 6:
                continue
            try:
                d = int(digitos[0:2])
                mo = int(digitos[2:4])
                if len(digitos) >= 8:
                    y = int(digitos[4:8])
                else:
                    y = 2000 + int(digitos[4:6])
                data_val = date(y, mo, d)
                break
            except ValueError:
                continue

    valor_val = None
    # Procura o valor logo após "Valor distribuído" / "R$" — ignora espaços
    # e quebras de linha (no recibo, o valor pode estar numa linha abaixo do R$).
    for fonte in (limpo, texto):
        mv = re.search(
            r"(?:Valor\s+distribu[íi]do[^0-9R$]*)?R\$[^\d-]*([\d\.,]+)",
            fonte, re.I | re.S,
        )
        if mv:
            valor_val = _parse_valor(mv.group(1))
            if valor_val:
                break

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
