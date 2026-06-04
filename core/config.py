"""Configuração central: caminhos e segredos lidos do ambiente."""
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
BACKUPS_DIR = DATA_DIR / "backups"
DB_PATH = DATA_DIR / "financas.db"

# Carrega o .env da raiz do projeto (se existir).
load_dotenv(BASE_DIR / ".env")

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


def _ler_secret(chave: str) -> Optional[str]:
    """Lê um segredo de forma robusta, na ordem:
    1) variável de ambiente (`.env` local);
    2) `st.secrets` do Streamlit (deploy na nuvem).
    Leitura em tempo de uso — não no import — para o Streamlit já ter os
    segredos disponíveis. Silencioso fora do Streamlit."""
    valor = os.environ.get(chave)
    if valor:
        return valor
    try:
        import streamlit as st

        valor = st.secrets[chave]
        return str(valor) if valor else None
    except Exception:
        return None


def get_db_url() -> str:
    """URL do banco para o SQLAlchemy.

    Com DATABASE_URL definida (env ou st.secrets), usa o Postgres da nuvem;
    senão, o SQLite local — o app funciona igual na sua máquina.
    """
    url = _ler_secret("DATABASE_URL")
    if url:
        # Provedores costumam dar 'postgres://...'; o SQLAlchemy quer o driver.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url
    return f"sqlite:///{DB_PATH}"


def get_anthropic_key() -> Optional[str]:
    """Chave da API da Anthropic (env local ou st.secrets na nuvem)."""
    return _ler_secret("ANTHROPIC_API_KEY")
