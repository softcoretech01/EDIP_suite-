import sqlite3
conn = sqlite3.connect('edip.db')
c = conn.cursor()
c.execute("SELECT id, error_message FROM query_logs WHERE status='error' ORDER BY id DESC")
print(c.fetchall())
