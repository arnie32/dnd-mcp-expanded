"""Quick check of Templar + Holy Defender class/subclass status with the new SQL filter."""
import sqlite3

GENERICS = [
    'AbilityBonus','AbilityScore','LightArmor','MediumArmor','HeavyArmor','Shields',
    'SimpleWeapons','MartialWeapons','SavingThrow','SpellSlot','CommonerSpellSlot','WarlockSpellSlot',
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
gcsv = ",".join(f"'{g}'" for g in GENERICS)

SQL = f"""
SELECT r.class_name, r.subclass_name,
       COUNT(r.raw_id) AS total_refs,
       SUM(CASE
             WHEN r.raw_id IS NULL THEN 0
             WHEN r.raw_id GLOB '????????-????-????-????-????????????' THEN 0
             WHEN r.raw_id IN ({gcsv}) THEN 0
             WHEN a.raw_id IS NULL
               OR trim(COALESCE(a.name, '')) = ''
               OR trim(COALESCE(a.description, '')) = ''
             THEN 1 ELSE 0
           END) AS missing_refs
FROM class_ability_refs r
LEFT JOIN abilities a ON a.raw_id = r.raw_id
WHERE lower(r.class_name) IN ('templar', 'beastmaster (standalone)', 'chronomancer',
                               'dragoon', 'gunslinger', 'psion', 'runemaster',
                               'shaman', 'spellblade', 'summoner', 'warlord')
GROUP BY r.class_name, r.subclass_name
ORDER BY r.class_name, r.subclass_name
"""

con = sqlite3.connect("extra_classes.db")
con.row_factory = sqlite3.Row
rows = con.execute(SQL).fetchall()
print(f"{'Class':<35} {'Subclass':<25} {'Total':>6} {'Missing':>8} {'Status':>12}")
print("-" * 92)
for row in rows:
    cn = row["class_name"] or ""
    sc = row["subclass_name"] or "(base)"
    total = row["total_refs"] or 0
    miss = row["missing_refs"] or 0
    status = "COMPLETE" if miss == 0 else f"MISSING {miss}"
    print(f"{cn:<35} {sc:<25} {total:>6} {miss:>8} {status:>12}")
con.close()
