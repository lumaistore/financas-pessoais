"""Conexão com o banco e sessão.

Cria o arquivo SQLite e todas as tabelas na primeira execução.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_db_url
from core.models import Base

_db_url = get_db_url()
# SQLite precisa liberar acesso entre threads do Streamlit; Postgres não.
_connect_args = {"check_same_thread": False} if _db_url.startswith("sqlite") else {}
engine = create_engine(_db_url, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, class_=Session, expire_on_commit=False)


# Colunas adicionadas depois que o banco já existia. SQLite só cria tabelas
# novas em create_all — colunas novas em tabelas existentes precisam de ALTER.
# Formato: (tabela, coluna, definição SQL).
_MIGRACOES_COLUNAS = [
    ("transacoes_cartao", "lumai", "BOOLEAN DEFAULT 0"),
    ("investimento_snapshots", "ticker", "VARCHAR"),
    ("investimento_snapshots", "indexador", "VARCHAR"),
    ("investimento_snapshots", "taxa_indice", "FLOAT"),
    ("investimento_snapshots", "data_aplicacao", "DATE"),
]


def _migrar_colunas() -> None:
    # Só faz sentido no SQLite local (banco antigo a evoluir). No Postgres o
    # create_all já cria todas as colunas, então não há o que migrar.
    if engine.dialect.name != "sqlite":
        return
    insp = inspect(engine)
    tabelas = set(insp.get_table_names())
    with engine.begin() as conn:
        for tabela, coluna, definicao in _MIGRACOES_COLUNAS:
            if tabela not in tabelas:
                continue
            existentes = {c["name"] for c in insp.get_columns(tabela)}
            if coluna not in existentes:
                conn.execute(text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}"))


def init_db() -> None:
    """Cria as tabelas que ainda não existirem e aplica migrações leves."""
    Base.metadata.create_all(engine)
    _migrar_colunas()


@contextmanager
def get_session():
    """Sessão transacional: commit no sucesso, rollback no erro."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
