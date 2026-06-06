"""Perfil do usuário (singleton) — usado como padrão em formulários.

Ex.: na aba de despesas médicas, o nome do usuário vira o paciente padrão.
Se ainda não estiver configurado, tenta puxar do RetiradaLucroConfig
(que já foi preenchido pelo usuário com nome+CPF).
"""
from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select

from core.db import get_session
from core.models import PerfilUsuario, RetiradaLucroConfig


def _semear_de_retirada(s) -> PerfilUsuario:
    """Pré-preenche o perfil com nome/CPF da config de lucros, se existir."""
    p = PerfilUsuario()
    cfg = s.scalar(select(RetiradaLucroConfig).limit(1))
    if cfg:
        p.nome = cfg.beneficiario or None
        p.cpf = cfg.cpf or None
    s.add(p)
    s.flush()
    return p


def get_perfil() -> dict:
    with get_session() as s:
        p = s.scalar(select(PerfilUsuario).limit(1))
        if not p:
            p = _semear_de_retirada(s)
        return {
            "nome": p.nome or "",
            "cpf": p.cpf or "",
            "dependentes": p.dependentes or "",
        }


def salvar_perfil(nome: str, cpf: str, dependentes: str = "") -> None:
    with get_session() as s:
        p = s.scalar(select(PerfilUsuario).limit(1))
        if not p:
            p = PerfilUsuario()
            s.add(p)
        p.nome = nome.strip() or None
        p.cpf = cpf.strip() or None
        p.dependentes = dependentes.strip() or None


def lista_pacientes() -> List[str]:
    """O usuário + dependentes (para sugerir no campo paciente)."""
    p = get_perfil()
    nomes = [p["nome"]] if p["nome"] else []
    if p["dependentes"]:
        nomes += [n.strip() for n in p["dependentes"].split(",") if n.strip()]
    return nomes


def paciente_padrao() -> Optional[str]:
    p = get_perfil()
    return p["nome"] or None
