import json, sqlite3, sys
db_path = sys.argv[1]
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row
rows = conn.execute("""
SELECT c.class_name, ar.subclass_name,
       COUNT(ar.raw_id) AS total_refs,
       SUM(CASE
             WHEN ar.raw_id IS NULL THEN 0
             WHEN ar.raw_id GLOB '????????-????-????-????-????????????' THEN 0
             WHEN ar.raw_id IN (
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
               'SneakAttack_Charge','Evasion','DeflectMissiles_Charge','WarMagic'
             ) THEN 0
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
""").fetchall()
class_map = {}
subclass_map = {}
for row in rows:
    class_name = (row["class_name"] or "").strip()
    if not class_name:
        continue
    total_refs = int(row["total_refs"] or 0)
    missing_refs = int(row["missing_refs"] or 0)
    class_entry = class_map.get(class_name, {"total_refs": 0, "missing_refs": 0})
    class_entry["total_refs"] += total_refs
    class_entry["missing_refs"] += missing_refs
    class_map[class_name] = class_entry
    subclass_name = (row["subclass_name"] or "").strip()
    if subclass_name:
        subclass_map.setdefault(class_name, {})[subclass_name] = {
            "total_refs": total_refs,
            "missing_refs": missing_refs,
            "incomplete": (total_refs > 0) and (missing_refs > 0)
        }
output = {"classBuildStatus": {}, "subclassBuildStatusByClass": subclass_map}
for class_name, entry in class_map.items():
    total_refs = int(entry.get("total_refs", 0))
    missing_refs = int(entry.get("missing_refs", 0))
    output["classBuildStatus"][class_name] = {
        "total_refs": total_refs,
        "missing_refs": missing_refs,
        "incomplete": (total_refs > 0) and (missing_refs > 0)
    }
print(json.dumps(output))
conn.close()
