"""Parser genérico de fatura (fallback).

Usado quando nenhum parser específico reconhece o banco. Varre todas as linhas
procurando o padrão `DD/MM DESCRIÇÃO VALOR`. É melhor-esforço: o usuário revisa.
"""
from __future__ import annotations

import re
from datetime import date

import pdfplumber

from parsers.base import FaturaExtraida, TransacaoExtraida, inferir_ano, parse_valor_br
from parsers.categorizador import sugerir_categoria

RE_LINHA = re.compile(
    r"^(\d{2})/(\d{2})(?:/(\d{2,4}))?\s+(.+?)\s+(-?(?:R\$\s*)?[\d.]+,\d{2})\s*([DC]?)\s*$"
)


class ParserGenerico:
    banco = "Genérico"

    def detectar(self, texto: str) -> bool:
        return True  # sempre serve como último recurso

    def extrair(self, pdf_path: str) -> FaturaExtraida:
        fatura = FaturaExtraida(banco=self.banco)
        with pdfplumber.open(pdf_path) as pdf:
            for pg in pdf.pages:
                for linha in (pg.extract_text() or "").splitlines():
                    m = RE_LINHA.match(linha.strip())
                    if not m:
                        continue
                    if m.group(6) == "C":  # crédito
                        continue
                    valor = parse_valor_br(m.group(5))
                    if valor <= 0:
                        continue
                    dia, mes = int(m.group(1)), int(m.group(2))
                    if m.group(3):
                        ano = int(m.group(3))
                        ano = ano + 2000 if ano < 100 else ano
                    else:
                        ano = inferir_ano(mes, fatura.vencimento)
                    descricao = re.sub(r"\s{2,}", " ", m.group(4)).strip()
                    fatura.transacoes.append(
                        TransacaoExtraida(
                            data=date(ano, mes, dia),
                            descricao=descricao,
                            valor=valor,
                            categoria_sugerida=sugerir_categoria(descricao),
                        )
                    )
        return fatura
