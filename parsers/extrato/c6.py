"""Parser do extrato PDF do C6 Bank.

Formato: cabeçalho com o ano do período + linhas 'DD/MM DD/MM Tipo Descrição
R$ valor' (negativo com sinal). O ano das datas vem do cabeçalho.
"""
from __future__ import annotations

import io
import re
from datetime import date

from parsers.extrato.base import ExtratoLido, LancamentoExtrato, _parse_valor_br


BANCO = "C6"

MESES_PT = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8, "setembro": 9,
    "outubro": 10, "novembro": 11, "dezembro": 12,
}


def detectar(texto: str) -> bool:
    t = (texto or "").lower()
    return ("c6" in t and ("banco" in t or "c6tag" in t or "conta" in t)) or \
           "c6 bank" in t


# Linha: '01/06 01/06 Entrada PIX Pix recebido de ...  R$ 4.450,00'
#     ou '01/06 01/06 Pagamento MIRAVALES ...          -R$ 756,84'
# Duas datas iniciais, depois tudo, e o valor no final.
LINHA = re.compile(
    r"^(\d{2}/\d{2})\s+(\d{2}/\d{2})\s+(.+?)\s+(-?\s*R\$\s*[\d\.,]+)\s*$"
)

# Fallback para linhas com só uma data no início.
LINHA_ALT = re.compile(
    r"^(\d{2}/\d{2})\s+(.+?)\s+(-?\s*R\$\s*[\d\.,]+)\s*$"
)

IGNORAR = re.compile(r"saldo\s+do\s+dia|cheque\s+especial", re.I)


def _detectar_ano(texto: str) -> int:
    """Extrai o ano do cabeçalho 'Período • 1 de junho de 2026 até ...' ou
    'Junho 2026'."""
    # Prioridade: 'de <ano>' após um nome de mês.
    for nome_mes in MESES_PT:
        m = re.search(rf"{nome_mes}\s+de\s+(\d{{4}})", texto, re.I)
        if m:
            return int(m.group(1))
    # 'Junho 2026'
    for nome_mes in MESES_PT:
        m = re.search(rf"{nome_mes}\s+(\d{{4}})", texto, re.I)
        if m:
            return int(m.group(1))
    # Qualquer /AAAA no texto.
    m = re.search(r"/(20\d{2})", texto)
    if m:
        return int(m.group(1))
    return date.today().year


def extrair(dados: bytes, senha: str = "") -> ExtratoLido:
    import pdfplumber

    texto = ""
    with pdfplumber.open(io.BytesIO(dados), password=senha or "") as pdf:
        for pg in pdf.pages:
            texto += (pg.extract_text(x_tolerance=2) or "") + "\n"

    ano = _detectar_ano(texto)

    lancs = []
    for linha in texto.split("\n"):
        linha = linha.strip()
        if not linha or IGNORAR.search(linha):
            continue
        m = LINHA.match(linha) or LINHA_ALT.match(linha)
        if not m:
            continue
        if len(m.groups()) == 4:  # LINHA (2 datas)
            data_str, _, desc, valor_str = m.groups()
        else:  # LINHA_ALT (1 data)
            data_str, desc, valor_str = m.groups()

        # Data com o ano do cabeçalho
        try:
            d, mes = data_str.split("/")
            dt = date(ano, int(mes), int(d))
        except ValueError:
            continue

        valor = _parse_valor_br(valor_str)
        if valor is None or valor == 0:
            continue

        desc = desc.strip()
        # Se dá pra derivar a forma de pagamento a partir do 'tipo', ok, mas
        # a UI já sugere a forma pela descrição — deixa a descrição inteira.
        lancs.append(LancamentoExtrato(data=dt, descricao=desc, valor=valor))

    return ExtratoLido(banco=BANCO, lancamentos=lancs)
