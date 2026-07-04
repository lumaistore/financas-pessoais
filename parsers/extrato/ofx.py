"""Parser OFX (padrão de extrato bancário — Open Financial Exchange).

Funciona pra qualquer banco. Baixa o extrato como .ofx do internet banking
(disponível em Itaú, BB, C6, Nubank etc.).
"""
from __future__ import annotations

import re
from datetime import date

from parsers.extrato.base import ExtratoLido, LancamentoExtrato


BANCO = "OFX"


def detectar(texto: str) -> bool:
    t = (texto or "")[:2000].upper()
    return "<OFX>" in t or "<STMTTRN>" in t or "<TRNTYPE>" in t


def _parse_data(s: str):
    """OFX usa 'YYYYMMDD' ou 'YYYYMMDDHHMMSS'."""
    if not s or len(s) < 8:
        return None
    try:
        return date(int(s[:4]), int(s[4:6]), int(s[6:8]))
    except ValueError:
        return None


def extrair_texto_ofx(texto: str) -> ExtratoLido:
    lancs = []
    # Cada transação vem em <STMTTRN>...</STMTTRN>
    for bloco in re.finditer(r"<STMTTRN>(.*?)</STMTTRN>", texto, re.S | re.I):
        b = bloco.group(1)
        m_data = re.search(r"<DTPOSTED>\s*([\d]+)", b, re.I)
        m_val = re.search(r"<TRNAMT>\s*(-?[\d\.]+)", b, re.I)
        m_desc = re.search(r"<MEMO>\s*(.+?)\s*<", b, re.I | re.S)
        if not m_desc:
            m_desc = re.search(r"<NAME>\s*(.+?)\s*<", b, re.I | re.S)
        if not (m_data and m_val):
            continue
        try:
            valor = float(m_val.group(1))
        except ValueError:
            continue
        d = _parse_data(m_data.group(1))
        if d is None or valor == 0:
            continue
        desc = (m_desc.group(1).strip() if m_desc else "").replace("\n", " ")
        lancs.append(LancamentoExtrato(data=d, descricao=desc, valor=valor))
    return ExtratoLido(banco=BANCO, lancamentos=lancs)


def extrair(dados: bytes) -> ExtratoLido:
    # OFX pode vir em latin-1 (bancos BR) ou UTF-8. Tenta os dois.
    for enc in ("utf-8", "latin-1"):
        try:
            texto = dados.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        texto = dados.decode("utf-8", errors="ignore")
    return extrair_texto_ofx(texto)
