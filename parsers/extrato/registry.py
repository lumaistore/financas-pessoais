"""Escolhe o parser certo pelo formato do arquivo."""
from __future__ import annotations

import io
from typing import Optional

from parsers.extrato.base import ExtratoLido
from parsers.extrato import c6 as parser_c6
from parsers.extrato import itau as parser_itau
from parsers.extrato import ofx as parser_ofx


def _ler_texto_pdf(dados: bytes, senha: str = "") -> str:
    try:
        import pdfplumber
        texto = ""
        with pdfplumber.open(io.BytesIO(dados), password=senha or "") as pdf:
            for pg in pdf.pages[:3]:
                texto += (pg.extract_text(x_tolerance=2) or "") + "\n"
        return texto
    except Exception:
        return ""


def pdf_pede_senha(dados: bytes) -> bool:
    """Detecta se o PDF está protegido por senha (sem tentar abrir com senha)."""
    try:
        import pdfplumber
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            _ = pdf.pages[0]
        return False
    except Exception as e:
        msg = str(e).lower()
        return "password" in msg or "encrypt" in msg


def _ler_texto_planilha(dados: bytes, nome: str) -> str:
    """Converte 1a planilha em texto para detecção."""
    try:
        if nome.lower().endswith(".csv"):
            return dados[:5000].decode("utf-8", errors="ignore")
        import pandas as pd
        df = pd.read_excel(io.BytesIO(dados), sheet_name=0, nrows=50)
        return df.to_string(index=False)
    except Exception:
        return ""


def extrair(dados: bytes, nome_arquivo: str, senha: str = "") -> Optional[ExtratoLido]:
    """Recebe os bytes do arquivo, escolhe o parser e devolve os lançamentos.
    Retorna None se não reconhecer o formato. Passe `senha` se o PDF estiver
    protegido (comum em extratos bancários)."""
    nome = (nome_arquivo or "").lower()

    # OFX (pelo nome ou pelo conteúdo)
    if nome.endswith(".ofx"):
        return parser_ofx.extrair(dados)

    # PDF
    if nome.endswith(".pdf"):
        texto = _ler_texto_pdf(dados, senha=senha)
        if parser_c6.detectar(texto):
            return parser_c6.extrair(dados, senha=senha)
        if parser_itau.detectar(texto):
            return parser_itau.extrair(dados, senha=senha)
        if parser_ofx.detectar(texto):
            return parser_ofx.extrair_texto_ofx(texto)
        # Genérico: tenta o regex do Itaú, que cobre a maioria dos PDFs BR
        # com linha "DD/MM/AAAA descrição valor".
        return parser_itau.extrair(dados, senha=senha)

    # Excel / CSV — placeholder: a maioria dos bancos suporta OFX, então
    # priorizamos OFX. Se você tiver um Excel específico, montamos o parser
    # olhando o formato.
    if nome.endswith((".xlsx", ".xls", ".csv")):
        # Tenta ler como texto e usar o detector do Itaú.
        _ = _ler_texto_planilha(dados, nome)
        # Ainda não temos parser dedicado.
        return None

    return None
