#!/usr/bin/env python3
"""
enrich_extra_classes_db.py

Post-processes extra_classes.db by matching null-name ability raw_ids
against the dnd5eapi.co spells AND features APIs, then patching in the
canonical D&D name and description.

Run once after build_extra_classes_db.py (and re-run after any rebuild):
    python enrich_extra_classes_db.py

A local cache (dnd5e_enrich_cache.json) stores API responses so
subsequent runs don't re-fetch unchanged data.
"""

import json
import re
import sqlite3
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

DB_PATH = Path(__file__).parent / "extra_classes.db"
CACHE_FILE = Path(__file__).parent / "dnd5e_enrich_cache.json"
API_BASE = "https://www.dnd5eapi.co/api"
REQUEST_DELAY = 0.15  # seconds between API calls to be polite


# ── slug helpers ─────────────────────────────────────────────────────────────

# BG3 verb prefixes used for spell/ability IDs — strip these to get the D&D name
_BG3_SPELL_PREFIXES = (
    "Shout_", "Target_", "Zone_", "Projectile_", "Rush_",
    "Throw_", "Teleport_", "Wall_", "Summon_",
    "Scroll_", "ScrollAndStaff_", "Staff_",
)

# BG3 suffixes that don't carry D&D meaning — strip these before slug lookup
_SUFFIX_RE = re.compile(
    r"(Unlock|Resource|Use|Charges?|Points?|Passive\d*|Tracker|Visuals?|"
    r"Logic|Technical|Toggle|Check|Reset|Remover|Lock|Start|End|"
    r"Setup|Message|Baseline|Dummy|Restore|Container|Scaling|"
    r"Level\d+|Replenish|Impede|Failsafe|Baseline|Identifier)$"
)

# Class prefixes that BG3 prepends but the API doesn't use
_CLASS_PREFIXES = (
    "Cleric", "Bard", "Warlock", "Wizard", "Fighter", "Rogue",
    "Monk", "Druid", "Paladin", "Ranger", "Sorcerer", "Barbarian",
    "Artificer", "5e",
)


def _camel_to_kebab(s: str) -> str:
    s = re.sub(r"([a-z])([A-Z])", r"\1-\2", s)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1-\2", s)
    s = re.sub(r"[_\s]+", "-", s)
    return s.lower()


def candidate_slugs(raw_id: str) -> list[str]:
    """Return candidate dnd5eapi.co slugs for a BG3 raw_id."""
    candidates = []

    def add(s: str) -> None:
        slug = _camel_to_kebab(s)
        if slug and slug not in candidates:
            candidates.append(slug)

    add(raw_id)

    stripped = _SUFFIX_RE.sub("", raw_id)
    if stripped != raw_id:
        add(stripped)

    for prefix in _CLASS_PREFIXES:
        if raw_id.startswith(prefix):
            rest = raw_id[len(prefix):]
            add(rest)
            rest_s = _SUFFIX_RE.sub("", rest)
            if rest_s != rest:
                add(rest_s)

    # BG3 verb-prefixed spell IDs: Target_Fireball → fireball,
    # Projectile_AcidArrow → acid-arrow, etc.
    for prefix in _BG3_SPELL_PREFIXES:
        if raw_id.startswith(prefix):
            rest = raw_id[len(prefix):]
            # Strip trailing digits/version tags: _2e, _2, _Greater, _Improved
            rest = re.sub(r"_?\d+e?$", "", rest)
            rest = re.sub(
                r"_(Greater|Lesser|Improved|Scroll|Staff|Container|Upgrade)$",
                "", rest, flags=re.I
            )
            add(rest)
            break

    return candidates


# ── API helpers ───────────────────────────────────────────────────────────────

def _get(url: str) -> dict | list | None:
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"  [HTTP {e.code}] {url}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  [ERR] {url}: {e}", file=sys.stderr)
        return None


def fetch_index(endpoint: str) -> dict[str, str]:
    """Return slug→name mapping for a top-level API endpoint."""
    data = _get(f"{API_BASE}/{endpoint}?limit=500")
    if not data:
        return {}
    results = data.get("results", [])
    return {item["index"]: item["name"] for item in results}


def fetch_detail(endpoint: str, index: str) -> dict | None:
    time.sleep(REQUEST_DELAY)
    return _get(f"{API_BASE}/{endpoint}/{index}")


def desc_from_detail(detail: dict) -> str:
    """Extract plain-text description from an API detail response."""
    parts = detail.get("desc", [])
    if isinstance(parts, list):
        return " ".join(parts)
    return str(parts)


# ── cache ─────────────────────────────────────────────────────────────────────

