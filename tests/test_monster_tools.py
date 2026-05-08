#!/usr/bin/env python3
"""Tests for the monster normalizer and repository."""

import json
import sqlite3
import unittest

from src.monsters.normalizer import normalize_monster
from src.monsters.repository import (
    count_monsters,
    get_monster_by_index,
    search_monsters,
    upsert_monster,
)
from src.monsters.schema import ensure_schema


# ── Fixtures ─────────────────────────────────────────────────────────────────

GOBLIN_RAW = {
    "index": "goblin",
    "name": "Goblin",
    "size": "Small",
    "type": "humanoid",
    "subtype": "goblinoid",
    "alignment": "neutral evil",
    "armor_class": [{"value": 15, "type": "leather armor, shield"}],
    "hit_points": 7,
    "hit_dice": "2d6",
    "speed": {"walk": "30"},
    "strength": 8,
    "dexterity": 14,
    "constitution": 10,
    "intelligence": 10,
    "wisdom": 8,
    "charisma": 8,
    "proficiencies": [
        {"value": 4, "proficiency": {"index": "skill-stealth", "name": "Skill: Stealth"}},
    ],
    "damage_vulnerabilities": [],
    "damage_resistances": [],
    "damage_immunities": [],
    "condition_immunities": [],
    "senses": {"darkvision": "60 ft.", "passive_perception": 9},
    "languages": "Common, Goblin",
    "challenge_rating": 0.25,
    "xp": 50,
    "actions": [
        {"name": "Scimitar", "desc": "Melee Weapon Attack: +4 to hit, reach 5 ft., one target."},
        {"name": "Shortbow", "desc": "Ranged Weapon Attack: +4 to hit, range 80/320 ft., one target."},
    ],
    "special_abilities": [],
    "legendary_actions": [],
    "url": "/api/monsters/goblin",
}

DRAGON_RAW = {
    "index": "adult-red-dragon",
    "name": "Adult Red Dragon",
    "size": "Huge",
    "type": "dragon",
    "alignment": "chaotic evil",
    "armor_class": 19,
    "hit_points": 256,
    "hit_dice": "19d12",
    "speed": {"walk": "40", "climb": "40", "fly": "80"},
    "strength": 27,
    "dexterity": 10,
    "constitution": 25,
    "intelligence": 16,
    "wisdom": 13,
    "charisma": 21,
    "proficiencies": [
        {"value": 10, "proficiency": {"index": "saving-throw-dex", "name": "Saving Throw: DEX"}},
        {"value": 13, "proficiency": {"index": "saving-throw-con", "name": "Saving Throw: CON"}},
    ],
    "damage_vulnerabilities": [],
    "damage_resistances": [],
    "damage_immunities": ["fire"],
    "condition_immunities": [],
    "senses": {"blindsight": "60 ft.", "darkvision": "120 ft.", "passive_perception": 21},
    "languages": "Common, Draconic",
    "challenge_rating": 17,
    "xp": 18000,
    "actions": [
        {"name": "Multiattack", "desc": "The dragon can use its Frightful Presence."},
        {"name": "Bite", "desc": "Melee Weapon Attack: +14 to hit, reach 10 ft., one target."},
    ],
    "special_abilities": [
        {"name": "Legendary Resistance", "desc": "If the dragon fails a saving throw, it can choose to succeed instead."},
    ],
    "legendary_actions": [
        {"name": "Detect", "desc": "The dragon makes a Wisdom (Perception) check."},
    ],
    "url": "/api/monsters/adult-red-dragon",
}


def make_in_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    ensure_schema(conn)
    return conn


# ── Normalizer tests ──────────────────────────────────────────────────────────

