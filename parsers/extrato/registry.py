"""Escolhe o parser certo pelo formato do arquivo."""
from __future__ import annotations

import io
from typing import Optional

from parsers.extrato.base import ExtratoLido
from parsers.extrato import itau as parser_itau
from parsers.extrato import ofx as parser_ofx


def _ler_texto_pdf(dados: bytes) -> str:
    try:
        import pdfplumber
        texto = ""
        with pdfplumber.open(io.BytesIO(dados)) as pdf:
            for pg in pdf.pages[:3]:
                texto += (pg.extract_text(x_tolerance=2) or "") + "\n"
        return texto
    except Exception:
        return ""


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


def extrair(dados: bytes, nome_arquivo: str) -> Optional[ExtratoLido]:
    """Recebe os bytes do arquivo, escolhe o parser e devolve os lançamentos.
    Retorna None se não reconhecer o formato."""
    nome = (nome_arquivo or "").lower()

    # OFX (pelo nome ou pelo conteúdo)
    if nome.endswith(".ofx"):
        return parser_ofx.extrair(dados)

    # PDF
    if nome.endswith(".pdf"):
        texto = _ler_texto_pdf(dados)
        if parser_itau.detectar(texto):
            return parser_itau.extrair(dados)
        if parser_ofx.detectar(texto):
            return parser_ofx.extrair_texto_ofx(texto)
        # Genérico: tenta o regex do Itaú, que cobre a maioria dos PDFs BR
        # com linha "DD/MM/AAAA descrição valor".
        return parser_itau.extrair(dados)

    # Excel / CSV — placeholder: a maioria dos bancos suporta OFX, então
    # priorizamos OFX. Se você tiver um Excel específico, montamos o parser
    # olhando o formato.
    if nome.endswith((".xlsx", ".xls", ".csv")):
        # Tenta ler como texto e usar o detector do Itaú.
        _ = _ler_texto_planilha(dados, nome)
        # Ainda não temos parser dedicado.
        return None

    return None
