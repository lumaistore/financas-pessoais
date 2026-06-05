"""Conexão com o banco e sessão.

Cria o arquivo SQLite e todas as tabelas na primeira execução.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from core.config import get_db_url
from core.models import Base

# Engine criado de forma PREGUIÇOSA (na primeira utilização), não no import.
# Assim, na nuvem, ele só é montado quando o Streamlit já disponibilizou os
# segredos (DATABASE_URL) — evitando cair no SQLite vazio por engano.
_engine = None
_SessionLocal = None


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        url = get_db_url()
        # SQLite precisa liberar acesso entre threads; Postgres não.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url, future=True, connect_args=connect_args, pool_pre_ping=True
        )
        _SessionLocal = sessionmaker(bind=_engine, class_=Session, expire_on_commit=False)
    return _engine


def info_banco() -> dict:
    """Diagnóstico: tipo de banco e se está conectando (sem expor segredos)."""
    eng = get_engine()
    return {"dialeto": eng.dialect.name, "host": (eng.url.host or "local")}


def _migrar_colunas() -> None:
    """Auto-migração: para cada tabela já existente, adiciona as colunas do
    modelo que ainda não existem no banco, com o tipo certo para o dialeto
    (SQLite ou Postgres). Cobre tanto o banco local antigo quanto o Postgres
    da nuvem (que tem a tabela antiga). Colunas novas devem ser anuláveis."""
    eng = get_engine()
    insp = inspect(eng)
    existentes_tabelas = set(insp.get_table_names())
    prep = eng.dialect.identifier_preparer
    with eng.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            if tabela.name not in existentes_tabelas:
                continue  # tabela nova já criada inteira por create_all
            cols_db = {c["name"] for c in insp.get_columns(tabela.name)}
            for coluna in tabela.columns:
                if coluna.name in cols_db:
                    continue
                tipo = coluna.type.compile(dialect=eng.dialect)
                conn.execute(
                    text(
                        f"ALTER TABLE {prep.format_table(tabela)} "
                        f"ADD COLUMN {prep.format_column(coluna)} {tipo}"
                    )
                )


def _sincronizar_sequencias_postgres() -> None:
    """Após migrar dados (com IDs explícitos) para o Postgres, os contadores de
    ID (sequences) ficam atrasados, causando IntegrityError em novos inserts.
    Aqui realinhamos cada sequence para MAX(id)+1. Idempotente e barato."""
    eng = get_engine()
    if eng.dialect.name != "postgresql":
        return
    with eng.begin() as conn:
        for tabela in Base.metadata.sorted_tables:
            if "id" not in tabela.columns:
                continue
            nome = tabela.name
            try:
                conn.execute(
                    text(
                        f"SELECT setval(pg_get_serial_sequence('{nome}', 'id'), "
                        f"COALESCE((SELECT MAX(id) FROM {nome}), 0) + 1, false)"
                    )
                )
            except Exception:
                pass  # tabela sem sequence/serial — ignora


_inicializado = False


def init_db() -> None:
    """Cria tabelas e aplica migrações — uma única vez por processo.

    Como cada página chama init_db(), o controle `_inicializado` evita refazer
    introspecção + sync de sequences a cada navegação (custoso com banco na
    nuvem). Roda só na primeira vez; depois é praticamente instantâneo."""
    global _inicializado
    if _inicializado:
        return
    Base.metadata.create_all(get_engine())
    _migrar_colunas()
    _sincronizar_sequencias_postgres()
    _inicializado = True


@contextmanager
def get_session():
    """Sessão transacional: commit no sucesso, rollback no erro."""
    get_engine()  # garante engine + sessionmaker criados
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
