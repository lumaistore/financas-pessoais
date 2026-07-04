"""Cadastro de contas financeiras do usuário + detecção automática de
transferências internas e aplicações a partir do texto de lançamentos.

Regras:
- Se a descrição de um lançamento contém um identificador de conta cadastrada
  como CORRENTE/POUPANÇA do usuário → é `transferencia` (não conta em nada).
- Se contém identificador de conta cadastrada como APLICAÇÃO (ex.: BTG) →
  é `aplicacao` (vai para carteira, não é despesa).
"""
from __future__ import annotations

import unicodedata
from typing import List, Optional, Tuple

from sqlalchemy import select

from core.db import get_session
from core.models import ContaFinanceira

TIPOS_CONTA = ["corrente", "poupança", "aplicação"]


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------
def _norm(s: str) -> str:
    """Normaliza para comparação: minúsculas sem acento."""
    if not s:
        return ""
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower())
        if not unicodedata.combining(c)
    )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def adicionar_conta(apelido: str, banco: str, tipo: str, identificadores: str) -> int:
    with get_session() as s:
        c = ContaFinanceira(
            apelido=apelido.strip(),
            banco=banco.strip() or None,
            tipo=tipo if tipo in TIPOS_CONTA else "corrente",
            identificadores=identificadores.strip() or None,
        )
        s.add(c)
        s.flush()
        return c.id


def atualizar_conta(cid: int, apelido: str, banco: str, tipo: str,
                    identificadores: str, ativa: bool = True) -> None:
    with get_session() as s:
        c = s.get(ContaFinanceira, cid)
        if not c:
            return
        c.apelido = apelido.strip()
        c.banco = banco.strip() or None
        c.tipo = tipo if tipo in TIPOS_CONTA else "corrente"
        c.identificadores = identificadores.strip() or None
        c.ativa = bool(ativa)


def excluir_conta(cid: int) -> None:
    with get_session() as s:
        c = s.get(ContaFinanceira, cid)
        if c:
            s.delete(c)


def listar_contas(apenas_ativas: bool = True) -> List[dict]:
    with get_session() as s:
        stmt = select(ContaFinanceira).order_by(ContaFinanceira.apelido)
        if apenas_ativas:
            stmt = stmt.where(ContaFinanceira.ativa.is_(True))
        return [
            {
                "id": c.id, "apelido": c.apelido, "banco": c.banco,
                "tipo": c.tipo, "identificadores": c.identificadores or "",
                "ativa": c.ativa,
            }
            for c in s.scalars(stmt).all()
        ]


# ---------------------------------------------------------------------------
# Detecção
# ---------------------------------------------------------------------------
def _lista_identificadores(conta: dict) -> List[str]:
    """Devolve os identificadores normalizados dessa conta."""
    ids = [conta["apelido"]]
    if conta.get("banco"):
        ids.append(conta["banco"])
    if conta.get("identificadores"):
        ids += [x.strip() for x in conta["identificadores"].split(",") if x.strip()]
    return [_norm(x) for x in ids if x]


def detectar_conta(descricao: str,
                   conta_origem_id: Optional[int] = None
                   ) -> Tuple[str, Optional[int]]:
    """Analisa a descrição de um lançamento e retorna (tipo, conta_destino_id).

    - `tipo` ∈ {"transferencia", "aplicacao", ""}
    - `conta_destino_id` só é preenchido se identificou uma conta cadastrada.
    - Retorna ("", None) se não reconhece — o chamador decide (receita/despesa
      normais).

    `conta_origem_id` evita casar consigo mesmo (ex.: descrição do C6 contendo
    "C6" não deve virar transferência interna).
    """
    if not descricao:
        return "", None
    d = _norm(descricao)
    contas = listar_contas(apenas_ativas=True)
    for conta in contas:
        if conta_origem_id and conta["id"] == conta_origem_id:
            continue
        ids = _lista_identificadores(conta)
        if not ids:
            continue
        for identificador in ids:
            # Match por substring, tomando o identificador com pelo menos 4
            # chars para evitar falso positivo em siglas curtas.
            if len(identificador) >= 4 and identificador in d:
                if conta["tipo"] == "aplicação":
                    return "aplicacao", conta["id"]
                return "transferencia", conta["id"]
    return "", None


def semear_contas_padrao() -> int:
    """Cria as contas básicas do usuário se ainda não existirem (idempotente).
    Ajuda no primeiro uso; usuário pode editar/excluir depois."""
    from services.perfil import get_perfil

    ja_tem = {c["apelido"].lower() for c in listar_contas(apenas_ativas=False)}
    perfil = get_perfil()
    ids_usuario = perfil.get("nome", "")
    criadas = 0
    padroes = [
        ("Itaú (corrente)", "Itaú", "corrente", ids_usuario),
        ("C6 (corrente)", "C6", "corrente", ids_usuario),
        ("BTG (aplicação)", "BTG", "aplicação", "BTG,BTG PACTUAL"),
    ]
    for apelido, banco, tipo, identificadores in padroes:
        if apelido.lower() in ja_tem:
            continue
        adicionar_conta(apelido, banco, tipo, identificadores)
        criadas += 1
    return criadas
