"""Parser do extrato PDF do Itaú (conta corrente / Universitária)."""
from __future__ import annotations

import io
import re
from datetime import date

from parsers.extrato.base import ExtratoLido, LancamentoExtrato, _parse_valor_br


BANCO = "Itaú"


def detectar(texto: str) -> bool:
    t = (texto or "").lower()
    return ("itau" in t or "itaú" in t) and "extrato" in t and "saldo" in t


# Linha típica: '03/07/2026 PIX TRANSF LUMAI I03/07 3.094,00'
# ou           '01/07/2026 DA CELPE 7055000969 -26,17'
LINHA = re.compile(
    r"^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?[\d\.,]+)\s*$"
)

# Linhas a ignorar: saldos, rendimentos irrelevantes, cabeçalhos.
IGNORAR = re.compile(
    r"SALDO\s+(DO\s+DIA|ANTERIOR|FINAL)|LIMITE|SALDO EM CONTA",
    re.I,
)


def extrair(dados: bytes) -> ExtratoLido:
    import pdfplumber

    texto = ""
    with pdfplumber.open(io.BytesIO(dados)) as pdf:
        for pg in pdf.pages:
            # x_tolerance=2 preserva espaços entre colunas
            texto += (pg.extract_text(x_tolerance=2) or "") + "\n"

    lancs = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        m = LINHA.match(linha)
        if not m:
            continue
        data_str, desc, valor_str = m.group(1), m.group(2).strip(), m.group(3)
        # Filtra linhas de saldo/limite.
        if IGNORAR.search(desc) or IGNORAR.search(linha):
            continue
        v = _parse_valor_br(valor_str)
        if v is None or v == 0:
            continue
        try:
            d, mes, ano = data_str.split("/")
            dt = date(int(ano), int(mes), int(d))
        except ValueError:
            continue
        lancs.append(LancamentoExtrato(data=dt, descricao=desc, valor=v))

    return ExtratoLido(banco=BANCO, lancamentos=lancs)
