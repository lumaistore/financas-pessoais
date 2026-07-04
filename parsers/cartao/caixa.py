"""Parser de fatura do cartão Caixa (Visa).

Layout em seções (COMPRAS, COMPRAS PARCELADAS, COMPRAS INTERNACIONAIS...).
Cada lançamento: `DD/MM DESCRIÇÃO ... CIDADE VALOR[D|C]`.
Parcelas aparecem como "05 DE 10" na descrição. Sufixo D = débito (gasto),
C = crédito (pagamento/estorno).
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

import pdfplumber

from parsers.base import FaturaExtraida, TransacaoExtraida, inferir_ano, parse_valor_br
from parsers.categorizador import sugerir_categoria

# Valor no fim da linha: 1.482,31D  /  309,94D  /  8.605,21C
RE_VALOR_FIM = re.compile(r"(-?[\d.]+,\d{2})\s*([DC])\s*$")
# Data em qualquer posição: uma barra lateral ("Programa de Pontos") às vezes
# aparece antes da data na mesma linha extraída.
RE_DATA = re.compile(r"\b(\d{2})/(\d{2})\b")
RE_PARCELA = re.compile(r"(\d{2})\s*DE\s*(\d{2})")
RE_VENC = re.compile(r"VENCIMENTO\s+(\d{2})/(\d{2})/(\d{4})")

# Descrições que NÃO são compras (totais, pagamentos, ajustes).
IGNORAR = (
    "TOTAL DA FATURA", "OBRIGADO PELO PAGAMENTO", "TOTAL COMPRAS",
    "TOTAL ", "ANUIDADE", "SALDO", "PAGAMENTO",
)


def _melhor_data(linha: str, vencimento):
    """Escolhe qual DD/MM da linha é a DATA da transação.

    A linha pode conter outros DD/DD (parcela '03/08', pontos etc.). Preferimos
    a data que cai DENTRO da janela da fatura: entre 0 e 2 meses antes do
    vencimento. Isso evita ler a parcela como se fosse a data (o que jogava
    lançamentos para meses errados, ex.: agosto)."""
    candidatos = []
    for m in RE_DATA.finditer(linha):
        d, mo = int(m.group(1)), int(m.group(2))
        if not (1 <= d <= 31 and 1 <= mo <= 12):
            continue
        ano = inferir_ano(mo, vencimento)
        try:
            dt = date(ano, mo, d)
        except ValueError:
            continue
        candidatos.append((dt, m))
    if not candidatos:
        return None, None
    if vencimento:
        em_janela = []
        for dt, m in candidatos:
            dif = (vencimento.year - dt.year) * 12 + (vencimento.month - dt.month)
            if 0 <= dif <= 2:  # transação até ~2 meses antes do vencimento
                em_janela.append((dif, m.start(), dt, m))
        if em_janela:
            em_janela.sort(key=lambda x: (x[0], x[1]))  # mais perto do venc., depois posição
            return em_janela[0][2], em_janela[0][3]
    return candidatos[0]


class ParserCaixa:
    banco = "Caixa"

    def detectar(self, texto: str) -> bool:
        t = texto.upper()
        return "CAIXA" in t and ("VISA" in t or "40040104" in t)

    def extrair(self, pdf_path: str) -> FaturaExtraida:
        fatura = FaturaExtraida(banco=self.banco)
        linhas = []
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                txt = pg.extract_text() or ""
                linhas.extend(txt.splitlines())

        texto_completo = "\n".join(linhas)
        m = RE_VENC.search(texto_completo)
        if m:
            fatura.vencimento = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            fatura.mes_referencia = fatura.vencimento.strftime("%Y-%m")

        for linha in linhas:
            t = linha.strip()
            dt, mdata = _melhor_data(t, fatura.vencimento)
            mval = RE_VALOR_FIM.search(t)
            if not (dt and mdata and mval):
                continue
            descricao_full = t[mdata.end():mval.start()].strip()
            if not descricao_full or any(p in descricao_full.upper() for p in IGNORAR):
                continue

            valor = parse_valor_br(mval.group(1))
            if mval.group(2) == "C":  # crédito: pagamento/estorno — ignora como gasto
                continue

            ano = dt.year

            parcela = None
            mp = RE_PARCELA.search(descricao_full)
            if mp:
                parcela = f"{mp.group(1)}/{mp.group(2)}"
                descricao_full = RE_PARCELA.sub("", descricao_full).strip()

            descricao = re.sub(r"\s{2,}", " ", descricao_full)
            fatura.transacoes.append(
                TransacaoExtraida(
                    data=dt,
                    descricao=descricao,
                    valor=valor,
                    parcela=parcela,
                    categoria_sugerida=sugerir_categoria(descricao),
                )
            )
        return fatura
