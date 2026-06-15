import pymysql

conn = pymysql.connect(host='100.86.181.18', port=3309, user='root', password='Tr@d3w@63', database='Tradeware', connect_timeout=15, autocommit=True)
cur = conn.cursor()
cur.execute("SELECT sql_query FROM query_logs WHERE status='success' ORDER BY id DESC LIMIT 5")
rows = cur.fetchall()
for r in rows:
    print(r[0])
conn.close()
