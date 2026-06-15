import sqlite3

conn = sqlite3.connect('d:\\EDIP Suite\\backend\\edip.db')
cursor = conn.cursor()

cursor.execute("SELECT id, name FROM erp_connections")
for row in cursor.fetchall():
    print(f"ID: {row[0]}, Name: {row[1]}")
