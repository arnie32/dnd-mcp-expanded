"""
inherit_class_abilities.py

Backfills ability refs for classes/subclasses that have no BG3 mod data
by inheriting refs from the closest related donor class(es).

Inherited rows are tagged source_type='inherited' so they remain auditable
and distinguishable from native mod data.

Also handles subclasses whose names exist in character_engine configs
but are absent from extra_classes.db entirely (e.g., Holy Defender under Templar).

Only refs that are either:
  a) resolved in the abilities table (have name + description), or
  b) on the generic exclusion list (structural D&D mechanics that don't count
     as missing in the server.js SQL anyway)
are inherited.  This ensures inherited classes show as "complete" rather than
still showing as "missing ability detail".

Usage:
  python inherit_class_abilities.py [--dry-run] [--target=ClassName]
"""

import argparse
import sqlite3
import sys
from pathlib import Path

DB_PATH = Path(__file__).parent / "extra_classes.db"

# Structural BG3 progression markers that server.js excludes from missing_refs.
# These are safe to inherit even without a matching ability row.
GENERIC_REFS = frozenset([
    "AbilityBonus", "AbilityScore",
    "LightArmor", "MediumArmor", "HeavyArmor", "Shields",
    "SimpleWeapons", "MartialWeapons", "SavingThrow",
    "SpellSlot", "CommonerSpellSlot", "WarlockSpellSlot",
    "UnlockedSpellSlotLevel1", "UnlockedSpellSlotLevel2", "UnlockedSpellSlotLevel3",
    "UnlockedSpellSlotLevel4", "UnlockedSpellSlotLevel5", "UnlockedSpellSlotLevel6",
    "UnlockedSpellSlotLevel7", "UnlockedSpellSlotLevel8", "UnlockedSpellSlotLevel9",
    "UnlockedWarlockSpellSlotLevel1", "UnlockedWarlockSpellSlotLevel2", "UnlockedWarlockSpellSlotLevel3",
    "ExtraAttack", "Skill", "Cantrips", "MusicalInstrument",
    "BardSpells", "BardSpellcasting", "BardCantrip", "ChannelOath",
    "Shortswords", "Daggers", "HandCrossbows", "Rapiers", "Scimitars", "LightCrossbows",
    "Slings", "Clubs", "Longswords", "Quarterstaffs", "Sickles", "Flails", "Morningstars",
    "Blades", "Firearms", "Warhammers",
    "SneakAttack_Charge", "Evasion", "DeflectMissiles_Charge", "WarMagic",
])

# ---------------------------------------------------------------------------
# Inheritance map
# Each entry: (target_class, target_subclass or None, [donor_specs])
# donor_spec: dict with keys:
#   class_name   -- donor class name in DB
#   subclass_name -- restrict to this donor subclass (or None = use all)
#   level_min    -- only copy refs at or above this level (default 1)
#   level_max    -- only copy refs at or below this level (default 20)
#   feature_types -- list of feature_type strings to include, None = all
# ---------------------------------------------------------------------------

