"""Backup do banco de dados local (Fase 11).

Copia o arquivo SQLite para data/backups/ com data e hora no nome. Tudo fica
na própria máquina — é só uma cópia de segurança dos seus dados.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from typing import List

from core.config import BACKUPS_DIR, DB_PATH


def criar_backup() -> str:
    """Cria uma cópia do banco com timestamp. Retorna o caminho do backup."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    carimbo = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = BACKUPS_DIR / f"financas_{carimbo}.db"
    shutil.copy2(DB_PATH, destino)
    return str(destino)


def listar_backups() -> List[dict]:
    """Backups existentes, do mais recente para o mais antigo."""
    if not BACKUPS_DIR.exists():
        return []
    arquivos = sorted(BACKUPS_DIR.glob("financas_*.db"), reverse=True)
    return [
        {
            "nome": f.name,
            "tamanho_kb": round(f.stat().st_size / 1024, 1),
            "modificado": datetime.fromtimestamp(f.stat().st_mtime),
        }
        for f in arquivos
    ]
