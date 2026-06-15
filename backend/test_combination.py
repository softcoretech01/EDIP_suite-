import re

# This is the SQL AFTER auto_fix_collation
sql = "SELECT T1.customer_name, (SUM(T2.supplied_qty * T2.unit_price) - SUM(T2.supplied_qty * T3.standardPrice)) / SUM(T2.supplied_qty * T2.unit_price) * 100 AS profit_margin FROM Sales_Masters.Invoice_Header AS T1 INNER JOIN Sales_Masters.Invoice_Details AS T2 ON T1.invoice_id COLLATE utf8mb4_unicode_ci = T2.invoice_id COLLATE utf8mb4_unicode_ci INNER JOIN masters.items AS T3 ON T2.item_id COLLATE utf8mb4_unicode_ci = T3.id COLLATE utf8mb4_unicode_ci GROUP BY T1.customer_name ORDER BY profit_margin DESC"

schema_context = """Table: `Sales_Masters.Invoice_Header`
Columns: invoice_id, customer_name, total, created_at, amount, tax_amount

Table: `Sales_Masters.Invoice_Details`
Columns: id, invoice_id, item_id, name, ordered_qty, supplied_qty, pending_qty, unit_price

Table: `masters.items`
Columns: id, name, standardprice"""

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
        cols = {c.strip().lower() for c in block.split('Columns:')[1].split(',')}
        table_cols[tbl_name] = cols

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
