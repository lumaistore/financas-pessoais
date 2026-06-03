"""Parser de fatura do cartão Itaú.

Layout em DUAS COLUNAS. O texto puro sai entrelaçado, então separamos as
palavras por coordenada x (coluna esquerda x < 340, direita x >= 340),
reconstruímos as linhas de cada coluna e só então fazemos o parsing.

Cada lançamento: `DD/MM ESTABELECIMENTO [parcela DD/DD] VALOR`.
A linha seguinte (categoria/cidade) é ignorada — a categoria é sugerida a
partir do nome do estabelecimento.
"""
from __future__ import annotations

import re
from collections import defaultdict
from datetime import date
from typing import List, Optional

import pdfplumber

from parsers.base import FaturaExtraida, TransacaoExtraida, inferir_ano, parse_valor_br
from parsers.categorizador import sugerir_categoria

COLUNA_SPLIT_X = 340
RE_DATA = re.compile(r"^\d{2}/\d{2}$")
RE_MONEY = re.compile(r"^-?\d{1,3}(\.\d{3})*,\d{2}$")
RE_PARCELA = re.compile(r"^\d{2}/\d{2}$")
RE_VENC = re.compile(r"Vencimento:\s*(\d{2})/(\d{2})/(\d{4})")

IGNORAR = ("pagamento", "total", "saldo", "encargos", "estabelecimento", "data")


class ParserItau:
    banco = "Itaú"

    def detectar(self, texto: str) -> bool:
        t = texto.lower()
        return "itaú" in t or "itau" in t or "341-7" in texto

    def _linhas_ordenadas(self, page) -> List[str]:
        """Reconstrói as linhas separando as duas colunas (esquerda, depois direita)."""
        esquerda: dict = defaultdict(list)
        direita: dict = defaultdict(list)
        for w in page.extract_words():
            alvo = esquerda if w["x0"] < COLUNA_SPLIT_X else direita
            alvo[round(w["top"])].append(w)

        linhas: List[str] = []
        for coluna in (esquerda, direita):
            for top in sorted(coluna):
                ws = sorted(coluna[top], key=lambda w: w["x0"])
                linhas.append(" ".join(w["text"] for w in ws))
        return linhas

    def extrair(self, pdf_path: str) -> FaturaExtraida:
        fatura = FaturaExtraida(banco=self.banco)
        todas_linhas: List[str] = []
        texto_completo = ""
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                texto_completo += (pg.extract_text() or "") + "\n"
                todas_linhas.extend(self._linhas_ordenadas(pg))

        m = RE_VENC.search(texto_completo)
        if m:
            fatura.vencimento = date(int(m.group(3)), int(m.group(2)), int(m.group(1)))
            fatura.mes_referencia = fatura.vencimento.strftime("%Y-%m")

        for linha in todas_linhas:
            # A seção "Compras parceladas - próximas faturas" lista PARCELAS
            # FUTURAS (não pertencem a esta fatura). Para tudo ao chegar nela.
            if "ximas faturas" in linha.lower():
                break

            tokens = linha.split()
            if len(tokens) < 3 or not RE_DATA.match(tokens[0]):
                continue
            # Valor = último token com formato monetário.
            idx_valor = None
            for i in range(len(tokens) - 1, 0, -1):
                if RE_MONEY.match(tokens[i]):
                    idx_valor = i
                    break
            if idx_valor is None:
                continue

            valor = parse_valor_br(tokens[idx_valor])
            if valor <= 0:  # pagamentos/estornos
                continue

            miolo = tokens[1:idx_valor]
            parcela = None
            estab_tokens = []
            for tk in miolo:
                if parcela is None and RE_PARCELA.match(tk):
                    parcela = tk
                else:
                    estab_tokens.append(tk)
            descricao = " ".join(estab_tokens).strip()
            if not descricao or any(p in descricao.lower() for p in IGNORAR):
                continue

            dia, mes = int(tokens[0][:2]), int(tokens[0][3:5])
            ano = inferir_ano(mes, fatura.vencimento)
            fatura.transacoes.append(
                TransacaoExtraida(
                    data=date(ano, mes, dia),
                    descricao=descricao,
                    valor=valor,
                    parcela=parcela,
                    categoria_sugerida=sugerir_categoria(descricao),
                )
            )
        return fatura
