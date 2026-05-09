"""Per-class gap report: shows total_refs, missing_refs, and pct for every class and subclass."""
import sqlite3
import re

DB_PATH = "extra_classes.db"
UUID_PAT = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

def run():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    cur = con.cursor()

    print("\n=== CLASS-LEVEL GAP REPORT ===")
    print(f"{'Class':<40} {'Total':>6} {'Miss':>6} {'Pct':>5}")
    print("-" * 62)

    cur.execute("""
        SELECT
            r.class_name,
            COUNT(*) as total_refs,
            SUM(CASE
                WHEN a.raw_id IS NULL
                  OR trim(COALESCE(a.name,'')) = ''
                  OR trim(COALESCE(a.description,'')) = ''
                THEN 1 ELSE 0 END) as missing_refs
        FROM class_ability_refs r
        LEFT JOIN abilities a ON a.raw_id = r.raw_id
        WHERE (r.subclass_name IS NULL OR r.subclass_name = '')
        GROUP BY r.class_name
        ORDER BY missing_refs DESC, r.class_name
    """)
    class_rows = cur.fetchall()
    complete = 0
    incomplete = 0
    for row in class_rows:
        name, total, miss = row["class_name"], row["total_refs"], row["missing_refs"]
        pct = int(100 * miss / total) if total else 0
        tag = "  OK" if miss == 0 else ""
        print(f"{name:<40} {total:>6} {miss:>6} {pct:>4}%{tag}")
        if miss == 0:
            complete += 1
        else:
            incomplete += 1
    print(f"\nClasses: {complete} complete, {incomplete} with missing refs\n")

    print("\n=== SUBCLASS-LEVEL GAP REPORT ===")
    print(f"{'Class / Subclass':<60} {'Total':>6} {'Miss':>6} {'Pct':>5}")
    print("-" * 78)

    cur.execute("""
        SELECT
            r.class_name,
            r.subclass_name,
            COUNT(*) as total_refs,
            SUM(CASE
                WHEN a.raw_id IS NULL
                  OR trim(COALESCE(a.name,'')) = ''
                  OR trim(COALESCE(a.description,'')) = ''
                THEN 1 ELSE 0 END) as missing_refs
        FROM class_ability_refs r
        LEFT JOIN abilities a ON a.raw_id = r.raw_id
        WHERE r.subclass_name IS NOT NULL AND r.subclass_name != ''
        GROUP BY r.class_name, r.subclass_name
        ORDER BY missing_refs DESC, r.class_name, r.subclass_name
    """)
    sub_rows = cur.fetchall()
    for row in sub_rows:
        label = f"  {row['class_name']} / {row['subclass_name']}"
        total, miss = row["total_refs"], row["missing_refs"]
        pct = int(100 * miss / total) if total else 0
        tag = "  OK" if miss == 0 else ""
        print(f"{label:<60} {total:>6} {miss:>6} {pct:>4}%{tag}")

    print("\n=== SAMPLE ORPHANED RAW_IDS (non-UUID, non-matched) ===")
    cur.execute("""
        SELECT DISTINCT r.raw_id, r.class_name
        FROM class_ability_refs r
        LEFT JOIN abilities a ON a.raw_id = r.raw_id
        WHERE a.raw_id IS NULL
        ORDER BY r.class_name, r.raw_id
        LIMIT 60
    """)
    orphan_rows = cur.fetchall()
    uuid_count = 0
    named_count = 0
    for row in orphan_rows:
        raw_id = row["raw_id"]
        is_uuid = bool(UUID_PAT.match(raw_id))
        if is_uuid:
            uuid_count += 1
        else:
            named_count += 1
        kind = "UUID" if is_uuid else "NAMED"
        print(f"  [{kind}] {row['class_name']}: {raw_id}")

    # Total UUID vs named counts across all orphans
    cur.execute("""
        SELECT r.raw_id
        FROM class_ability_refs r
        LEFT JOIN abilities a ON a.raw_id = r.raw_id
        WHERE a.raw_id IS NULL
    """)
    all_orphans = [r[0] for r in cur.fetchall()]
    total_uuid = sum(1 for r in all_orphans if UUID_PAT.match(r))
    total_named = len(all_orphans) - total_uuid
    print(f"\nAll orphaned refs: {len(all_orphans)} total — {total_uuid} UUID-pattern, {total_named} named (non-UUID)")

    con.close()

if __name__ == "__main__":
    run()
