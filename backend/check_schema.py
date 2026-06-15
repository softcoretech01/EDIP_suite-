import pymysql

conn = pymysql.connect(host='100.86.181.18', port=3309, user='root', password='Tr@d3w@63', database='Purchase_Masters', connect_timeout=15, autocommit=True)
cur = conn.cursor()
cur.execute("SHOW TABLES LIKE '%req%'")
rows = cur.fetchall()
for r in rows:
    print('Table:', r[0])
    cur.execute(f"DESCRIBE {r[0]}")
    for c in cur.fetchall():
        print('  ', c[0])
conn.close()
