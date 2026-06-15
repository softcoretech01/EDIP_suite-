import pymysql

schemas = ['Sales_Masters', 'Purchase_Masters', 'masters']
for schema in schemas:
    conn = pymysql.connect(host='100.86.181.18', port=3309, user='root', password='Tr@d3w@63', database=schema, connect_timeout=15, autocommit=True)
    cur = conn.cursor()
    cur.execute("SHOW TABLES")
    tables = [r[0] for r in cur.fetchall()]
    for t in tables:
        cur.execute(f"DESCRIBE {t}")
        cols = [r[0] for r in cur.fetchall()]
        print(f"{schema}.{t}: {', '.join(cols)}")
    conn.close()
