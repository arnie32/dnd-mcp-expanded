"""Normalizer: transforms raw dnd5eapi monster JSON into a flat DB-ready dict."""

from datetime import datetime, timezone


def _normalize_armor_class(raw: dict) -> int:
    ac = raw.get("armor_class", 10)
    if isinstance(ac, list):
        return ac[0].get("value", 10) if ac else 10
    if isinstance(ac, (int, float)):
        return int(ac)
    return 10


def _normalize_abilities(raw: dict) -> dict:
    return {
        "str": raw.get("strength", 10),
        "dex": raw.get("dexterity", 10),
        "con": raw.get("constitution", 10),
        "int": raw.get("intelligence", 10),
        "wis": raw.get("wisdom", 10),
        "cha": raw.get("charisma", 10),
    }


def _extract_saving_throws(raw: dict) -> dict:
    result = {}
    for prof in raw.get("proficiencies", []):
        idx = prof.get("proficiency", {}).get("index", "")
        if "saving-throw" in idx:
            name = prof.get("proficiency", {}).get("name", "").replace("Saving Throw: ", "")
            result[name] = prof.get("value", 0)
    return result


def _extract_skills(raw: dict) -> dict:
    result = {}
    for prof in raw.get("proficiencies", []):
        idx = prof.get("proficiency", {}).get("index", "")
        if "skill" in idx:
            name = prof.get("proficiency", {}).get("name", "").replace("Skill: ", "")
            result[name] = prof.get("value", 0)
    return result


def _make_compact_stat_block(raw: dict, ac: int) -> str:
    actions = [a.get("name", "") for a in raw.get("actions", [])]
    speed_parts = [f"{k} {v}" for k, v in raw.get("speed", {}).items()]
    return (
        f"{raw.get('name', '')} | "
        f"AC {ac}, HP {raw.get('hit_points', 0)} | "
        f"CR {raw.get('challenge_rating', 0)} | "
        f"Speed {', '.join(speed_parts)} | "
        f"Actions: {', '.join(actions)}"
    )


def normalize_monster(raw: dict) -> dict:
    """Normalize raw dnd5eapi monster data into a DB-ready dict."""
    ac = _normalize_armor_class(raw)
    now = datetime.now(timezone.utc).isoformat()

    combat = {
        "armor_class": ac,
        "hit_points": raw.get("hit_points", 1),
        "hit_dice": raw.get("hit_dice"),
        "speed": raw.get("speed", {}),
        "challenge_rating": raw.get("challenge_rating", 0),
        "xp": raw.get("xp"),
        "abilities": _normalize_abilities(raw),
        "saving_throws": _extract_saving_throws(raw),
        "skills": _extract_skills(raw),
        "damage_vulnerabilities": raw.get("damage_vulnerabilities", []),
        "damage_resistances": raw.get("damage_resistances", []),
        "damage_immunities": raw.get("damage_immunities", []),
        "condition_immunities": [
            c.get("name", "") for c in raw.get("condition_immunities", [])
        ],
        "senses": raw.get("senses", {}),
        "languages": raw.get("languages"),
        "actions": raw.get("actions", []),
        "special_abilities": raw.get("special_abilities", []),
        "legendary_actions": raw.get("legendary_actions", []),
    }

    ai_summary = {
        "compact_stat_block": _make_compact_stat_block(raw, ac),
        "narration_tags": [
            t for t in [raw.get("type"), raw.get("size"), raw.get("alignment")]
            if t
        ],
    }

    return {
        "index_key": raw["index"],
        "name": raw["name"],
        "type": raw.get("type"),
        "size": raw.get("size"),
        "alignment": raw.get("alignment"),
        "challenge_rating": float(raw.get("challenge_rating", 0)),
        "source": "dnd5eapi",
        "source_version": "2014",
        "url": raw.get("url"),
        "combat": combat,
        "ai_summary": ai_summary,
        "raw": raw,
        "created_at": now,
        "updated_at": now,
    }
