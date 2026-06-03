"""Copia todos os dados do SQLite local para o banco de destino (Postgres).

Uso:
    DATABASE_URL="postgresql://...neon..." .venv/bin/python tools/migrar_para_postgres.py

O destino (DATABASE_URL) recebe o schema (create_all) e depois cada linha do
SQLite local é copiada. Idempotente o suficiente para rodar de novo: ele
pergunta antes de apagar dados existentes no destino.
"""
from __future__ import annotations

import os
import sys

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

# Garante import do pacote do projeto quando rodado da raiz.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import DB_PATH, get_db_url  # noqa: E402
from core.models import (  # noqa: E402
    Base,
    CarteiraHistorico,
    Categoria,
    Compromisso,
    CompromissoParcela,
    DespesaManual,
    Fatura,
    Instituicao,
    InvestimentoMovimento,
    InvestimentoSnapshot,
    Orcamento,
    Receita,
    TransacaoCartao,
)

# Ordem importa por causa das chaves estrangeiras (pais antes dos filhos).
ORDEM = [
    Instituicao,
    Categoria,
    Receita,
    Orcamento,
    Fatura,
    TransacaoCartao,
    DespesaManual,
    Compromisso,
    CompromissoParcela,
    InvestimentoSnapshot,
    InvestimentoMovimento,
    CarteiraHistorico,
]

COLUNAS = {
    cls: [c.name for c in cls.__table__.columns] for cls in ORDEM
}


def main() -> None:
    destino_url = get_db_url()
    if destino_url.startswith("sqlite"):
        print("ERRO: defina DATABASE_URL com o Postgres de destino antes de rodar.")
        print('Ex.: DATABASE_URL="postgresql://user:pass@host/db?sslmode=require" \\')
        print("     .venv/bin/python tools/migrar_para_postgres.py")
        sys.exit(1)

    origem = create_engine(f"sqlite:///{DB_PATH}", future=True)
    destino = create_engine(destino_url, future=True)

    print(f"Origem  (SQLite):  {DB_PATH}")
    print(f"Destino (Postgres): {destino_url.split('@')[-1]}")
    print()

    # Cria o schema no destino.
    Base.metadata.create_all(destino)

    with Session(origem) as s_orig, Session(destino) as s_dest:
        # Checagem de segurança: destino já tem dados?
        ja_tem = s_dest.scalar(select(Categoria).limit(1)) or s_dest.scalar(
            select(Receita).limit(1)
        )
        if ja_tem:
            resp = input("O destino já tem dados. Apagar e recopiar? (digite SIM): ")
            if resp.strip() != "SIM":
                print("Abortado.")
                return
            for cls in reversed(ORDEM):
                s_dest.query(cls).delete()
            s_dest.commit()

        total = 0
        for cls in ORDEM:
            linhas = s_orig.scalars(select(cls)).all()
            for obj in linhas:
                dados = {col: getattr(obj, col) for col in COLUNAS[cls]}
                s_dest.add(cls(**dados))
            s_dest.commit()
            print(f"  {cls.__tablename__}: {len(linhas)} linha(s)")
            total += len(linhas)

        print(f"\nConcluído: {total} linha(s) copiada(s) para o Postgres.")


if __name__ == "__main__":
    main()
