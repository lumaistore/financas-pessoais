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


def _espelhar_secrets_do_streamlit() -> None:
    """Na nuvem (Streamlit Cloud) os segredos chegam via st.secrets. Copia-os
    para variáveis de ambiente, para o resto do código (e o SDK da Anthropic)
    enxergarem do mesmo jeito que no .env local. Silencioso fora do Streamlit."""
    try:
        import streamlit as st
    except Exception:
        return
    for chave in ("DATABASE_URL", "ANTHROPIC_API_KEY"):
        if os.environ.get(chave):
            continue
        try:
            valor = st.secrets[chave]
        except Exception:
            valor = None
        if valor:
            os.environ[chave] = str(valor)


_espelhar_secrets_do_streamlit()

DATA_DIR.mkdir(exist_ok=True)
UPLOADS_DIR.mkdir(exist_ok=True)


def get_db_url() -> str:
    """URL do banco para o SQLAlchemy.

    Se a variável de ambiente DATABASE_URL estiver definida (deploy na nuvem,
    ex.: Postgres do Neon), usa ela. Caso contrário, usa o SQLite local — assim
    o app funciona igual na sua máquina, sem nenhuma mudança.
    """
    url = os.environ.get("DATABASE_URL")
    if url:
        # Provedores costumam dar 'postgres://...'; o SQLAlchemy quer o driver.
        if url.startswith("postgres://"):
            url = "postgresql+psycopg2://" + url[len("postgres://"):]
        elif url.startswith("postgresql://"):
            url = "postgresql+psycopg2://" + url[len("postgresql://"):]
        return url
    return f"sqlite:///{DB_PATH}"


def get_anthropic_key() -> Optional[str]:
    """Chave da API da Anthropic, sempre via variável de ambiente."""
    return os.environ.get("ANTHROPIC_API_KEY")
