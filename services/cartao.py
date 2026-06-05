"""Regras de negócio das faturas de cartão (Fase 3).

Importa o PDF (via parser do banco), grava fatura + transações com categoria
sugerida, e oferece consultas/edição para a revisão manual.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from sqlalchemy import func, select

from core.config import UPLOADS_DIR
from core.db import get_session
from core.models import Categoria, Fatura, TransacaoCartao
from parsers.categorizador import CATEGORIAS_PADRAO
from parsers.registry import escolher_parser, extrair_fatura


# ---------------------------------------------------------------------------
# Categorias
# ---------------------------------------------------------------------------
def garantir_categorias_padrao() -> None:
    with get_session() as s:
        existentes = {c.nome for c in s.scalars(select(Categoria)).all()}
        for nome in CATEGORIAS_PADRAO:
            if nome not in existentes:
                s.add(Categoria(nome=nome))


def listar_categorias() -> List[dict]:
    garantir_categorias_padrao()
    with get_session() as s:
        cats = s.scalars(select(Categoria).order_by(Categoria.nome)).all()
        return [{"id": c.id, "nome": c.nome} for c in cats]


def _id_categoria(s, nome: Optional[str]) -> Optional[int]:
    if not nome:
        return None
    cat = s.scalar(select(Categoria).where(Categoria.nome == nome))
    if not cat:
        cat = Categoria(nome=nome)
        s.add(cat)
        s.flush()
    return cat.id


# ---------------------------------------------------------------------------
# Importação
# ---------------------------------------------------------------------------
def detectar_banco(pdf_path: str) -> str:
    return escolher_parser(pdf_path).banco


def salvar_upload(nome_arquivo: str, conteudo: bytes) -> str:
    """Salva o PDF enviado em data/uploads e devolve o caminho."""
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = UPLOADS_DIR / f"{stamp}_{Path(nome_arquivo).name}"
    destino.write_bytes(conteudo)
    return str(destino)


def previsualizar(pdf_path: str) -> dict:
    """Extrai a fatura sem gravar — para o usuário conferir antes de importar."""
    fat = extrair_fatura(pdf_path)
    return {
        "banco": fat.banco,
        "vencimento": fat.vencimento,
        "mes_referencia": fat.mes_referencia,
        "transacoes": [
            {
                "data": t.data,
                "descricao": t.descricao,
                "valor": t.valor,
                "parcela": t.parcela,
                "categoria_sugerida": t.categoria_sugerida,
            }
            for t in fat.transacoes
        ],
    }


def importar_fatura(pdf_path: str, mes_referencia: Optional[str] = None) -> int:
    """Extrai e grava a fatura. Retorna o id da fatura criada."""
    garantir_categorias_padrao()
    fat = extrair_fatura(pdf_path)
    mes_ref = mes_referencia or fat.mes_referencia

    with get_session() as s:
        fatura = Fatura(
            banco=fat.banco,
            mes_referencia=mes_ref,
            arquivo=pdf_path,
        )
        s.add(fatura)
        s.flush()
        for t in fat.transacoes:
            s.add(
                TransacaoCartao(
                    fatura_id=fatura.id,
                    data=t.data,
                    descricao=(t.descricao + (f" [{t.parcela}]" if t.parcela else "")),
                    valor=t.valor,
                    categoria_id=_id_categoria(s, t.categoria_sugerida),
                    revisado=False,
                )
            )
        return fatura.id


# ---------------------------------------------------------------------------
# Consultas e edição
# ---------------------------------------------------------------------------
def listar_faturas() -> List[dict]:
    with get_session() as s:
        faturas = s.scalars(select(Fatura).order_by(Fatura.data_importacao.desc())).all()
        resultado = []
        for f in faturas:
            n = len(f.transacoes)
            total = sum(t.valor for t in f.transacoes)
            pendentes = sum(1 for t in f.transacoes if not t.revisado)
            tem_comprovante = f.comprovante_nome is not None
            # "Validada/fechada" = paga + comprovante anexado.
            fechada = bool(f.paga) and tem_comprovante
            diferenca = (float(f.valor_pago) - total) if f.valor_pago is not None else None
            confere = diferenca is not None and abs(diferenca) < 0.01
            resultado.append(
                {
                    "id": f.id,
                    "banco": f.banco,
                    "mes_referencia": f.mes_referencia,
                    "data_importacao": f.data_importacao,
                    "transacoes": n,
                    "total": total,
                    "pendentes_revisao": pendentes,
                    "paga": bool(f.paga),
                    "data_pagamento": f.data_pagamento,
                    "valor_pago": f.valor_pago,
                    "tem_comprovante": tem_comprovante,
                    "comprovante_nome": f.comprovante_nome,
                    "fechada": fechada,
                    "diferenca": diferenca,
                    "confere": confere,
                }
            )
        return resultado


def listar_transacoes(fatura_id: int) -> List[dict]:
    with get_session() as s:
        stmt = (
            select(TransacaoCartao)
            .where(TransacaoCartao.fatura_id == fatura_id)
            .order_by(TransacaoCartao.data)
        )
        txs = s.scalars(stmt).all()
        return [
            {
                "id": t.id,
                "data": t.data,
                "descricao": t.descricao,
                "valor": t.valor,
                "categoria": t.categoria.nome if t.categoria else "Outros",
                "lumai": bool(t.lumai),
                "revisado": t.revisado,
            }
            for t in txs
        ]


def salvar_revisao(alteracoes: List[dict]) -> None:
    """Aplica edições. Cada item: {id, categoria, lumai, revisado} (campos opcionais)."""
    with get_session() as s:
        for item in alteracoes:
            t = s.get(TransacaoCartao, item["id"])
            if not t:
                continue
            if "categoria" in item:
                t.categoria_id = _id_categoria(s, item["categoria"])
            if "lumai" in item:
                t.lumai = bool(item["lumai"])
            if "revisado" in item:
                t.revisado = bool(item["revisado"])


# ---------------------------------------------------------------------------
# Gestão de categorias
# ---------------------------------------------------------------------------
def adicionar_categoria(nome: str) -> bool:
    """Cria uma categoria nova. Retorna False se o nome já existir/for vazio."""
    nome = (nome or "").strip()
    if not nome:
        return False
    with get_session() as s:
        existe = s.scalar(select(Categoria).where(func.lower(Categoria.nome) == nome.lower()))
        if existe:
            return False
        s.add(Categoria(nome=nome))
        return True


def renomear_categoria(nome_atual: str, nome_novo: str) -> bool:
    """Renomeia uma categoria (reflete em todas as transações por FK)."""
    nome_novo = (nome_novo or "").strip()
    if not nome_novo or nome_novo == nome_atual:
        return False
    with get_session() as s:
        cat = s.scalar(select(Categoria).where(Categoria.nome == nome_atual))
        if not cat:
            return False
        ja_existe = s.scalar(
            select(Categoria).where(func.lower(Categoria.nome) == nome_novo.lower())
        )
        if ja_existe and ja_existe.id != cat.id:
            return False
        cat.nome = nome_novo
        return True


def excluir_categoria(nome: str) -> bool:
    """Exclui uma categoria; transações ligadas a ela ficam sem categoria."""
    with get_session() as s:
        cat = s.scalar(select(Categoria).where(Categoria.nome == nome))
        if not cat:
            return False
        for t in s.scalars(select(TransacaoCartao).where(TransacaoCartao.categoria_id == cat.id)).all():
            t.categoria_id = None
        s.delete(cat)
        return True


# ---------------------------------------------------------------------------
# Reembolso LUMAI
# ---------------------------------------------------------------------------
def total_lumai_fatura(fatura_id: int) -> float:
    """Soma das transações marcadas como LUMAI numa fatura."""
    with get_session() as s:
        return float(
            s.scalar(
                select(func.coalesce(func.sum(TransacaoCartao.valor), 0.0))
                .where(TransacaoCartao.fatura_id == fatura_id)
                .where(TransacaoCartao.lumai.is_(True))
            )
            or 0.0
        )


def reembolso_lumai_por_fatura() -> List[dict]:
    """Para cada fatura com despesas LUMAI: banco, mês, qtd e total a reembolsar."""
    with get_session() as s:
        faturas = s.scalars(select(Fatura).order_by(Fatura.mes_referencia)).all()
        resultado = []
        for f in faturas:
            marcadas = [t for t in f.transacoes if t.lumai]
            if not marcadas:
                continue
            resultado.append(
                {
                    "fatura_id": f.id,
                    "banco": f.banco,
                    "mes_referencia": f.mes_referencia,
                    "itens": len(marcadas),
                    "total": sum(t.valor for t in marcadas),
                }
            )
        return resultado


def excluir_fatura(fatura_id: int) -> None:
    with get_session() as s:
        f = s.get(Fatura, fatura_id)
        if f:
            s.delete(f)


def registrar_pagamento_fatura(
    fatura_id: int,
    data_pagamento,
    valor_pago: float,
    comprovante_nome: Optional[str] = None,
    comprovante_dados: Optional[bytes] = None,
) -> None:
    """Marca a fatura como paga e anexa o comprovante (guardado no banco)."""
    with get_session() as s:
        f = s.get(Fatura, fatura_id)
        if not f:
            return
        f.paga = True
        f.data_pagamento = data_pagamento
        f.valor_pago = float(valor_pago) if valor_pago is not None else None
        if comprovante_dados is not None:
            f.comprovante_nome = comprovante_nome
            f.comprovante_dados = comprovante_dados


def remover_pagamento_fatura(fatura_id: int) -> None:
    """Desfaz o pagamento/validação (reabre a fatura e remove o comprovante)."""
    with get_session() as s:
        f = s.get(Fatura, fatura_id)
        if not f:
            return
        f.paga = False
        f.data_pagamento = None
        f.valor_pago = None
        f.comprovante_nome = None
        f.comprovante_dados = None


def comprovante_fatura(fatura_id: int):
    """Retorna (nome, dados) do comprovante, ou (None, None) se não houver."""
    with get_session() as s:
        f = s.get(Fatura, fatura_id)
        if not f or f.comprovante_dados is None:
            return None, None
        return f.comprovante_nome, f.comprovante_dados


def atualizar_mes_referencia(fatura_id: int, mes_referencia: str) -> None:
    """Ajusta o mês de competência (AAAA-MM) de uma fatura (rótulo organizador)."""
    with get_session() as s:
        f = s.get(Fatura, fatura_id)
        if f:
            f.mes_referencia = (mes_referencia or "").strip() or None


# ---------------------------------------------------------------------------
# Agregações para o painel
#
# O gasto é contado por FATURA: cada fatura pertence a um mês de competência
# (mes_referencia) que o usuário define. Ex.: a fatura com vencimento em
# 06/junho é a fatura de MAIO. A fatura inteira entra nesse mês — inclusive as
# parcelas — em vez de espalhar pelas datas originais das compras.
# ---------------------------------------------------------------------------
def gasto_total(mes_referencia: Optional[str] = None) -> float:
    with get_session() as s:
        stmt = select(func.coalesce(func.sum(TransacaoCartao.valor), 0.0)).join(Fatura)
        if mes_referencia:
            stmt = stmt.where(Fatura.mes_referencia == mes_referencia)
        return float(s.scalar(stmt) or 0.0)


def gasto_por_categoria(mes_referencia: Optional[str] = None) -> List[dict]:
    with get_session() as s:
        stmt = (
            select(Categoria.nome, func.sum(TransacaoCartao.valor))
            .select_from(TransacaoCartao)
            .join(Fatura, TransacaoCartao.fatura_id == Fatura.id)
            .outerjoin(Categoria, TransacaoCartao.categoria_id == Categoria.id)
            .group_by(Categoria.nome)
            .order_by(func.sum(TransacaoCartao.valor).desc())
        )
        if mes_referencia:
            stmt = stmt.where(Fatura.mes_referencia == mes_referencia)
        return [{"categoria": nome or "Outros", "total": float(total or 0.0)} for nome, total in s.execute(stmt)]


def gasto_por_categoria_fatura(fatura_id: int) -> List[dict]:
    """Quebra por categoria das transações de UMA fatura (independe do mês)."""
    with get_session() as s:
        stmt = (
            select(Categoria.nome, func.sum(TransacaoCartao.valor))
            .select_from(TransacaoCartao)
            .outerjoin(Categoria, TransacaoCartao.categoria_id == Categoria.id)
            .where(TransacaoCartao.fatura_id == fatura_id)
            .group_by(Categoria.nome)
            .order_by(func.sum(TransacaoCartao.valor).desc())
        )
        return [{"categoria": nome or "Outros", "total": float(total or 0.0)} for nome, total in s.execute(stmt)]
