import sqlite3

conn = sqlite3.connect('d:\\EDIP Suite\\backend\\edip.db')
cursor = conn.cursor()

cursor.execute("SELECT sql_query, error_message FROM query_logs ORDER BY id DESC LIMIT 5")
for row in cursor.fetchall():
    print(f"SQL: {row[0]}")
    print(f"ERROR: {row[1]}")
    print("-" * 50)
