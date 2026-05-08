"""Database schema for monster_templates."""

import sqlite3

CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS monster_templates (
    index_key   TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    type        TEXT,
    size        TEXT,
    alignment   TEXT,
    challenge_rating REAL NOT NULL DEFAULT 0,
    source      TEXT NOT NULL DEFAULT 'dnd5eapi',
    source_version TEXT NOT NULL DEFAULT '2014',
    url         TEXT,
    combat_json TEXT NOT NULL,
    ai_summary_json TEXT,
    raw_json    TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    updated_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_monster_cr
    ON monster_templates (challenge_rating);

CREATE INDEX IF NOT EXISTS idx_monster_name
    ON monster_templates (name COLLATE NOCASE);
"""


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables and indexes if they do not already exist."""
    conn.executescript(CREATE_TABLES)
    conn.commit()
