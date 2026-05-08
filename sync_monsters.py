#!/usr/bin/env python3
"""
Standalone script to sync all monsters from dnd5eapi.co into local SQLite.

Usage:
    python sync_monsters.py
"""

import json
import sys
import os

# Ensure imports resolve from project root
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from src.monsters.db import open_db
from src.monsters.schema import ensure_schema
from src.monsters.normalizer import normalize_monster
from src.monsters.repository import upsert_monster

import time
import logging
import requests

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

REMOTE_BASE_URL = "https://www.dnd5eapi.co/api/2014"
REQUEST_TIMEOUT = 10


def main() -> int:
    db = open_db()
    ensure_schema(db)

    logger.info("Fetching monster list from dnd5eapi.co …")
    try:
        resp = requests.get(f"{REMOTE_BASE_URL}/monsters", timeout=REQUEST_TIMEOUT)
        resp.raise_for_status()
        monster_list = resp.json().get("results", [])
    except Exception as exc:
        logger.error(f"Failed to fetch monster list: {exc}")
        return 1

    logger.info(f"Found {len(monster_list)} monsters. Starting sync …")
    synced = 0
    errors: list[dict] = []

    for item in monster_list:
        idx = item.get("index", "")
        try:
            r = requests.get(f"{REMOTE_BASE_URL}/monsters/{idx}", timeout=REQUEST_TIMEOUT)
            r.raise_for_status()
            raw = r.json()
            normalized = normalize_monster(raw)
            upsert_monster(db, normalized)
            synced += 1
            if synced % 50 == 0:
                logger.info(f"  … {synced}/{len(monster_list)}")
            time.sleep(0.1)
        except Exception as exc:
            logger.warning(f"Failed {idx}: {exc}")
            errors.append({"index": idx, "error": str(exc)})

    result = {
        "source": "dnd5eapi",
        "source_version": "2014",
        "synced": synced,
        "failed": len(errors),
        "errors": errors,
    }
    print(json.dumps(result, indent=2))
    return 0 if not errors else 1


if __name__ == "__main__":
    sys.exit(main())
