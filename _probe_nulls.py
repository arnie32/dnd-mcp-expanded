import sys, re
sys.path.insert(0, '.')
from src.extra_classes.db import open_db
db = open_db()
uuid_pat = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', re.I)

# Abilities: in table, name is null, but HAS a description
rows = db.execute(
    "SELECT raw_id, description FROM abilities WHERE name IS NULL AND description IS NOT NULL AND length(description) > 0"
).fetchall()
named = [(r['raw_id'], r['description']) for r in rows if not uuid_pat.match(r['raw_id'])]
all_ids = [(r['raw_id'], r['description']) for r in rows]
print('Has description but null name (all):', len(all_ids))
print('Has description but null name (non-UUID):', len(named))
print()
for raw_id, desc in named[:20]:
    print('ID:', raw_id)
    print('Desc:', desc[:150])
    print()
