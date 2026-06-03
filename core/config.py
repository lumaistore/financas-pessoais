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
