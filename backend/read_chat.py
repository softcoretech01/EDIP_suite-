import sqlite3

conn = sqlite3.connect('d:\\EDIP Suite\\backend\\edip.db')
cursor = conn.cursor()

cursor.execute("SELECT question, generated_sql, response_json FROM chat_history ORDER BY id DESC LIMIT 2")
for row in cursor.fetchall():
    print(f"QUESTION: {row[0]}")
    print(f"SQL: {row[1]}")
    print(f"JSON: {row[2]}")
    print("-" * 50)