def load_cache() -> dict:
    if CACHE_FILE.exists():
        with open(CACHE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ── match + enrich ────────────────────────────────────────────────────────────

def build_api_lookup(cache: dict) -> dict[str, tuple[str, str, str]]:
    """
    Returns {slug: (name, description, source_endpoint)} for all
    spells and features from the API (cached).
    """
    lookup: dict[str, tuple[str, str, str]] = {}

    for endpoint in ("spells", "features"):
        index_key = f"__index_{endpoint}"
        if index_key not in cache:
            print(f"  Fetching {endpoint} index ...", flush=True)
            cache[index_key] = fetch_index(endpoint)
            save_cache(cache)

        for slug, name in cache[index_key].items():
            if slug not in lookup:
                lookup[slug] = (name, "", endpoint)

    return lookup


def resolve_raw_id(raw_id: str, lookup: dict, cache: dict) -> tuple[str, str, str] | None:
    """
    Return (name, description, endpoint) if raw_id matches an API entry.
    Tries all candidate slugs.  Fetches description on first match.
    """
    for endpoint in ("spells", "features"):
        index_key = f"__index_{endpoint}"
        index = cache.get(index_key, {})

        for slug in candidate_slugs(raw_id):
            if slug in index:
                # Fetch detail if not cached
                detail_key = f"{endpoint}/{slug}"
                if detail_key not in cache:
                    print(f"    Fetching {detail_key} ...", flush=True)
                    detail = fetch_detail(endpoint, slug)
                    cache[detail_key] = detail or {}
                    save_cache(cache)

                detail = cache.get(detail_key, {})
                if detail:
                    name = detail.get("name", index[slug])
                    desc = desc_from_detail(detail)
                    return name, desc, endpoint
    return None


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    if not DB_PATH.exists():
        print(f"ERROR: database not found at {DB_PATH}", file=sys.stderr)
        print("Run build_extra_classes_db.py first.", file=sys.stderr)
        return 1

    print("Loading API index cache ...")
    cache = load_cache()

    print("Building dnd5eapi.co lookup ...")
    lookup = build_api_lookup(cache)
    print(f"  {len(lookup)} entries in API lookup (spells + features)")

    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row

    # Collect all unique null-name raw_ids (named, not UUID)
    uuid_pat = re.compile(
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I
    )

    # Case A: in abilities table, name is null
    in_table_null = {
        r["raw_id"]
        for r in conn.execute(
            "SELECT DISTINCT raw_id FROM abilities WHERE name IS NULL"
        ).fetchall()
        if not uuid_pat.match(r["raw_id"])
    }

    # Case B: referenced in class_ability_refs but not in abilities table
    not_in_table = {
        r["raw_id"]
        for r in conn.execute(
            "SELECT DISTINCT ar.raw_id FROM class_ability_refs ar"
            " LEFT JOIN abilities a ON ar.raw_id=a.raw_id WHERE a.raw_id IS NULL"
        ).fetchall()
        if not uuid_pat.match(r["raw_id"])
    }

    # Case C: items stored inside SpellList/PassiveList JSON that have no abilities row
    spell_item_null: set[str] = set()
    for (items_json,) in conn.execute(
        "SELECT items FROM abilities WHERE items IS NOT NULL"
    ).fetchall():
        try:
            items = json.loads(items_json)
        except (json.JSONDecodeError, TypeError):
            continue
        for item_id in items:
            if uuid_pat.match(item_id):
                continue
            existing = conn.execute(
                "SELECT name FROM abilities WHERE raw_id=?", (item_id,)
            ).fetchone()
            if existing is None or existing["name"] is None:
                spell_item_null.add(item_id)

    all_candidates = in_table_null | not_in_table | spell_item_null
    print(f"\nResolving {len(all_candidates)} named null-ability raw_ids "
          f"({len(spell_item_null)} from SpellList items) ...")

    matched_in_table = 0
    matched_inserted = 0
    no_match = 0

    for raw_id in sorted(all_candidates):
        result = resolve_raw_id(raw_id, lookup, cache)
        if result is None:
            no_match += 1
            continue

        name, desc, endpoint = result
        source = f"dnd5eapi.co/{endpoint}"

        if raw_id in in_table_null:
            conn.execute(
                "UPDATE abilities SET name=?, description=?, source_mod=? WHERE raw_id=?",
                (name, desc or None, source, raw_id),
            )
            matched_in_table += 1
        else:
            # Insert a minimal abilities row sourced from the API
            conn.execute(
                "INSERT OR IGNORE INTO abilities"
                " (raw_id, name, description, type, source_mod) VALUES (?,?,?,?,?)",
                (raw_id, name, desc or None, endpoint.rstrip("s"), source),
            )
            # Also add to FTS
            conn.execute(
                "INSERT INTO abilities_fts (raw_id, name, description) VALUES (?,?,?)",
                (raw_id, name, desc or ""),
            )
            matched_inserted += 1

        print(f"  [match] {raw_id} -> '{name}' ({endpoint})")

    conn.commit()
    save_cache(cache)

    # Report null rate against class_ability_refs
    total_refs = conn.execute("SELECT count(*) FROM class_ability_refs").fetchone()[0]
    null_refs = conn.execute(
        "SELECT count(*) FROM class_ability_refs ar"
        " LEFT JOIN abilities a ON ar.raw_id=a.raw_id WHERE a.name IS NULL"
    ).fetchone()[0]

    print(f"\nResults:")
    print(f"  Updated (in-table):  {matched_in_table}")
    print(f"  Inserted (new rows): {matched_inserted}")
    print(f"  No match:            {no_match}")
    print(f"  Total candidates:    {len(all_candidates)}")
    print(f"  Null rate (class refs): {null_refs}/{total_refs} ({100*null_refs//total_refs}%)")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