class TestMonsterNormalizer(unittest.TestCase):

    def test_ac_extraction_from_list(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertEqual(result["combat"]["armor_class"], 15)

    def test_ac_extraction_from_number(self):
        result = normalize_monster(DRAGON_RAW)
        self.assertEqual(result["combat"]["armor_class"], 19)

    def test_index_key(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertEqual(result["index_key"], "goblin")

    def test_name(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertEqual(result["name"], "Goblin")

    def test_challenge_rating(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertAlmostEqual(result["challenge_rating"], 0.25)

    def test_abilities_mapping(self):
        result = normalize_monster(GOBLIN_RAW)
        abilities = result["combat"]["abilities"]
        self.assertEqual(abilities["str"], 8)
        self.assertEqual(abilities["dex"], 14)
        self.assertEqual(abilities["con"], 10)
        self.assertEqual(abilities["int"], 10)
        self.assertEqual(abilities["wis"], 8)
        self.assertEqual(abilities["cha"], 8)

    def test_compact_stat_block_contains_name(self):
        result = normalize_monster(GOBLIN_RAW)
        stat_block = result["ai_summary"]["compact_stat_block"]
        self.assertIn("Goblin", stat_block)

    def test_compact_stat_block_contains_ac_hp_cr(self):
        result = normalize_monster(GOBLIN_RAW)
        stat_block = result["ai_summary"]["compact_stat_block"]
        self.assertIn("AC 15", stat_block)
        self.assertIn("HP 7", stat_block)
        self.assertIn("CR 0.25", stat_block)

    def test_narration_tags(self):
        result = normalize_monster(GOBLIN_RAW)
        tags = result["ai_summary"]["narration_tags"]
        self.assertIn("humanoid", tags)
        self.assertIn("Small", tags)
        self.assertIn("neutral evil", tags)

    def test_skill_extraction(self):
        result = normalize_monster(GOBLIN_RAW)
        skills = result["combat"]["skills"]
        self.assertIn("Stealth", skills)
        self.assertEqual(skills["Stealth"], 4)

    def test_saving_throw_extraction(self):
        result = normalize_monster(DRAGON_RAW)
        saves = result["combat"]["saving_throws"]
        self.assertIn("DEX", saves)
        self.assertIn("CON", saves)

    def test_damage_immunities(self):
        result = normalize_monster(DRAGON_RAW)
        self.assertIn("fire", result["combat"]["damage_immunities"])

    def test_raw_preserved(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertEqual(result["raw"]["index"], "goblin")

    def test_source_fields(self):
        result = normalize_monster(GOBLIN_RAW)
        self.assertEqual(result["source"], "dnd5eapi")
        self.assertEqual(result["source_version"], "2014")


# ── Repository tests ──────────────────────────────────────────────────────────

class TestMonsterRepository(unittest.TestCase):

    def setUp(self):
        self.db = make_in_memory_db()
        goblin = normalize_monster(GOBLIN_RAW)
        dragon = normalize_monster(DRAGON_RAW)
        upsert_monster(self.db, goblin)
        upsert_monster(self.db, dragon)

    def tearDown(self):
        self.db.close()

    def test_get_by_index_found(self):
        result = get_monster_by_index(self.db, "goblin")
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "Goblin")

    def test_get_by_index_not_found(self):
        result = get_monster_by_index(self.db, "fake-monster-xyz")
        self.assertIsNone(result)

    def test_get_returns_combat_dict(self):
        result = get_monster_by_index(self.db, "goblin")
        self.assertIsInstance(result["combat"], dict)
        self.assertEqual(result["combat"]["armor_class"], 15)

    def test_get_returns_index_not_index_key(self):
        result = get_monster_by_index(self.db, "goblin")
        self.assertIn("index", result)
        self.assertNotIn("index_key", result)

    def test_upsert_updates_existing(self):
        modified = dict(GOBLIN_RAW)
        modified["hit_points"] = 99
        upsert_monster(self.db, normalize_monster(modified))
        result = get_monster_by_index(self.db, "goblin")
        self.assertEqual(result["combat"]["hit_points"], 99)

    def test_count(self):
        self.assertEqual(count_monsters(self.db), 2)

    def test_search_by_name(self):
        results = search_monsters(self.db, query="goblin")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["name"], "Goblin")

    def test_search_case_insensitive(self):
        results = search_monsters(self.db, query="GOBLIN")
        self.assertEqual(len(results), 1)

    def test_search_partial_name(self):
        results = search_monsters(self.db, query="dragon")
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["index"], "adult-red-dragon")

    def test_search_by_cr_max(self):
        results = search_monsters(self.db, cr_max=1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["index"], "goblin")

    def test_search_by_cr_min(self):
        results = search_monsters(self.db, cr_min=10)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["index"], "adult-red-dragon")

    def test_search_cr_range_excludes_all(self):
        results = search_monsters(self.db, cr_min=5, cr_max=10)
        self.assertEqual(len(results), 0)

    def test_search_no_filters_returns_all(self):
        results = search_monsters(self.db, limit=100)
        self.assertEqual(len(results), 2)

    def test_search_limit(self):
        results = search_monsters(self.db, limit=1)
        self.assertEqual(len(results), 1)

    def test_search_order_by_cr_asc(self):
        results = search_monsters(self.db, limit=100)
        crs = [r["combat"]["challenge_rating"] for r in results]
        self.assertEqual(crs, sorted(crs))


if __name__ == "__main__":
    unittest.main()
