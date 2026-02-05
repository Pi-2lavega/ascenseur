"""Connexion SQLite et exécution des migrations."""
from __future__ import annotations

import sqlite3
from pathlib import Path
from .config import DB_PATH, SQL_DIR, DATA_DIR


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Ouvre une connexion SQLite avec les pragmas adaptés."""
    path = db_path or DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def run_migrations(conn: sqlite3.Connection) -> None:
    """Exécute tous les fichiers SQL dans sql/ par ordre alphabétique."""
    sql_files = sorted(SQL_DIR.glob("*.sql"))
    for sql_file in sql_files:
        script = sql_file.read_text(encoding="utf-8")
        conn.executescript(script)
    conn.commit()


def init_db(db_path: Path | None = None) -> sqlite3.Connection:
    """Initialise la base : crée le fichier, exécute les migrations."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = get_connection(db_path)
    run_migrations(conn)
    return conn


def table_count(conn: sqlite3.Connection, table: str) -> int:
    """Retourne le nombre de lignes d'une table."""
    row = conn.execute(f"SELECT COUNT(*) FROM [{table}]").fetchone()
    return row[0]
