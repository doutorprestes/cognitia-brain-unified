import sqlite3
conn = sqlite3.connect("data/cognitia.db")
c = conn.cursor()

c.execute("DELETE FROM items WHERE type = 'grant'")
print(f"Grants falsos removidos: {c.rowcount}")

c.execute("SELECT COUNT(*) FROM items WHERE type = 'grant'")
print(f"Grants restantes: {c.fetchone()[0]}")

conn.commit()
conn.close()
