import re

sql = "SELECT T1.customer_name, (SUM(T2.supplied_qty * T2.unit_price) - SUM(T2.supplied_qty * T3.standardPrice)) / SUM(T2.supplied_qty * T2.unit_price) * 100 AS profit_margin FROM Sales_Masters.Invoice_Header AS T1 INNER JOIN Sales_Masters.Invoice_Details AS T2 ON T1.invoice_id = T2.invoice_id INNER JOIN masters.items AS T3 ON T2.item_id = T3.id GROUP BY T1.customer_name ORDER BY profit_margin DESC"

schema_context = """Table: `Sales_Masters.Invoice_Header`
Description: Stores Sales Invoice headers
Columns: invoice_id (VARCHAR(50)), so_id (VARCHAR(50)), cpo_ref (VARCHAR(50)), customer_name (VARCHAR(150)), amount (DECIMAL(15, 2)), tax_amount (DECIMAL(15, 2)), tax_type (VARCHAR(10)), total (DECIMAL(15, 2)), created_at (TIMESTAMP), updated_at (TIMESTAMP)

Table: `Sales_Masters.Invoice_Details`
Description: Line items for Sales Invoices
Columns: id (INTEGER), invoice_id (VARCHAR(50)), item_id (VARCHAR(50)), name (VARCHAR(150)), ordered_qty (DECIMAL(10, 2)), supplied_qty (DECIMAL(10, 2)), pending_qty (DECIMAL(10, 2)), unit_price (DECIMAL(15, 2))

Table: `masters.items`
Description: Master catalog of all inventory items
Columns: id (VARCHAR(50)), name (VARCHAR(100)), group_id (INTEGER), category_id (INTEGER), brand (VARCHAR(100)), model (VARCHAR(100)), size (VARCHAR(100)), color (VARCHAR(100)), uom_id (INTEGER), hsnCode (INTEGER), gst_percent_id (INTEGER), minStock (INTEGER), reorderLevel (INTEGER), batchApplicable (BIT), serialApplicable (BIT), isImported (BIT), active (BIT), standardPrice (DECIMAL(10, 2))"""

# Run the exact code from auto_remove_invalid_filters
alias_map = {}
tables = []
SQL_KEYWORDS = {"AS", "ON", "JOIN", "INNER", "LEFT", "RIGHT", "CROSS", "WHERE", "GROUP", "ORDER", "LIMIT", "USING", "AND", "OR", "UNION", "SELECT", "BY", "HAVING"}

for m in re.finditer(r'\b(?:FROM|JOIN)\s+([\w.]+)\b', sql, re.IGNORECASE):
    table_name = m.group(1)
    if table_name.upper() not in SQL_KEYWORDS:
        tables.append(table_name)
        start_pos = m.end()
        tail = sql[start_pos:].strip()
        alias_match = re.match(r'^(?:AS\s+)?([a-zA-Z0-9_]+)\b', tail, re.IGNORECASE)
        if alias_match:
            alias = alias_match.group(1)
            if alias.upper() not in SQL_KEYWORDS:
                alias_map[alias.upper()] = table_name

print("alias_map:", alias_map)
print("tables:", tables)

table_cols = {}
for block in schema_context.split('\n\n'):
    tm = re.search(r'Table:\s*`?([a-zA-Z0-9_.]+)', block)
    if tm:
        tbl_name = tm.group(1)
        cols = set(re.findall(r'Column:\s*`?([a-zA-Z0-9_]+)', block))
        if not cols:
            cm = re.search(r'Columns:\s*(.+)', block, re.DOTALL)
            if cm:
                cols = {c.split('(')[0].strip().replace('`', '').lower() for c in cm.group(1).split(',')}
        table_cols[tbl_name] = {c.lower() for c in cols}

print("table_cols keys:", table_cols.keys())

def repl_invalid_col(m: re.Match) -> str:
    alias = m.group(1)
    col = m.group(2)
    print(f"Matched: '{m.group(0)}' -> alias: '{alias}', col: '{col}'")
    
    if col.upper() in SQL_KEYWORDS or (alias and alias.upper() in SQL_KEYWORDS):
        return m.group(0)
        
    is_valid = False
    if alias:
        alias_upper = alias.upper()
        target_table = None
        if alias_upper in alias_map:
            target_table = alias_map[alias_upper]
        else:
            for t in tables:
                if t.upper() == alias_upper or t.split('.')[-1].upper() == alias_upper:
                    target_table = t
                    break
        
        if target_table:
            for t_real, cols in table_cols.items():
                if t_real.lower() == target_table.lower() or t_real.split('.')[-1].lower() == target_table.lower():
                    if col.lower() in cols:
                        is_valid = True
                        break
        else:
            is_valid = True
    else:
        if not tables:
            is_valid = True
        else:
            for target_table in tables:
                for t_real, cols in table_cols.items():
                    if t_real.lower() == target_table.lower() or t_real.split('.')[-1].lower() == target_table.lower():
                        if col.lower() in cols:
                            is_valid = True
                            break
                if is_valid:
                    break
                    
    if not is_valid:
        print(f"  -> INVALID! Replacing with 1=1")
        return "1=1"
    return m.group(0)

pattern = r'\b(?:([a-zA-Z_][a-zA-Z0-9_]*)\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(?:=|!=|<>|>=|<=|>|<|\bLIKE\b|\bNOT\s+LIKE\b|\bIN\b|\bNOT\s+IN\b|\bIS\b\s+(?:\bNOT\b\s+)?\bNULL\b)\s*(?:\'[^\']*\'|"[^"]*"|\d+(?:\.\d+)?|\([^)]*\)|(?:CURDATE|CURRENT_DATE|NOW)\(\)?|[a-zA-Z0-9_]+)?'

result = re.sub(pattern, repl_invalid_col, sql, flags=re.IGNORECASE)
print("-" * 50)
print("RESULT:")
print(result)