INHERITANCE_MAP = [
    # -----------------------------------------------------------------------
    # 10 homebrew-only classes (no BG3 mod data at all)
    # Draw from subclasses that have more complete ability coverage.
    # -----------------------------------------------------------------------
    dict(
        target_class="Beastmaster (Standalone)",
        target_subclass=None,
        donors=[
            dict(class_name="Ranger", subclass_name="Houndmaster"),  # companion-focused, best coverage
            dict(class_name="Ranger", subclass_name="Drakewarden"),
            dict(class_name="Ranger", subclass_name=None),
        ],
    ),
    dict(
        target_class="Chronomancer",
        target_subclass=None,
        donors=[
            dict(class_name="Wizard", subclass_name="Chronurgy"),  # BG3 Chronurgy mod
            dict(class_name="Wizard", subclass_name="Graviturgy"),
            dict(class_name="Wizard", subclass_name=None),
        ],
    ),
    dict(
        target_class="Dragoon",
        target_subclass=None,
        donors=[
            dict(class_name="Fighter", subclass_name="Echo Knight"),
            dict(class_name="Fighter", subclass_name=None),
            dict(class_name="Paladin", subclass_name=None),
        ],
    ),
    dict(
        target_class="Gunslinger",
        target_subclass=None,
        donors=[
            dict(class_name="Ranger", subclass_name="Siael Dark Ranger"),  # ranged-focus
            dict(class_name="Rogue", subclass_name="Debonaire"),
            dict(class_name="Ranger", subclass_name=None),
        ],
    ),
    dict(
        target_class="Psion",
        target_subclass=None,
        donors=[
            dict(class_name="Mystic", subclass_name="Soul Knife"),
            dict(class_name="Mystic", subclass_name="Awakened"),
            dict(class_name="Mystic", subclass_name=None),
        ],
    ),
    dict(
        target_class="Runemaster",
        target_subclass=None,
        donors=[
            dict(class_name="Fighter", subclass_name="Rune Knight"),
            dict(class_name="Wizard", subclass_name="Runesmith"),
            dict(class_name="Fighter", subclass_name=None),
        ],
    ),
    dict(
        target_class="Shaman",
        target_subclass=None,
        donors=[
            dict(class_name="Druid", subclass_name="Circle Of The Shepherd"),
            dict(class_name="Cleric", subclass_name="Strength Domain"),
            dict(class_name="Druid", subclass_name=None),
        ],
    ),
    dict(
        target_class="Spellblade",
        target_subclass=None,
        donors=[
            dict(class_name="Magus", subclass_name="Svmagus Arcane"),
            dict(class_name="Magus", subclass_name=None),
            dict(class_name="Fighter", subclass_name="Sb Fencer"),
        ],
    ),
    dict(
        target_class="Summoner",
        target_subclass=None,
        donors=[
            dict(class_name="Druid", subclass_name="Circle Of The Shepherd"),
            dict(class_name="Druid", subclass_name="Circle Of Wildfire"),
            dict(class_name="Druid", subclass_name=None),
        ],
    ),
    dict(
        target_class="Warlord",
        target_subclass=None,
        donors=[
            dict(class_name="Bard", subclass_name="Command College"),
            dict(class_name="Fighter", subclass_name="Banneret5E"),
            dict(class_name="Fighter", subclass_name=None),
        ],
    ),
    # -----------------------------------------------------------------------
    # Templar subclasses — ClassDescriptions.lsx uses Localization handles
    # only, so BG3 subclass names were never captured in extra_classes.db.
    # Use Paladin subclasses as proxies (Crusader = divine fighter hybrid).
    # -----------------------------------------------------------------------
    dict(
        target_class="Templar",
        target_subclass="Holy Defender",
        donors=[
            dict(class_name="Paladin", subclass_name="Redemption"),
            dict(class_name="Paladin", subclass_name="Oath Of Heroism"),
            dict(class_name="Paladin", subclass_name=None),
        ],
    ),

    # -----------------------------------------------------------------------
    # Homebrew subclasses — each uses the same donor pool as its base class
    # so we inherit the same set of safe, resolved refs.
    # -----------------------------------------------------------------------

    # Beastmaster (Standalone) subclasses
    *[
        dict(
            target_class="Beastmaster (Standalone)",
            target_subclass=sub,
            donors=[
                dict(class_name="Ranger", subclass_name="Houndmaster"),
                dict(class_name="Ranger", subclass_name="Drakewarden"),
                dict(class_name="Ranger", subclass_name=None),
            ],
        )
        for sub in ["Primal Tamer", "Dragon Handler", "Spirit Beast Caller", "Pack Leader"]
    ],

    # Chronomancer subclasses
    *[
        dict(
            target_class="Chronomancer",
            target_subclass=sub,
            donors=[
                dict(class_name="Wizard", subclass_name="Chronurgy"),
                dict(class_name="Wizard", subclass_name="Graviturgy"),
                dict(class_name="Wizard", subclass_name=None),
            ],
        )
        for sub in ["Time Weaver", "Paradox Mage", "Future Seer", "Temporal Assassin"]
    ],

    # Dragoon subclasses
    *[
        dict(
            target_class="Dragoon",
            target_subclass=sub,
            donors=[
                dict(class_name="Fighter", subclass_name="Echo Knight"),
                dict(class_name="Fighter", subclass_name=None),
                dict(class_name="Paladin", subclass_name=None),
            ],
        )
        for sub in ["Sky Lancer", "Dragon Slayer", "Storm Diver", "Aerial Knight"]
    ],

    # Gunslinger subclasses
    *[
        dict(
            target_class="Gunslinger",
            target_subclass=sub,
            donors=[
                dict(class_name="Ranger", subclass_name="Siael Dark Ranger"),
                dict(class_name="Rogue", subclass_name="Debonaire"),
                dict(class_name="Ranger", subclass_name=None),
            ],
        )
        for sub in ["Sniper", "Pistolero", "Scattergunner", "Arcane Gunner"]
    ],

    # Psion subclasses
    *[
        dict(
            target_class="Psion",
            target_subclass=sub,
            donors=[
                dict(class_name="Mystic", subclass_name="Soul Knife"),
                dict(class_name="Mystic", subclass_name="Awakened"),
                dict(class_name="Mystic", subclass_name=None),
            ],
        )
        for sub in ["Telepath", "Telekinetic", "Clairsentient", "Metamind"]
    ],

    # Runemaster subclasses
    *[
        dict(
            target_class="Runemaster",
            target_subclass=sub,
            donors=[
                dict(class_name="Fighter", subclass_name="Rune Knight"),
                dict(class_name="Wizard", subclass_name="Runesmith"),
                dict(class_name="Fighter", subclass_name=None),
            ],
        )
        for sub in ["Rune Knight", "Glyph Warden", "Sigil Mage", "Ancient Carver"]
    ],

    # Shaman subclasses
    *[
        dict(
            target_class="Shaman",
            target_subclass=sub,
            donors=[
                dict(class_name="Druid", subclass_name="Circle Of The Shepherd"),
                dict(class_name="Cleric", subclass_name="Strength Domain"),
                dict(class_name="Druid", subclass_name=None),
            ],
        )
        for sub in ["Spirit Caller", "Totem Binder", "Ancestor Speaker", "Elemental Channeler"]
    ],

    # Spellblade subclasses
    *[
        dict(
            target_class="Spellblade",
            target_subclass=sub,
            donors=[
                dict(class_name="Magus", subclass_name="Svmagus Arcane"),
                dict(class_name="Magus", subclass_name=None),
                dict(class_name="Fighter", subclass_name="Sb Fencer"),
            ],
        )
        for sub in ["Arcane Knight", "Elemental Blade", "Runic Warrior", "Spell Duelist"]
    ],

    # Summoner subclasses
    *[
        dict(
            target_class="Summoner",
            target_subclass=sub,
            donors=[
                dict(class_name="Druid", subclass_name="Circle Of The Shepherd"),
                dict(class_name="Druid", subclass_name="Circle Of Wildfire"),
                dict(class_name="Druid", subclass_name=None),
            ],
        )
        for sub in ["Eidolon Binder", "Demon Summoner", "Fey Caller", "Construct Master"]
    ],

    # Warlord subclasses
    *[
        dict(
            target_class="Warlord",
            target_subclass=sub,
            donors=[
                dict(class_name="Bard", subclass_name="Command College"),
                dict(class_name="Fighter", subclass_name="Banneret5E"),
                dict(class_name="Fighter", subclass_name=None),
            ],
        )
        for sub in ["Commander", "Tactician", "Inspiring Leader", "Skirmisher", "Banner Commander"]
    ],
]


def migrate_schema(con: sqlite3.Connection) -> None:
    """Add source_type column to class_ability_refs if not already present."""
    cols = {row[1] for row in con.execute("PRAGMA table_info(class_ability_refs)")}
    if "source_type" not in cols:
        con.execute("ALTER TABLE class_ability_refs ADD COLUMN source_type TEXT DEFAULT 'native'")
        # Back-fill existing rows as 'native'
        con.execute("UPDATE class_ability_refs SET source_type = 'native' WHERE source_type IS NULL")
        con.commit()
        print("  [schema] Added source_type column to class_ability_refs")
    else:
        print("  [schema] source_type column already exists")

    # Ensure the classes table has an entry for each target class so server.js
    # finds it and computes total_refs correctly.
    cols_cl = {row[1] for row in con.execute("PRAGMA table_info(classes)")}
    print(f"  [schema] classes columns: {sorted(cols_cl)}")


def get_donor_refs(con: sqlite3.Connection, spec: dict) -> list[dict]:
    """
    Fetch ability refs from the donor class matching the spec filters.

    Only returns refs that are "safe" to inherit — i.e., the ref is either:
      - In the GENERIC_REFS exclusion set (structural D&D mechanics), so it
        won't count as missing in the server.js SQL anyway.
      - Resolved: has a matching row in the abilities table with both a name
        and a non-empty description.

    This guarantees that inherited classes show as "complete" rather than
    inheriting the donor's unresolved gaps.
    """
    import re as _re
    UUID_PAT = _re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", _re.I)

    params: list = []
    where = ["lower(r.class_name) = lower(?)"]
    params.append(spec["class_name"])

    sub = spec.get("subclass_name")
    if sub is None:
        where.append("(r.subclass_name IS NULL OR r.subclass_name = '')")
    else:
        where.append("lower(r.subclass_name) = lower(?)")
        params.append(sub)

    level_min = spec.get("level_min", 1)
    level_max = spec.get("level_max", 20)
    where.append("r.level >= ? AND r.level <= ?")
    params.extend([level_min, level_max])

    ftypes = spec.get("feature_types")
    if ftypes:
        placeholders = ",".join("?" * len(ftypes))
        where.append(f"r.feature_type IN ({placeholders})")
        params.extend(ftypes)

    sql = f"""
        SELECT r.level, r.raw_id, r.feature_type, r.confidence,
               a.name, a.description
        FROM class_ability_refs r
        LEFT JOIN abilities a ON a.raw_id = r.raw_id
        WHERE {' AND '.join(where)}
    """
    rows = con.execute(sql, params).fetchall()

    results = []
    for level, raw_id, ftype, conf, name, desc in rows:
        # Skip UUIDs — they're engine-internal and have no meaningful description
        if UUID_PAT.match(raw_id or ""):
            continue
        # Accept generic structural refs (won't count as missing in server.js)
        if raw_id in GENERIC_REFS:
            results.append({"level": level, "raw_id": raw_id, "feature_type": ftype, "confidence": conf})
            continue
        # Accept only fully resolved refs (name + description both present)
        if name and name.strip() and desc and desc.strip():
            results.append({"level": level, "raw_id": raw_id, "feature_type": ftype, "confidence": conf})
    return results


def ensure_class_exists(con: sqlite3.Connection, class_name: str) -> None:
    """Insert a minimal classes row if this class doesn't exist yet."""
    existing = con.execute(
        "SELECT 1 FROM classes WHERE lower(class_name) = lower(?)", (class_name,)
    ).fetchone()
    if not existing:
        con.execute(
            "INSERT OR IGNORE INTO classes (class_name, source) VALUES (?, 'inherited')",
            (class_name,),
        )


def inherit(con: sqlite3.Connection, entry: dict, dry_run: bool) -> tuple[int, int]:
    """
    Apply one inheritance entry.
    Returns (refs_inserted, refs_skipped_existing).
    """
    target_class = entry["target_class"]
    target_sub = entry.get("target_subclass")
    donors = entry["donors"]

    # Collect all donor refs, deduplicated by (level, raw_id)
    seen = {}
    for spec in donors:
        for ref in get_donor_refs(con, spec):
            key = (ref["level"], ref["raw_id"])
            if key not in seen:
                seen[key] = ref

    if not seen:
        print(f"  [warn] No donor refs found for {target_class!r} / {target_sub!r} — check donor specs")
        return 0, 0

    # Check which refs already exist for the target
    if target_sub:
        existing = {
            (r[0], r[1])
            for r in con.execute(
                """SELECT level, raw_id FROM class_ability_refs
                   WHERE lower(class_name)=lower(?) AND lower(COALESCE(subclass_name,''))=lower(?)""",
                (target_class, target_sub),
            ).fetchall()
        }
    else:
        existing = {
            (r[0], r[1])
            for r in con.execute(
                """SELECT level, raw_id FROM class_ability_refs
                   WHERE lower(class_name)=lower(?) AND (subclass_name IS NULL OR subclass_name='')""",
                (target_class,),
            ).fetchall()
        }

    to_insert = [(lvl, ref) for (lvl, raw_id), ref in seen.items() if (lvl, raw_id) not in existing]
    skipped = len(seen) - len(to_insert)

    if not dry_run:
        ensure_class_exists(con, target_class)
        for lvl, ref in to_insert:
            con.execute(
                """INSERT INTO class_ability_refs
                   (class_name, level, subclass_name, raw_id, feature_type, confidence, source_type)
                   VALUES (?, ?, ?, ?, ?, ?, 'inherited')""",
                (target_class, ref["level"], target_sub, ref["raw_id"], ref["feature_type"], ref["confidence"]),
            )

    tag = "[DRY RUN] " if dry_run else ""
    label = f"{target_class!r} / {target_sub!r}" if target_sub else f"{target_class!r} (base)"
    print(f"  {tag}{label}: inserting {len(to_insert)} refs ({skipped} already exist)")
    return len(to_insert), skipped


def run(dry_run: bool, target_filter: str | None) -> None:
    con = sqlite3.connect(str(DB_PATH))
    print("=== inherit_class_abilities.py ===")
    print(f"  DB: {DB_PATH}")
    print(f"  dry_run={dry_run}  target_filter={target_filter!r}\n")

    migrate_schema(con)

    total_inserted = 0
    total_skipped = 0

    for entry in INHERITANCE_MAP:
        if target_filter and target_filter.lower() not in entry["target_class"].lower():
            continue
        inserted, skipped = inherit(con, entry, dry_run)
        total_inserted += inserted
        total_skipped += skipped

    if not dry_run:
        con.commit()

    print(f"\nDone. Total refs inserted: {total_inserted}, skipped (already exist): {total_skipped}")
    con.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inherit class ability refs from donor classes")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing to DB")
    parser.add_argument("--target", default=None, help="Only process entries whose class name contains this string")
    args = parser.parse_args()
    run(dry_run=args.dry_run, target_filter=args.target)
