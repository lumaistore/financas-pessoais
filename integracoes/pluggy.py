"""Integração futura com agregador (Pluggy).

NÃO IMPLEMENTADO nesta fase — por escolha de escopo. Este módulo existe
apenas para deixar a arquitetura preparada: quando for plugar um agregador
via API, implemente esta interface e os dados desembocam nas mesmas tabelas
de investimentos já usadas pelos uploads manuais.
"""
from __future__ import annotations

from typing import Protocol


class AgregadorInvestimentos(Protocol):
    """Contrato esperado de um agregador externo (ex.: Pluggy)."""

    def importar_posicoes(self) -> list[dict]:
        """Deve retornar snapshots no mesmo formato de InvestimentoSnapshot."""
        ...

    def importar_movimentos(self) -> list[dict]:
        """Deve retornar movimentos no mesmo formato de InvestimentoMovimento."""
        ...


class PluggyClient:
    def __init__(self, *args, **kwargs) -> None:
        raise NotImplementedError(
            "Integração com Pluggy não implementada nesta fase. "
            "A arquitetura está preparada para recebê-la no futuro."
        )
