"""SQLite connection helper for the monster_templates database."""

import sqlite3
from pathlib import Path

DB_FILENAME = "monster_templates.db"


def open_db(path: str | Path | None = None) -> sqlite3.Connection:
    """Open (or create) the monster_templates SQLite database.

    By default the database is placed at the project root
    (two directories above this file: src/monsters/db.py → root).
    """
    if path is None:
        path = Path(__file__).parent.parent.parent / DB_FILENAME
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn
