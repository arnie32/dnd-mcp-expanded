#!/usr/bin/env python3
"""
Build the extra_classes SQLite database from BG3 mod JSON files.

Run once (and again whenever the source JSON files are regenerated):
    python build_extra_classes_db.py

Source files (expected in DATA_DIR):
  - dnd_classes_expanded_with_levels.json   class metadata + feature strings
  - bg3_spells_abilities_by_class.json      per-class per-level ability refs
  - bg3_ability_descriptions.json           ability mechanical details
"""

import importlib
import json
import sqlite3
import sys
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
DB_PATH = Path(__file__).parent / "extra_classes.db"

CLASSES_JSON = DATA_DIR / "dnd_classes_expanded_with_levels.json"
ABILITIES_BY_CLASS_JSON = DATA_DIR / "bg3_spells_abilities_by_class.json"
ABILITY_DESCRIPTIONS_JSON = DATA_DIR / "bg3_ability_descriptions.json"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

DDL = """
DROP TABLE IF EXISTS abilities_fts;
DROP TABLE IF EXISTS class_ability_refs;
DROP TABLE IF EXISTS class_features;
DROP TABLE IF EXISTS abilities;
DROP TABLE IF EXISTS classes;

CREATE TABLE classes (
    class_name          TEXT PRIMARY KEY,
    role                TEXT,
    tags                TEXT,
    ruleset             TEXT,
    is_official         INTEGER,
    source              TEXT,
    source_mods         TEXT,
    subclasses          TEXT,
    subclass_gain_level INTEGER,
    skill_options       TEXT,
    primary_stats       TEXT,
    proficiencies       TEXT
);

CREATE TABLE class_features (
    class_name    TEXT NOT NULL,
    level         INTEGER NOT NULL,
    subclass_name TEXT,
    features      TEXT,
    PRIMARY KEY (class_name, level, subclass_name)
);

CREATE INDEX idx_cf_class_level ON class_features (class_name, level);

CREATE TABLE class_ability_refs (
    class_name    TEXT NOT NULL,
    level         INTEGER NOT NULL,
    subclass_name TEXT,
    raw_id        TEXT NOT NULL,
    feature_type  TEXT,
    confidence    TEXT
);

CREATE INDEX idx_car_class ON class_ability_refs (class_name);
CREATE INDEX idx_car_class_level ON class_ability_refs (class_name, level);
CREATE INDEX idx_car_raw_id ON class_ability_refs (raw_id);

CREATE TABLE abilities (
    raw_id              TEXT PRIMARY KEY,
    name                TEXT,
    description         TEXT,
    extra_description   TEXT,
    type                TEXT,
    source_mod          TEXT,
    spell_properties    TEXT,
    tooltip_damage      TEXT,
    damage_type         TEXT,
    level               TEXT,
    spell_school        TEXT,
    spell_flags         TEXT,
    verbal_intent       TEXT,
    use_costs           TEXT,
    cooldown            TEXT,
    range               TEXT,
    area_radius         TEXT,
    target_radius       TEXT,
    shape               TEXT,
    angle               TEXT,
    maximum_targets     TEXT,
    target_conditions   TEXT,
    cycle_conditions    TEXT,
    spell_roll          TEXT,
    tooltip_attack_save TEXT,
    description_params  TEXT,
    boosts              TEXT,
    stats_functors      TEXT,
    projectile_count    TEXT,
    spell_success       TEXT,
    spell_fail          TEXT,
    items               TEXT,
    using_ref           TEXT
);

CREATE VIRTUAL TABLE abilities_fts USING fts5(
    raw_id      UNINDEXED,
    name,
    description
);
"""

ABILITIES_INSERT = (
    "INSERT OR REPLACE INTO abilities VALUES ("
    + ",".join(["?"] * 33)
    + ")"
)


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def load_classes(conn: sqlite3.Connection, data: dict) -> None:
    classes = data.get("classes", {})
    class_rows = []
    feature_rows = []

    for class_name, cls in classes.items():
        class_rows.append((
            class_name,
            cls.get("role"),
            json.dumps(cls.get("tags", [])),
            cls.get("ruleset"),
            int(bool(cls.get("is_official", False))),
            cls.get("source"),
            json.dumps([]),          # source_mods filled in by load_ability_refs
            json.dumps(cls.get("subclasses", [])),
            cls.get("subclass_gain_level"),
            json.dumps(cls.get("skill_options", [])),
            json.dumps(cls.get("primary_stats", [])),
            json.dumps(cls.get("proficiencies", {})),
        ))

        for level_str, features in cls.get("class_features_by_level", {}).items():
            feature_rows.append((class_name, int(level_str), None, json.dumps(features)))

        for sub_name, sub_data in cls.get("subclass_features_by_level", {}).items():
            for level_str, features in sub_data.items():
                feature_rows.append((class_name, int(level_str), sub_name, json.dumps(features)))

    conn.executemany(
        "INSERT OR REPLACE INTO classes VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", class_rows
    )
    conn.executemany(
        "INSERT OR REPLACE INTO class_features"
        " (class_name, level, subclass_name, features) VALUES (?,?,?,?)",
        feature_rows,
    )
    print(f"  classes: {len(class_rows)} classes, {len(feature_rows)} feature rows")


def load_ability_refs(conn: sqlite3.Connection, data: dict) -> None:
    classes = data.get("classes", {})
    ref_rows = []

    for class_name, cls in classes.items():
        source_mods = cls.get("source_mods", [])
        conn.execute(
            "UPDATE classes SET source_mods = ? WHERE class_name = ?",
            (json.dumps(source_mods), class_name),
        )

        for level_str, level_data in cls.get("spells_by_level", {}).items():
            level = int(level_str)
            for feature_type, features in level_data.items():
                if not isinstance(features, list):
                    continue
                for feat in features:
                    raw_id = feat.get("raw_id") if isinstance(feat, dict) else str(feat)
                    if raw_id:
                        ref_rows.append((
                            class_name,
                            level,
                            None,
                            raw_id,
                            feature_type,
                            feat.get("confidence") if isinstance(feat, dict) else None,
                        ))

        for sub_name, sub_data in cls.get("subclasses", {}).items():
            for level_str, level_data in sub_data.get("spells_by_level", {}).items():
                level = int(level_str)
                for feature_type, features in level_data.items():
                    if not isinstance(features, list):
                        continue
                    for feat in features:
                        raw_id = feat.get("raw_id") if isinstance(feat, dict) else str(feat)
                        if raw_id:
                            ref_rows.append((
                                class_name,
                                level,
                                sub_name,
                                raw_id,
                                feature_type,
                                feat.get("confidence") if isinstance(feat, dict) else None,
                            ))

    conn.executemany(
        "INSERT INTO class_ability_refs VALUES (?,?,?,?,?,?)", ref_rows
    )
    print(f"  ability refs: {len(ref_rows)} rows")


def load_abilities(conn: sqlite3.Connection, data: dict) -> None:
    entries = data.get("entries", {})
    ability_rows = []
    fts_rows = []

    for raw_id, entry in entries.items():
        ability_rows.append((
            raw_id,
            entry.get("name"),
            entry.get("description"),
            entry.get("extra_description"),
            entry.get("type"),
            entry.get("source_mod"),
            entry.get("SpellProperties"),
            entry.get("TooltipDamageList"),
            entry.get("DamageType"),
            entry.get("Level"),
            entry.get("SpellSchool"),
            entry.get("SpellFlags"),
            entry.get("VerbalIntent"),
            entry.get("UseCosts"),
            entry.get("Cooldown"),
            entry.get("Range"),
            entry.get("AreaRadius"),
            entry.get("TargetRadius"),
            entry.get("Shape"),
            entry.get("Angle"),
            entry.get("MaximumTargets"),
            entry.get("TargetConditions"),
            entry.get("CycleConditions"),
            entry.get("SpellRoll"),
            entry.get("TooltipAttackSave"),
            entry.get("DescriptionParams"),
            entry.get("Boosts"),
            entry.get("StatsFunctors"),
            entry.get("ProjectileCount"),
            entry.get("SpellSuccess"),
            entry.get("SpellFail"),
            json.dumps(entry["items"]) if "items" in entry else None,
            entry.get("using"),
        ))

        name = entry.get("name") or ""
        desc = entry.get("description") or ""
        if name or desc:
            fts_rows.append((raw_id, name, desc))

    conn.executemany(ABILITIES_INSERT, ability_rows)
    conn.executemany(
        "INSERT INTO abilities_fts (raw_id, name, description) VALUES (?,?,?)", fts_rows
    )
    print(f"  abilities: {len(ability_rows)} entries, {len(fts_rows)} indexed for FTS")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    for path in (CLASSES_JSON, ABILITIES_BY_CLASS_JSON, ABILITY_DESCRIPTIONS_JSON):
        if not path.exists():
            print(f"ERROR: source file not found: {path}", file=sys.stderr)
            return 1

    print(f"Building {DB_PATH} ...")

    conn = sqlite3.connect(str(DB_PATH))

    print("Creating schema ...")
    conn.executescript(DDL)

    print("Loading classes ...")
    with open(CLASSES_JSON, encoding="utf-8") as f:
        load_classes(conn, json.load(f))

    print("Loading ability refs ...")
    with open(ABILITIES_BY_CLASS_JSON, encoding="utf-8") as f:
        load_ability_refs(conn, json.load(f))

    print("Loading ability descriptions (this may take a moment) ...")
    with open(ABILITY_DESCRIPTIONS_JSON, encoding="utf-8") as f:
        load_abilities(conn, json.load(f))

    conn.commit()
    conn.close()

    size_mb = DB_PATH.stat().st_size / 1_048_576
    print(f"\nDone. Database written to: {DB_PATH} ({size_mb:.1f} MB)")

    # Run dnd5e API enrichment to fill in standard D&D names/descriptions
    print("\nRunning dnd5e API enrichment ...")
    try:
        import enrich_extra_classes_db
        importlib.reload(enrich_extra_classes_db)
        enrich_extra_classes_db.main()
    except Exception as exc:
        print(f"  [WARN] Enrichment failed (non-fatal): {exc}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
