"""MCP tools for D&D monster data with local SQLite storage."""

import json
import logging
import sqlite3
import time
from typing import Any

import requests

from .normalizer import normalize_monster
from .repository import (
    count_monsters,
    get_monster_by_index,
    search_monsters,
    upsert_monster,
)

logger = logging.getLogger(__name__)

REMOTE_BASE_URL = "https://www.dnd5eapi.co/api/2014"
REQUEST_TIMEOUT = 10
SYNC_SLEEP_SECONDS = 0.1


def _fetch_remote_monster(index: str) -> dict:
    response = requests.get(f"{REMOTE_BASE_URL}/monsters/{index}", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def _list_remote_monsters() -> list[dict]:
    response = requests.get(f"{REMOTE_BASE_URL}/monsters", timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json().get("results", [])


def _compact_view(monster: dict) -> dict:
    combat = monster.get("combat", {})
    return {
        "found": True,
        "source": monster.get("source", "local"),
        "index": monster["index"],
        "name": monster["name"],
        "combat": combat,
        "ai_summary": monster.get("ai_summary"),
    }


def register_monster_tools(app: Any, db: sqlite3.Connection) -> None:
    """Register monster MCP tools on the FastMCP app."""

    @app.tool()
    def get_monster(
        index: str,
        allow_remote_fallback: bool = True,
        compact: bool = True,
    ) -> dict:
        """Get a D&D monster by its index slug (e.g. 'goblin', 'adult-red-dragon').

        Checks local SQLite first. If not found and allow_remote_fallback is True,
        fetches from dnd5eapi.co and stores locally for future use.

        During active gameplay set allow_remote_fallback=False to prevent surprise
        network calls.

        Args:
            index: Monster index slug (e.g. 'goblin', 'adult-red-dragon')
            allow_remote_fallback: Whether to fetch from dnd5eapi.co if not in local DB
            compact: Return only combat stats and ai_summary (omit full raw JSON)

        Returns:
            Monster data dict, or {"found": False, "index": index} if not found.
        """
        logger.debug(f"get_monster: {index}, fallback={allow_remote_fallback}")

        local = get_monster_by_index(db, index)
        if local:
            if compact:
                return _compact_view(local)
            return {"found": True, "source": "local", "monster": local}

        if not allow_remote_fallback:
            return {"found": False, "index": index}

        try:
            raw = _fetch_remote_monster(index)
        except Exception as exc:
            return {"found": False, "index": index, "error": str(exc)}

        normalized = normalize_monster(raw)
        upsert_monster(db, normalized)
        normalized["index"] = normalized.pop("index_key")

        if compact:
            return _compact_view(normalized)
        return {"found": True, "source": "remote", "monster": normalized}

    @app.tool()
    def search_monsters_tool(
        query: str | None = None,
        cr_min: float | None = None,
        cr_max: float | None = None,
        limit: int = 20,
    ) -> dict:
        """Search monsters in the local database by name and/or challenge rating.

        All filters are optional and combinable.

        Args:
            query: Partial name match (case-insensitive)
            cr_min: Minimum challenge rating (inclusive)
            cr_max: Maximum challenge rating (inclusive)
            limit: Maximum number of results (default 20)

        Returns:
            Dict with count and list of compact monster summaries.
        """
        logger.debug(f"search_monsters: query={query}, cr={cr_min}-{cr_max}, limit={limit}")

        monsters = search_monsters(db, query=query, cr_min=cr_min, cr_max=cr_max, limit=limit)

        summaries = [
            {
                "index": m["index"],
                "name": m["name"],
                "challenge_rating": m["combat"].get("challenge_rating", 0),
                "armor_class": m["combat"].get("armor_class", 0),
                "hit_points": m["combat"].get("hit_points", 0),
                "type": m.get("type"),
                "size": m.get("size"),
                "summary": m.get("ai_summary", {}).get("compact_stat_block"),
            }
            for m in monsters
        ]

        return {"count": len(summaries), "monsters": summaries}

    @app.tool()
    def refresh_monster(index: str) -> dict:
        """Force re-fetch a monster from dnd5eapi.co and update the local database.

        Use this when you want the latest data for a specific monster.

        Args:
            index: Monster index slug (e.g. 'goblin')

        Returns:
            Dict with refreshed monster index and name.
        """
        logger.debug(f"refresh_monster: {index}")

        try:
            raw = _fetch_remote_monster(index)
        except Exception as exc:
            return {"refreshed": False, "index": index, "error": str(exc)}

        normalized = normalize_monster(raw)
        upsert_monster(db, normalized)

        return {
            "refreshed": True,
            "index": normalized["index_key"],
            "name": normalized["name"],
        }

    @app.tool()
    def sync_monsters_from_dnd5eapi() -> dict:
        """Sync all monsters from dnd5eapi.co into the local database.

        Fetches the full monster list, then retrieves and stores each monster.
        Use this once during setup or to refresh all data. Includes a 100ms
        delay between requests to be a polite API consumer.

        Returns:
            Dict with synced count, failed count, and any error details.
        """
        logger.info("sync_monsters_from_dnd5eapi: starting full sync")

        try:
            monster_list = _list_remote_monsters()
        except Exception as exc:
            return {"synced": 0, "failed": 0, "errors": [{"error": str(exc)}]}

        synced = 0
        errors: list[dict] = []

        for item in monster_list:
            idx = item.get("index", "")
            try:
                raw = _fetch_remote_monster(idx)
                normalized = normalize_monster(raw)
                upsert_monster(db, normalized)
                synced += 1
                time.sleep(SYNC_SLEEP_SECONDS)
            except Exception as exc:
                logger.warning(f"sync failed for {idx}: {exc}")
                errors.append({"index": idx, "error": str(exc)})

        logger.info(f"sync complete: {synced} synced, {len(errors)} failed")
        return {
            "source": "dnd5eapi",
            "source_version": "2014",
            "synced": synced,
            "failed": len(errors),
            "errors": errors,
        }
