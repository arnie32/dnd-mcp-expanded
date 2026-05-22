"""
generate_portrait_prompts.py

Reads all monsters from monster_templates.db and writes enemy_portrait_prompts.json.
Each entry contains:
  - slug          : index key (e.g. "goblin")
  - name          : display name (e.g. "Goblin")
  - challenge_rating
  - prompt        : image-generation prompt string

Also creates enemy_portraits/ directory (if absent) with a .gitkeep placeholder.
"""

import json
import os
import sqlite3

DB_PATH = os.path.join(os.path.dirname(__file__), "monster_templates.db")
OUTPUT_FILE = os.path.join(os.path.dirname(__file__), "enemy_portrait_prompts.json")
PORTRAITS_DIR = os.path.join(os.path.dirname(__file__), "enemy_portraits")


# ---------------------------------------------------------------------------
# Prompt assembly helpers
# ---------------------------------------------------------------------------

IMMUNITY_ADJECTIVES = {
    "fire":       "fire-resistant, flame-scarred hide",
    "cold":       "frost-hardened skin, cold-immune",
    "lightning":  "lightning-scarred, crackling with electricity",
    "poison":     "sickly green tinted, poison-resistant",
    "acid":       "acid-etched, corroded surface",
    "thunder":    "vibrating with thunder energy",
    "necrotic":   "shadowed by necrotic energy",
    "radiant":    "glowing with radiant light",
    "psychic":    "mind-shielded, blank expressionless eyes",
    "bludgeoning": "unnaturally durable, stone-like flesh",
    "slashing":   "blade-resistant scales or hide",
    "piercing":   "arrow-proof hide",
}


def immunity_hints(immunities: list) -> list[str]:
    hints = []
    for dmg in immunities:
        key = dmg.lower() if isinstance(dmg, str) else dmg.get("index", "").lower()
        if key in IMMUNITY_ADJECTIVES:
            hints.append(IMMUNITY_ADJECTIVES[key])
    return hints


def build_prompt(row: tuple) -> dict:
    index_key, name, size, mon_type, alignment, cr, combat_raw, raw_json_raw = row

    # Parse JSON blobs
    combat = json.loads(combat_raw) if combat_raw else {}
    raw = json.loads(raw_json_raw) if raw_json_raw else {}

    subtype = raw.get("subtype", "")
    type_phrase = f"{subtype} {mon_type}".strip() if subtype else mon_type

    # Special abilities — names only (keep it short)
    special_names = [sa["name"] for sa in combat.get("special_abilities", []) if sa.get("name")]

    # Actions — weapon/attack names
    action_names = [a["name"] for a in combat.get("actions", []) if a.get("name")]

    # Legendary actions
    legendary_names = [la["name"] for la in combat.get("legendary_actions", []) if la.get("name")]

    # Damage immunities → visual hints
    immunities = combat.get("damage_immunities", [])
    imm_hints = immunity_hints(immunities)

    # Senses
    senses = combat.get("senses", {})
    sense_parts = []
    if senses.get("darkvision"):
        sense_parts.append("darkvision eyes adapted for the dark")
    if senses.get("truesight"):
        sense_parts.append("all-seeing truesight gaze")
    if senses.get("blindsight"):
        sense_parts.append("blind but blindsight perception")
    if senses.get("tremorsense"):
        sense_parts.append("tremorsense antennae or vibration-sensitive organs")

    # Build characteristic parts list (de-duped, non-empty)
    characteristics = []
    if action_names:
        weapons = ", ".join(action_names)
        characteristics.append(f"armed with {weapons}")
    characteristics.extend(imm_hints)
    characteristics.extend(sense_parts)
    if special_names:
        abilities = ", ".join(special_names)
        characteristics.append(f"abilities: {abilities}")
    if legendary_names:
        characteristics.append(f"legendary: {', '.join(legendary_names)}")

    char_str = ", ".join(characteristics)

    # Compose final prompt
    parts = [
        f"Portrait of a {name} DnD full body illustration",
        f"{size} {type_phrase}",
        alignment,
    ]
    if char_str:
        parts.append(char_str)

    prompt = ", ".join(parts)

    return {
        "slug": index_key,
        "name": name,
        "challenge_rating": cr,
        "prompt": prompt,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """
        SELECT index_key, name, size, type, alignment, challenge_rating,
               combat_json, raw_json
        FROM monster_templates
        ORDER BY challenge_rating, name
        """
    )
    rows = cur.fetchall()
    conn.close()

    entries = []
    errors = []
    for row in rows:
        try:
            entries.append(build_prompt(row))
        except Exception as exc:
            errors.append({"slug": row[0], "error": str(exc)})
            print(f"  [WARN] {row[0]}: {exc}")

    # Write prompt file
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    # Create portraits directory
    os.makedirs(PORTRAITS_DIR, exist_ok=True)
    gitkeep = os.path.join(PORTRAITS_DIR, ".gitkeep")
    if not os.path.exists(gitkeep):
        open(gitkeep, "w").close()

    print(f"\nGenerated {len(entries)} prompts  ({len(errors)} errors)")
    print(f"Output   : {OUTPUT_FILE}")
    print(f"Directory: {PORTRAITS_DIR}")

    # Spot-check a few well-known creatures
    spot_check = {"goblin", "adult-red-dragon", "beholder", "lich", "tarrasque"}
    print("\n--- Spot checks ---")
    for e in entries:
        if e["slug"] in spot_check:
            print(f"\n[{e['slug']}]  CR {e['challenge_rating']}")
            print(f"  {e['prompt']}")


if __name__ == "__main__":
    main()
