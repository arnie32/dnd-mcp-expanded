"""Repository: CRUD operations for monster_templates SQLite table."""

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any


def _row_to_dict(row: sqlite3.Row) -> dict:
    d = dict(row)
    d["combat"] = json.loads(d.pop("combat_json", "{}"))
    d["ai_summary"] = json.loads(d.pop("ai_summary_json") or "{}")
    d["raw"] = json.loads(d.pop("raw_json", "{}"))
    # rename index_key back to index for external consumers
    d["index"] = d.pop("index_key")
    return d


def get_monster_by_index(conn: sqlite3.Connection, index: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM monster_templates WHERE index_key = ?", (index,)
    ).fetchone()
    return _row_to_dict(row) if row else None


def upsert_monster(conn: sqlite3.Connection, normalized: dict) -> None:
    now = datetime.now(timezone.utc).isoformat()
    conn.execute(
        """
        INSERT INTO monster_templates (
            index_key, name, type, size, alignment, challenge_rating,
            source, source_version, url,
            combat_json, ai_summary_json, raw_json,
            created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(index_key) DO UPDATE SET
            name          = excluded.name,
            type          = excluded.type,
            size          = excluded.size,
            alignment     = excluded.alignment,
            challenge_rating = excluded.challenge_rating,
            source        = excluded.source,
            source_version = excluded.source_version,
            url           = excluded.url,
            combat_json   = excluded.combat_json,
            ai_summary_json = excluded.ai_summary_json,
            raw_json      = excluded.raw_json,
            updated_at    = excluded.updated_at
        """,
        (
            normalized["index_key"],
            normalized["name"],
            normalized.get("type"),
            normalized.get("size"),
            normalized.get("alignment"),
            normalized["challenge_rating"],
            normalized.get("source", "dnd5eapi"),
            normalized.get("source_version", "2014"),
            normalized.get("url"),
            json.dumps(normalized["combat"]),
            json.dumps(normalized.get("ai_summary") or {}),
            json.dumps(normalized["raw"]),
            normalized.get("created_at", now),
            now,
        ),
    )
    conn.commit()


def search_monsters(
    conn: sqlite3.Connection,
    query: str | None = None,
    cr_min: float | None = None,
    cr_max: float | None = None,
    limit: int = 20,
) -> list[dict]:
    conditions: list[str] = []
    values: list[Any] = []

    if query:
        conditions.append("name LIKE ?")
        values.append(f"%{query}%")

    if cr_min is not None:
        conditions.append("challenge_rating >= ?")
        values.append(cr_min)

    if cr_max is not None:
        conditions.append("challenge_rating <= ?")
        values.append(cr_max)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    values.append(limit)

    rows = conn.execute(
        f"""
        SELECT * FROM monster_templates
        {where}
        ORDER BY challenge_rating ASC, name ASC
        LIMIT ?
        """,
        values,
    ).fetchall()

    return [_row_to_dict(r) for r in rows]


def count_monsters(conn: sqlite3.Connection) -> int:
    row = conn.execute("SELECT COUNT(*) FROM monster_templates").fetchone()
    return row[0] if row else 0
