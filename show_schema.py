import sqlite3
con = sqlite3.connect("extra_classes.db")
cur = con.cursor()
cur.execute("SELECT sql FROM sqlite_master WHERE type='table' ORDER BY name")
for row in cur.fetchall():
    print(row[0])
    print()
con.close()
