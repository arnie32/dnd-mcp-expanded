"""Validate the new server.js SQL filter works correctly in SQLite."""
import sqlite3

DB_PATH = "extra_classes.db"
GENERICS = [
    'AbilityBonus','AbilityScore',
    'LightArmor','MediumArmor','HeavyArmor','Shields',
    'SimpleWeapons','MartialWeapons','SavingThrow',
    'SpellSlot','CommonerSpellSlot','WarlockSpellSlot',
    'UnlockedSpellSlotLevel1','UnlockedSpellSlotLevel2','UnlockedSpellSlotLevel3',
    'UnlockedSpellSlotLevel4','UnlockedSpellSlotLevel5','UnlockedSpellSlotLevel6',
    'UnlockedSpellSlotLevel7','UnlockedSpellSlotLevel8','UnlockedSpellSlotLevel9',
    'UnlockedWarlockSpellSlotLevel1','UnlockedWarlockSpellSlotLevel2','UnlockedWarlockSpellSlotLevel3',
    'ExtraAttack','Skill','Cantrips','MusicalInstrument',
    'BardSpells','BardSpellcasting','BardCantrip','ChannelOath',
    'Shortswords','Daggers','HandCrossbows','Rapiers','Scimitars','LightCrossbows',
    'Slings','Clubs','Longswords','Quarterstaffs','Sickles','Flails','Morningstars',
    'Blades','Firearms','Warhammers',
    'SneakAttack_Charge','Evasion','DeflectMissiles_Charge','WarMagic',
]
generic_csv = ",".join(f"'{g}'" for g in GENERICS)

SQL = f"""
SELECT c.class_name, ar.subclass_name,
       COUNT(ar.raw_id) AS total_refs,
       SUM(CASE
             WHEN ar.raw_id IS NULL THEN 0
             WHEN ar.raw_id GLOB '????????-????-????-????-????????????' THEN 0
             WHEN ar.raw_id IN ({generic_csv}) THEN 0
             WHEN a.raw_id IS NULL
               OR trim(COALESCE(a.name, '')) = ''
               OR trim(COALESCE(a.description, '')) = ''
             THEN 1 ELSE 0
           END) AS missing_refs
FROM classes c
LEFT JOIN class_ability_refs ar ON lower(ar.class_name) = lower(c.class_name)
LEFT JOIN abilities a ON a.raw_id = ar.raw_id
GROUP BY c.class_name, ar.subclass_name
ORDER BY c.class_name, ar.subclass_name
"""

con = sqlite3.connect(DB_PATH)
con.row_factory = sqlite3.Row
rows = con.execute(SQL).fetchall()

class_map = {}
for row in rows:
    cn = (row["class_name"] or "").strip()
    if not cn:
        continue
    e = class_map.get(cn, {"total_refs": 0, "missing_refs": 0})
    e["total_refs"] += row["total_refs"] or 0
    e["missing_refs"] += row["missing_refs"] or 0
    class_map[cn] = e

complete = [(n, e) for n, e in class_map.items() if e["missing_refs"] == 0]
incomplete = [(n, e) for n, e in class_map.items() if e["missing_refs"] > 0]
print(f"SQL result: {len(complete)} complete, {len(incomplete)} incomplete\n")

print("=== STILL INCOMPLETE (class-level) ===")
for n, e in sorted(incomplete, key=lambda x: -x[1]["missing_refs"]):
    print(f"  {n:<38} total={e['total_refs']:>4}  missing={e['missing_refs']:>3}")

print("\n=== NOW COMPLETE ===")
for n, e in sorted(complete, key=lambda x: x[0]):
    was_zero = e["total_refs"] == 0
    tag = "  (no refs)" if was_zero else ""
    print(f"  {n}{tag}")

con.close()
