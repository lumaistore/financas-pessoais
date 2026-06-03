"""Seleção automática do parser de fatura conforme o banco.

Para adicionar um banco novo: implemente um parser em parsers/cartao/ e
inclua-o em PARSERS_ESPECIFICOS (antes do genérico).
"""
from __future__ import annotations

import pdfplumber

from parsers.base import FaturaExtraida, ParserFatura
from parsers.cartao.caixa import ParserCaixa
from parsers.cartao.generico import ParserGenerico
from parsers.cartao.itau import ParserItau

PARSERS_ESPECIFICOS = [ParserItau(), ParserCaixa()]
PARSER_GENERICO = ParserGenerico()


def _texto_inicial(pdf_path: str, paginas: int = 2) -> str:
    texto = ""
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages[:paginas]:
            texto += (pg.extract_text() or "") + "\n"
    return texto


def escolher_parser(pdf_path: str) -> ParserFatura:
    texto = _texto_inicial(pdf_path)
    for parser in PARSERS_ESPECIFICOS:
        if parser.detectar(texto):
            return parser
    return PARSER_GENERICO


def extrair_fatura(pdf_path: str) -> FaturaExtraida:
    return escolher_parser(pdf_path).extrair(pdf_path)
